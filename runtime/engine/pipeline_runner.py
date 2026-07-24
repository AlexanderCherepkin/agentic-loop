from __future__ import annotations

import asyncio
import importlib.util
import re
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

from ..contracts.agent_spec import AgentSpec
from ..contracts.message import Message, MessageType
from .agent_loader import AgentLoader
from .llm_engine import EvaluationEngine, LLMEngine, LLMResponse
from .message_bus import MessageBus
from .state_manager import StateManager
from ..observability.resource_monitor import ResourceLevel, ResourceMonitor
from ..safety.audit_logger import AuditLogger, AuditEventType
from tools_terminal.tui_dashboard import render_dashboard
from ..safety.file_system_guard import FSOperation, FileSystemGuard, FileSystemGuardError
from ..safety.network_guard import NetworkGuard, NetworkVerdict
from ..safety.safety_chain import SafetyChain, SafetyVerdict
from .agent_invocation_map import (
    PHASE_AGENTS,
    PLANNING_FLAG_GROUPS,
    conditional_groups_for_flags,
    phase_dispatch,
)

# Optional MCP integration
try:
    from mcp_servers.bootstrap import create_registry
    from mcp_servers.gateway import MCPGateway
    from mcp_servers.registry import MCPRegistry as _MCPRegistry
    HAS_MCP = True
except ImportError:
    HAS_MCP = False

# Optional Figma integration
def _load_figma_config_module():
    """Load figma-agent-core/config.py without requiring a valid Python package name."""
    core_dir = Path(__file__).resolve().parent.parent.parent / "figma-agent-core"
    config_path = core_dir / "config.py"
    if not config_path.exists():
        return None
    spec = importlib.util.spec_from_file_location("figma_config", str(config_path))
    if not spec or not spec.loader:
        return None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_figma_config_mod = _load_figma_config_module()
HAS_FIGMA_CONFIG = _figma_config_mod is not None


class TerminationStatus(str, Enum):
    SUCCESS = "success"
    PARTIAL = "partial"
    FAILURE = "failure"
    ESCALATED_HUMAN = "escalated_human"


class PipelineStatus(str, Enum):
    RUNNING = "running"
    COMPLETED = "completed"


@dataclass
class PhaseTransition:
    next_phase: str
    reason: str
    safety_override: TerminationStatus | None = None


class PhaseTransitionManager:
    """Routes the ReAct loop between phases based on agent outputs.

    Default sequence: planning → execution → observability → self_correction → result.
    Agent outputs can override the next phase (e.g., skip replanning, escalate to result).
    """

    def __init__(self, max_iterations: int = 5):
        self.max_iterations = max_iterations
        self._phase_history: list[str] = []

    def next_phase(self, current_phase: str, state: dict[str, Any], iteration: int) -> PhaseTransition:
        """Decide the next ReAct phase and optional safety override."""
        self._phase_history.append(current_phase)

        # Cycle detection: if a phase repeats too often, force termination
        if self._phase_history.count(current_phase) > 3:
            return PhaseTransition(
                next_phase="result",
                reason=f"Phase '{current_phase}' visited 4 times — possible loop",
                safety_override=TerminationStatus.PARTIAL,
            )

        if current_phase == "planning":
            return self._from_planning(state)
        if current_phase == "execution":
            return self._from_execution(state)
        if current_phase == "observability":
            return PhaseTransition(next_phase="self_correction", reason="Observation complete; proceed to validation")
        if current_phase == "self_correction":
            return self._from_self_correction(state, iteration)

        return PhaseTransition(next_phase="result", reason="Unknown phase — terminating safely")

    def _from_planning(self, state: dict[str, Any]) -> PhaseTransition:
        recommendation = self._get(state, "cost_risk_assessment.recommendation", "cost_risk_assessment", "recommendation")
        if recommendation == "escalate":
            return PhaseTransition(
                next_phase="result",
                reason="Cost/risk assessment recommends escalation",
                safety_override=TerminationStatus.ESCALATED_HUMAN,
            )
        if recommendation == "reduce_scope":
            return PhaseTransition(next_phase="planning", reason="Scope reduced; replan before execution")
        plan = state.get("plan", {})
        if plan.get("spec_scope_aligned") is False:
            return PhaseTransition(
                next_phase="self_correction",
                reason=f"Plan deviates from approved spec scope: {plan.get('spec_alignment_reason', 'unknown')}",
            )
        hint = self._get(state, "cost_risk_assessment.next_phase_hint")
        if hint in ("execution", "planning", "result"):
            return PhaseTransition(next_phase=hint, reason="Explicit next_phase_hint from cost_risk_assessment")
        return PhaseTransition(next_phase="execution", reason="Planning complete; proceed to execution")

    def _from_execution(self, state: dict[str, Any]) -> PhaseTransition:
        next_action = self._get(state, "execution.next_action", "tool_invocation", "next_action")
        if next_action == "abort":
            return PhaseTransition(
                next_phase="result",
                reason="Tool invocation aborted",
                safety_override=TerminationStatus.FAILURE,
            )
        if next_action == "escalate":
            return PhaseTransition(
                next_phase="result",
                reason="Tool invocation requires escalation",
                safety_override=TerminationStatus.ESCALATED_HUMAN,
            )

        guardrail_status = self._get(state, "execution.guardrail_status", "safety_guardrails", "guardrail_status")
        if guardrail_status == "aborted":
            return PhaseTransition(
                next_phase="result",
                reason="Safety guardrails aborted execution",
                safety_override=TerminationStatus.FAILURE,
            )

        recommendation = self._get(state, "execution.recommendation", "safety_guardrails", "recommendation")
        if recommendation == "escalate_to_human":
            return PhaseTransition(
                next_phase="result",
                reason="Safety guardrails requested human escalation",
                safety_override=TerminationStatus.ESCALATED_HUMAN,
            )
        if recommendation == "resume_with_limits":
            return PhaseTransition(next_phase="execution", reason="Resume execution with adjusted limits")

        hint = self._get(state, "execution.next_phase_hint")
        if hint in ("observability", "execution", "result"):
            return PhaseTransition(next_phase=hint, reason="Explicit next_phase_hint from execution")
        return PhaseTransition(next_phase="observability", reason="Execution complete; proceed to observation")

    def _from_self_correction(self, state: dict[str, Any], iteration: int) -> PhaseTransition:
        validation_status = self._get(state, "validation.validation_status", "result_validation", "validation_status")
        retry_recommended = self._get(state, "validation.retry_recommended", "result_validation", "retry_recommended")
        decision = self._get(state, "validation.decision", "recursion_or_termination", "decision")

        # First honor the explicit recursion/termination decision if present
        if decision == "terminate_success":
            return PhaseTransition(
                next_phase="result",
                reason="Termination decision: success",
                safety_override=TerminationStatus.SUCCESS,
            )
        if decision == "terminate_failure":
            return PhaseTransition(
                next_phase="result",
                reason="Termination decision: failure",
                safety_override=TerminationStatus.FAILURE,
            )
        if decision == "terminate_partial":
            return PhaseTransition(
                next_phase="result",
                reason="Termination decision: partial",
                safety_override=TerminationStatus.PARTIAL,
            )
        if decision == "escalate_human":
            return PhaseTransition(
                next_phase="result",
                reason="Termination decision: escalate to human",
                safety_override=TerminationStatus.ESCALATED_HUMAN,
            )
        if decision == "recurse":
            adjusted_plan = state.get("adjusted_plan")
            if adjusted_plan:
                return PhaseTransition(next_phase="execution", reason="Recurse with adjusted plan")
            return PhaseTransition(next_phase="planning", reason="Recurse without adjusted plan — replan")

        # Then evaluate validation status
        if validation_status == "complete":
            return PhaseTransition(
                next_phase="result",
                reason="Validation complete",
                safety_override=TerminationStatus.SUCCESS,
            )
        if validation_status in ("partial", "failed") and retry_recommended:
            return PhaseTransition(next_phase="planning", reason=f"Validation={validation_status}; retry recommended")
        if validation_status == "inconclusive":
            if iteration < self.max_iterations / 2:
                return PhaseTransition(next_phase="execution", reason="Inconclusive early — gather more data")
            return PhaseTransition(
                next_phase="result",
                reason="Inconclusive late — escalate",
                safety_override=TerminationStatus.ESCALATED_HUMAN,
            )

        hint = self._get(state, "validation.next_phase_hint", "result_validation", "next_phase_hint")
        if hint in ("self_correction", "execution", "planning", "result"):
            return PhaseTransition(next_phase=hint, reason="Explicit next_phase_hint from validation")

        # Default: if we still have budget, try one more execution; otherwise result partial
        if iteration < self.max_iterations:
            return PhaseTransition(next_phase="execution", reason="Default continue to execution")
        return PhaseTransition(
            next_phase="result",
            reason="Max iterations reached",
            safety_override=TerminationStatus.PARTIAL,
        )

    @staticmethod
    def _get(state: dict[str, Any], dotted_key: str, *fallback_keys: str) -> Any:
        """Resolve a value from the state dict.

        Tries the dotted path first, then treats fallback_keys as an alternate
        dotted path under each common prefix (e.g. ``tool_invocation.next_action``).
        """

        def _resolve(obj: Any, path: list[str]) -> Any:
            for k in path:
                if isinstance(obj, dict):
                    obj = obj.get(k)
                else:
                    return None
            return obj

        value = _resolve(state, dotted_key.split("."))
        if value is not None:
            return value

        if fallback_keys:
            fallback_path = ".".join(str(k) for k in fallback_keys).split(".")
            for prefix in ["", "execution", "validation"]:
                root = state.get(prefix, {}) if prefix else state
                value = _resolve(root, fallback_path)
                if value is not None:
                    return value

        return None


@dataclass
class IterationTrace:
    iteration: int
    phase: str
    agent_path: str
    inputs: dict[str, Any]
    outputs: dict[str, Any] | None
    latency_ms: float
    success: bool
    error: str | None = None


@dataclass
class SessionMetrics:
    session_id: str
    iterations: int = 0
    tools_used: list[str] = field(default_factory=list)
    time_elapsed_ms: float = 0
    tokens_consumed: int = 0
    safety_checks_passed: int = 0
    safety_checks_failed: int = 0


@dataclass
class PipelineResult:
    final_response: str
    termination_status: TerminationStatus
    session_metrics: SessionMetrics
    audit_anchor: str
    trace: list[IterationTrace] = field(default_factory=list)


class PipelineRunner:
    # Dispatch lists are maintained centrally in agent_invocation_map.py so that
    # every loaded agent has a documented runtime invocation path.
    FLOW_SEQUENCE = phase_dispatch("planning_core")
    SAFETY_AGENTS = phase_dispatch("safety_pre_check")
    MUTUAL_CHECK_AGENTS = phase_dispatch("mutual_check")
    EXECUTION_CORE = phase_dispatch("execution_core")
    OBSERVABILITY_CORE = phase_dispatch("observability")
    VALIDATION_CORE = phase_dispatch("self_correction")
    RESULT_AGENTS = phase_dispatch("result")
    SAFETY_POST_CHECK_AGENTS = phase_dispatch("safety_post_check")
    ORCHESTRATOR_AGENTS = phase_dispatch("orchestrator")
    CONTROL_AGENTS = phase_dispatch("control")

    def __init__(self, loader: AgentLoader, llm: LLMEngine, bus: MessageBus, state: StateManager,
                 workspace_root: str = ".", max_workers: int = 4, max_iterations: int = 5,
                 coverage_mode: bool = False):
        self.loader = loader
        self.llm = llm
        self.bus = bus
        self.state = state
        self.workspace = workspace_root
        self._max_iterations = max_iterations
        self._coverage_mode = coverage_mode
        self._agent_cache: dict[str, AgentSpec] = {}
        rules_data = self._load_project_rules()
        self._project_rules = {k: rules_data[k] for k in ("source", "content_hash", "sections")} if rules_data else None
        self._system_context = rules_data.get("system_context") if rules_data else None
        self._evaluator = EvaluationEngine(llm.config) if llm.config.use_evaluator else None

        self._safety_chain = SafetyChain()
        self._fs_guard = FileSystemGuard(workspace_root=self.workspace)
        self._network_guard = NetworkGuard()
        self._resource_monitor = ResourceMonitor(workspace_root=self.workspace)
        self._last_resource_state: dict[str, Any] | None = None
        self._audit_logger = AuditLogger(log_dir=Path(self.workspace) / ".audit", buffer_size=1)
        self._current_audit_anchor: str | None = None

        self._mcp_gateway = None
        if HAS_MCP:
            try:
                registry = create_registry(workspace_root, eager=False)
                self._mcp_gateway = MCPGateway(registry)
            except Exception:
                pass

    def _load_project_rules(self) -> dict[str, Any] | None:
        """Load lightweight project rules and CLAUDE.md from workspace root."""
        rules_path = Path(self.workspace) / "project_rules.md"
        claude_path = Path(self.workspace) / "CLAUDE.md"
        rules_text = rules_path.read_text(encoding="utf-8") if rules_path.exists() else ""
        claude_text = claude_path.read_text(encoding="utf-8") if claude_path.exists() else ""
        if not rules_text and not claude_text:
            return None
        try:
            sections = self._parse_project_rules(rules_text) if rules_text else {}
            project_summary = self._summarize_markdown(rules_text)
            claude_summary = self._summarize_markdown(claude_text)
            return {
                "source": str(rules_path) if rules_path.exists() else None,
                "content_hash": hash(rules_text) & 0xFFFFFFFF if rules_text else 0,
                "sections": sections,
                "claude_md_source": str(claude_path) if claude_path.exists() else None,
                "claude_md_content_hash": hash(claude_text) & 0xFFFFFFFF if claude_text else 0,
                "project_rules_summary": project_summary,
                "claude_md_summary": claude_summary,
                "system_context": self._build_system_context(project_summary, claude_summary),
            }
        except Exception:
            return None

    @staticmethod
    def _parse_project_rules(text: str) -> dict[str, list[str]]:
        """Parse project_rules.md into sections."""
        sections: dict[str, list[str]] = {}
        current: str | None = None
        for line in text.splitlines():
            if line.startswith("# "):
                continue
            if line.startswith("## "):
                current = line[3:].strip()
                sections[current] = []
            elif current and line.strip():
                sections[current].append(line.strip())
        return sections

    @staticmethod
    def _summarize_markdown(text: str, max_chars: int = 2400) -> str:
        """Compress markdown to headings, lists, tables, and short directives."""
        if not text:
            return ""
        kept: list[str] = []
        in_code_fence = False
        for raw in text.splitlines():
            line = raw.rstrip()
            if not line:
                continue
            stripped = line.lstrip()
            if stripped.startswith("```"):
                in_code_fence = not in_code_fence
                continue
            if in_code_fence or raw.startswith("  "):
                kept.append(line)
                continue
            if stripped.startswith(("# ", "## ", "### ", "#### ", "- ", "* ", "| ")):
                kept.append(line)
                continue
            if re.match(r"^\d+\.\s", stripped):
                kept.append(line)
                continue
            if len(stripped) <= 120 and any(marker in stripped for marker in ("—", "→", ":", "|", "must", "always", "never", "Gate", "Rules", "Conventions", "Safety", "Scope")):
                kept.append(line)
                continue
        summary = "\n".join(kept)
        if len(summary) > max_chars:
            summary = summary[:max_chars].rsplit("\n", 1)[0] + "\n..."
        return summary

    @staticmethod
    def _build_system_context(project_summary: str, claude_summary: str, max_total_chars: int = 4000) -> str:
        """Assemble the summarized project rules and CLAUDE.md into one system block."""
        parts = [
            "# Project System Context\n",
            "The following project-wide rules and CLAUDE.md directives are mandatory for every agent in this session.",
        ]
        if project_summary:
            parts.append("\n## Project Rules\n" + project_summary)
        if claude_summary:
            parts.append("\n## CLAUDE.md Directives\n" + claude_summary)
        context = "\n".join(parts)
        if len(context) > max_total_chars:
            context = context[:max_total_chars].rsplit("\n", 1)[0] + "\n..."
        return context

    def _system_context_for_phase(self, phase: str) -> str | None:
        """Return the shared system context for phases that must obey project-wide rules."""
        if phase not in ("planning", "execution"):
            return None
        return self._system_context

    @property
    def mcp_enabled(self) -> bool:
        return self._mcp_gateway is not None and self.llm.config.mcp_enabled

    @property
    def figma_available(self) -> bool:
        """True when figma-agent-core is present and Figma credentials are configured."""
        if not self.mcp_enabled:
            return False
        if not HAS_FIGMA_CONFIG or _figma_config_mod is None:
            return False
        core_dir = Path(self.workspace) / "figma-agent-core"
        if not core_dir.exists():
            return False
        return _figma_config_mod.is_figma_configured()

    # Maps MCP tool names to filesystem guard parameters. Any tool that touches
    # files must be listed here so execution is blocked deterministically before
    # reaching the MCP server.
    _FS_MCP_TOOL_PATTERNS = {
        # tools_read
        "read_file": (FSOperation.READ, ("path", "file_path")),
        "detect_encoding": (FSOperation.READ, ("path", "file_path")),
        "get_file_info": (FSOperation.READ, ("path", "file_path")),
        "read_chunk": (FSOperation.READ, ("path", "file_path")),
        "extract_content": (FSOperation.READ, ("path", "file_path")),
        "validate_integrity": (FSOperation.READ, ("path", "file_path")),
        "list_directory": (FSOperation.READ, ("path", "file_path")),
        # tools_replace
        "write_file": (FSOperation.WRITE, ("path", "file_path")),
        "create_backup": (FSOperation.READ, ("path", "file_path")),
        "match_pattern": (FSOperation.READ, ("path", "file_path")),
        "apply_edit": (FSOperation.WRITE, ("path", "file_path")),
        "validate_edit": (FSOperation.READ, ("path", "file_path")),
        "verify_write": (FSOperation.READ, ("path", "file_path")),
        "rollback": (FSOperation.WRITE, ("path", "file_path")),
        "safe_delete": (FSOperation.DELETE, ("path", "file_path")),
        # tools_search
        "regex_search": (FSOperation.READ, ("path", "file_path")),
        "semantic_search": (FSOperation.READ, ("path", "file_path")),
        "define_scope": (FSOperation.READ, ("path", "file_path")),
        "generate_snippet": (FSOperation.READ, ("path", "file_path")),
        "find_symbol": (FSOperation.READ, ("path", "file_path")),
        # tools_runcom (command itself is checked by the runcom server; paths inside it are guarded here)
        "setup_environment": (FSOperation.READ, ("path", "cwd")),
        "execute_command": (FSOperation.READ, ("path", "cwd")),
        "get_history": (FSOperation.READ, ("path", "cwd")),
        # tools_runtest
        "discover_tests": (FSOperation.READ, ("path",)),
        "optimize_suite": (FSOperation.READ, ("path",)),
        "generate_report": (FSOperation.READ, ("path", "output_dir")),
        # tools_terminal
        "create_session": (FSOperation.READ, ("path", "cwd")),
        "get_session_history": (FSOperation.READ, ("path", "cwd")),
        # tools_manangr
        "analyze_structure": (FSOperation.READ, ("path",)),
        "map_dependencies": (FSOperation.READ, ("path", "root")),
        "analyze_impact": (FSOperation.READ, ("path", "root")),
        "generate_docs": (FSOperation.READ, ("path", "output_dir")),
        "organize_files": (FSOperation.WRITE, ("path", "root", "output_dir")),
        # tools_memory (memory store is abstract, but any disk path argument is guarded)
        "write_memory": (FSOperation.WRITE, ("path", "file_path")),
        "index_entry": (FSOperation.WRITE, ("path", "file_path")),
    }

    # Maps MCP tool names to URL argument keys for network guard checks.
    _NETWORK_MCP_TOOL_PATTERNS = {
        # tools_web
        "build_request": ("url",),
        "check_network": ("url",),
        "send_request": ("url",),
        "handle_retry": ("url",),
        "cache_response": ("url",),
        # tools_browser
        "browser_navigate": ("url",),
        "browser_open": ("url",),
        # tools_runcom (commands may contain URLs; guard the explicit url/cwd keys)
        "execute_command": ("url",),
        # tools_runtest
        "discover_tests": ("url",),
    }

    async def execute_mcp_tool(self, tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        """Execute a tool via MCP servers directly — bypasses LLM for actual I/O operations.

        Filesystem guard: any file path argument is validated before the tool runs.
        Write/delete/execute operations outside allowed directories are blocked deterministically.
        Network guard: any URL argument is validated against the allow-list before egress.
        """
        if not self._mcp_gateway:
            return {"error": "MCP not available", "is_error": True}

        fs_check = self._check_fs_for_tool(tool_name, arguments)
        if fs_check:
            self._audit_logger.log_safety_blocked(
                f"mcp:{tool_name}", "", self._current_audit_anchor or "",
                fs_check.get("error", "filesystem guard blocked"),
            )
            return fs_check

        network_check = self._check_network_for_tool(tool_name, arguments)
        if network_check:
            self._audit_logger.log_safety_blocked(
                f"mcp:{tool_name}", "", self._current_audit_anchor or "",
                network_check.get("error", "network guard blocked"),
            )
            return network_check

        safety_check = self._check_safety_for_tool(tool_name, arguments)
        if safety_check:
            self._audit_logger.log_safety_blocked(
                f"mcp:{tool_name}", "", self._current_audit_anchor or "",
                safety_check.get("error", "safety chain blocked"),
            )
            return safety_check

        mcp_agent = f"mcp:{tool_name}"
        self._audit_logger.log_tool_invoked(mcp_agent, "", self._current_audit_anchor or "", arguments)
        t0 = time.perf_counter()
        try:
            result = await self._mcp_gateway.execute(tool_name, arguments)
            latency = (time.perf_counter() - t0) * 1000
            output_summary = {"tool": tool_name, "mcp_executed": True}
            if isinstance(result, dict):
                output_summary["is_error"] = result.get("is_error", False)
                output_summary["keys"] = list(result.keys())[:10]
            self._audit_logger.log_tool_completed(mcp_agent, "", self._current_audit_anchor or "", output_summary, latency)
            return {"tool": tool_name, "result": result, "mcp_executed": True}
        except Exception as e:
            self._audit_logger.log_tool_failed(mcp_agent, "", self._current_audit_anchor or "", str(e))
            return {"tool": tool_name, "error": str(e), "is_error": True, "mcp_executed": False}

    def _check_fs_for_tool(self, tool_name: str, arguments: dict[str, Any]) -> dict[str, Any] | None:
        """Return a guarded error dict if the tool touches a disallowed path; otherwise None."""
        operation, keys = self._FS_MCP_TOOL_PATTERNS.get(tool_name, (None, ()))
        if operation is None:
            return None

        for key in keys:
            raw_path = arguments.get(key)
            if not raw_path or not isinstance(raw_path, str):
                continue
            try:
                result = self._fs_guard.check(raw_path, operation)
            except Exception as e:
                return {"error": f"Filesystem guard error for {tool_name}: {e}", "is_error": True, "guard_blocked": True}
            if result.verdict.value == "blocked":
                return {
                    "error": f"Filesystem guard blocked {tool_name} on '{raw_path}': {result.reason}",
                    "is_error": True,
                    "guard_blocked": True,
                    "guard_result": result.to_dict(),
                }
        return None

    def _check_network_for_tool(self, tool_name: str, arguments: dict[str, Any]) -> dict[str, Any] | None:
        """Return a guarded error dict if the tool would egress to a disallowed URL; otherwise None."""
        keys = self._NETWORK_MCP_TOOL_PATTERNS.get(tool_name)
        if not keys:
            return None

        for key in keys:
            raw_url = arguments.get(key)
            if not raw_url or not isinstance(raw_url, str):
                continue
            try:
                result = self._network_guard.check_url(raw_url)
            except Exception as e:
                return {"error": f"Network guard error for {tool_name}: {e}", "is_error": True, "guard_blocked": True}
            if result.verdict.value == "blocked":
                return {
                    "error": f"Network guard blocked {tool_name} on '{raw_url}': {result.reason}",
                    "is_error": True,
                    "guard_blocked": True,
                    "guard_result": result.to_dict(),
                }
            if result.verdict.value == "escalate":
                return {
                    "error": f"Network guard escalated {tool_name} on '{raw_url}': {result.reason}",
                    "is_error": True,
                    "guard_blocked": True,
                    "guard_result": result.to_dict(),
                }
        return None

    def _check_safety_for_tool(self, tool_name: str, arguments: dict[str, Any]) -> dict[str, Any] | None:
        """Return a guarded error dict if the tool or its inner command trigger the safety chain."""
        if isinstance(arguments, dict) and isinstance(arguments.get("command"), str):
            safety_result = self._safety_chain.check_command(arguments["command"])
        else:
            safety_result = self._safety_chain.check_command(tool_name, arguments)
        if safety_result.verdict in (SafetyVerdict.ABORT_AND_REPORT, SafetyVerdict.RESUME_WITH_LIMITS, SafetyVerdict.ESCALATE_TO_HUMAN):
            reason = safety_result.triggered_rules[0].rule.description if safety_result.triggered_rules else "deterministic safety guardrail"
            return {
                "error": f"Safety chain blocked {tool_name}: {reason}",
                "is_error": True,
                "guard_blocked": True,
                "safety_result": safety_result,
            }
        return None

    def get_mcp_categories(self) -> list[str]:
        """Return MCP category metadata without loading servers.

        Filters out the Figma category if Figma is not configured so the planner
        does not waste tokens on tools that cannot execute.
        """
        if not self.mcp_enabled:
            return []
        categories = self._mcp_gateway.categories()
        if "figma" in categories and not self.figma_available:
            categories = [c for c in categories if c != "figma"]
        return categories

    async def run(self, user_input: str, session_id: str | None = None,
                  max_iterations: int = 5) -> PipelineResult:
        self._max_iterations = max_iterations
        session_id = session_id or uuid.uuid4().hex
        t_start = time.perf_counter()
        self._t_start = t_start
        metrics = SessionMetrics(session_id=session_id)
        trace: list[IterationTrace] = []
        audit_anchor = uuid.uuid4().hex
        self._current_audit_anchor = audit_anchor

        await self.bus.start()

        try:
            self._audit_logger.log_pipeline_start(session_id, audit_anchor, user_input)
            self.state.create(f"session:{session_id}", {
                "user_input": user_input,
                "status": PipelineStatus.RUNNING.value,
                "started_at": t_start,
            }, scope="session")

            await self._publish_progress("phase.start", {"phase": "session_init", "session_id": session_id})

            if self._coverage_mode:
                await self._run_coverage_preflight(user_input, session_id, trace, metrics)

            # Phase 0: Deterministic safety chain pre-check (hard guardrail)
            deterministic_safety = self._safety_chain.pre_check(user_input)
            if deterministic_safety.verdict != SafetyVerdict.PROCEED:
                metrics.safety_checks_failed += 1
                reason = deterministic_safety.triggered_rules[0].rule.description if deterministic_safety.triggered_rules else "deterministic safety guardrail"
                return await self._finalize_and_return(
                    user_input,
                    f"Request blocked by deterministic safety guardrail: {reason}",
                    TerminationStatus.FAILURE if deterministic_safety.verdict == SafetyVerdict.ABORT_AND_REPORT else TerminationStatus.ESCALATED_HUMAN,
                    metrics, audit_anchor, trace, session_id,
                )
            metrics.safety_checks_passed += 1

            # Phase 1: Safety pre-check (LLM-agent based)
            safety_passed = await self._run_safety_pre_check(user_input, session_id, trace, metrics)
            if not safety_passed:
                return await self._finalize_and_return(
                    user_input,
                    "Request blocked by safety pre-check.",
                    TerminationStatus.ESCALATED_HUMAN,
                    metrics, audit_anchor, trace, session_id,
                )

            await self._publish_progress("phase.end", {"phase": "safety_pre_check", "session_id": session_id})

            # Phase 2: Design intake & optional full-pipeline short-circuit
            await self._publish_progress("phase.start", {"phase": "design_intake", "session_id": session_id})
            intake_result = await self._run_design_intake(user_input, session_id, trace, metrics)
            await self._publish_progress("phase.end", {"phase": "design_intake", "session_id": session_id})

            design_descriptor: dict[str, Any] | None = None
            if intake_result:
                design_descriptor = intake_result.get("design_descriptor")
                request_type = intake_result.get("request_type")

                # Client-order branch: run PM-style brief agent and possibly interview the user.
                if request_type == "client_order":
                    brief_result = await self._run_client_brief(
                        user_input, session_id, trace, metrics, design_descriptor,
                    )
                    design_descriptor = brief_result.get("design_descriptor")
                    if brief_result.get("short_circuit"):
                        final_response = brief_result.get("response") or "Please provide more details so I can prepare the brief."
                        metrics.time_elapsed_ms = (time.perf_counter() - t_start) * 1000
                        self.state.update(f"session:{session_id}", {
                            "status": PipelineStatus.COMPLETED.value,
                            "completed_at": time.time(),
                            "client_brief_pending": True,
                        }, scope="session")
                        return await self._finalize_and_return(
                            user_input, final_response, TerminationStatus.SUCCESS,
                            metrics, audit_anchor, trace, session_id,
                        )

            if design_descriptor and self.mcp_enabled and self.figma_available:
                output_mode = design_descriptor.get("output_mode", "both")
                if output_mode in ("full_code", "both"):
                    pipeline_result = await self._run_design_pipeline(design_descriptor, session_id)
                    if pipeline_result and not pipeline_result.get("is_error"):
                        final_response = self._format_design_pipeline_result(design_descriptor, pipeline_result)
                        await self._run_safety_post_check(final_response, session_id, trace, metrics)
                        await self._run_mutual_check(final_response, session_id, trace, metrics)
                        metrics.time_elapsed_ms = (time.perf_counter() - t_start) * 1000
                        self.state.update(f"session:{session_id}", {
                            "status": PipelineStatus.COMPLETED.value,
                            "completed_at": time.time(),
                        }, scope="session")
                        return await self._finalize_and_return(
                            user_input, final_response, TerminationStatus.SUCCESS,
                            metrics, audit_anchor, trace, session_id,
                        )

            # Phase 3: Scope + spec approval gate
            parsed_request = (intake_result or {}).get("parsed_request")
            client_brief = None
            task_scope_result = await self._invoke_agent(
                "tooll_subagents/planning/task_scoping_agent.md",
                {
                    "raw_request": user_input,
                    "parsed_request": parsed_request,
                    "client_brief": client_brief,
                    "design_descriptor": design_descriptor,
                    "project_rules": self._project_rules,
                    "session_id": session_id,
                },
                trace, "scope", metrics,
            )
            task_scope: dict[str, Any] = (task_scope_result.parsed if task_scope_result and task_scope_result.parsed else {})
            if not task_scope:
                # Fallback to safe large scope if scoping agent fails
                task_scope = {"scope_size": "large", "needs_spec": True, "interview_depth": "full"}

            spec_status = "approved" if not task_scope.get("needs_spec") else "missing"
            approved_spec: dict[str, Any] | None = None
            if task_scope.get("needs_spec"):
                # Check for a pre-approved spec supplied by the caller in state (API/batch mode)
                approved_spec = self.state.read(f"session:{session_id}:approved_spec", scope="session").value
                if approved_spec:
                    spec_status = "approved"
                else:
                    # In interactive mode, invoke spec_approval_gate. In tests the mock auto-approves;
                    # in production this would pause for explicit user approval.
                    spec_result = await self._invoke_agent(
                        "tooll_subagents/planning/spec_approval_gate.md",
                        {
                            "raw_request": user_input,
                            "task_scope": task_scope,
                            "parsed_request": parsed_request,
                            "client_brief": client_brief,
                            "design_descriptor": design_descriptor,
                            "project_rules": self._project_rules,
                            "session_id": session_id,
                        },
                        trace, "spec_approval", metrics,
                    )
                    if spec_result and spec_result.parsed:
                        spec_status = spec_result.parsed.get("spec_status", "missing")
                        approved_spec = spec_result.parsed.get("approved_spec")
                        if spec_status != "approved":
                            response_text = spec_result.parsed.get("response") or "Approved spec is required before sub-agents can run."
                            return await self._finalize_and_return(
                                user_input, response_text, TerminationStatus.SUCCESS,
                                metrics, audit_anchor, trace, session_id,
                            )

            # Spec lock enforcement before planning or sub-agent dispatch
            spec_lock_result = await self._invoke_agent(
                "control/spec_lock.md",
                {
                    "session_id": session_id,
                    "spec_status": spec_status,
                    "approved_spec": approved_spec,
                    "task_scope": task_scope,
                    "plan": {},
                    "request_source": "cli",
                },
                trace, "spec_lock", metrics,
            )
            if spec_lock_result and spec_lock_result.parsed:
                if spec_lock_result.parsed.get("lock_status") == "locked":
                    reason = spec_lock_result.parsed.get("reason", "Spec lock is closed.")
                    return await self._finalize_and_return(
                        user_input,
                        f"Approved spec is required before sub-agents can run. {reason}",
                        TerminationStatus.SUCCESS,
                        metrics, audit_anchor, trace, session_id,
                    )

            # Materialize approved spec as a durable workspace artifact
            if approved_spec and spec_status == "approved":
                spec_path = self._write_spec_artifact(session_id, approved_spec)
                if spec_path:
                    approved_spec["spec_artifact_path"] = str(spec_path)

            # Phase 3: Plan
            await self._publish_progress("phase.start", {"phase": "planning", "session_id": session_id})
            plan = await self._run_planning(user_input, session_id, trace, metrics,
                                            design_descriptor=design_descriptor,
                                            approved_spec=approved_spec)
            await self._publish_progress("phase.end", {"phase": "planning", "session_id": session_id})

            # Phase 3: Resource checkpoint before ReAct loop
            resource_check = self._resource_monitor.check()
            self._last_resource_state = {
                "level": resource_check.level.value,
                "reason": resource_check.reason,
                "snapshot": {
                    "cpu_percent": resource_check.snapshot.cpu_percent,
                    "memory_percent": resource_check.snapshot.memory_percent,
                    "disk_percent": resource_check.snapshot.disk_percent,
                    "timestamp": resource_check.snapshot.timestamp,
                },
                "thresholds": resource_check.thresholds,
            }
            if resource_check.level == ResourceLevel.CRITICAL:
                return await self._finalize_and_return(
                    user_input,
                    f"Pipeline aborted: resource critical — {resource_check.reason}",
                    TerminationStatus.FAILURE,
                    metrics, audit_anchor, trace, session_id,
                )

            # Phase 4: ReAct loop with conditional edges
            transition_manager = PhaseTransitionManager(max_iterations=max_iterations)
            state: dict[str, Any] = {
                "plan": plan,
                "user_input": user_input,
                "session_id": session_id,
                "iteration": 0,
            }
            current_phase = "execution"
            result_text = ""

            while current_phase != "result":
                # Handle replanning requests from conditional edges
                if current_phase == "planning":
                    await self._publish_progress("phase.start", {"phase": "planning", "session_id": session_id})
                    plan = await self._run_planning(user_input, session_id, trace, metrics)
                    state["plan"] = plan
                    await self._publish_progress("phase.end", {"phase": "planning", "session_id": session_id})
                    # After replanning, always move to execution unless overridden
                    current_phase = "execution"
                    continue

                if current_phase == "execution":
                    state["iteration"] += 1
                    metrics.iterations = state["iteration"]

                    # Per-iteration resource guard: abort before heavy work if resources are critical
                    resource_check = self._resource_monitor.check()
                    self._last_resource_state = {
                        "level": resource_check.level.value,
                        "reason": resource_check.reason,
                        "snapshot": {
                            "cpu_percent": resource_check.snapshot.cpu_percent,
                            "memory_percent": resource_check.snapshot.memory_percent,
                            "disk_percent": resource_check.snapshot.disk_percent,
                            "timestamp": resource_check.snapshot.timestamp,
                        },
                        "thresholds": resource_check.thresholds,
                    }
                    if resource_check.level == ResourceLevel.CRITICAL:
                        return await self._finalize_and_return(
                            user_input,
                            f"Pipeline aborted at iteration {state['iteration']}: resource critical — {resource_check.reason}",
                            TerminationStatus.FAILURE,
                            metrics, audit_anchor, trace, session_id,
                        )

                if state["iteration"] > max_iterations:
                    return await self._finalize_and_return(
                        user_input, result_text or "Max iterations reached.",
                        TerminationStatus.PARTIAL, metrics, audit_anchor, trace, session_id,
                    )

                await self._publish_progress("phase.start", {"phase": current_phase, "session_id": session_id})
                await self._run_phase(current_phase, state, trace, metrics)
                await self._publish_progress("phase.end", {"phase": current_phase, "session_id": session_id})

                transition = transition_manager.next_phase(current_phase, state, state["iteration"])

                # Safety override: hard-terminate to result with a specific status
                if transition.safety_override:
                    return await self._finalize_and_return(
                        user_input,
                        state.get("result", transition.reason),
                        transition.safety_override,
                        metrics, audit_anchor, trace, session_id,
                    )

                # Preserve result text if we are about to finish successfully
                if transition.next_phase == "result":
                    result_text = state.get("result", state.get("observation", {}).get("result", transition.reason))

                current_phase = transition.next_phase

            # Result-layer formatting (lightweight; all result agents are reachable in coverage mode).
            await self._run_result(state, trace, metrics)
            result_text = state.get("result", result_text)

            # Phase 4: Deterministic safety chain post-check (hard guardrail)
            post_safety = self._safety_chain.post_check(result_text)
            if post_safety.verdict == SafetyVerdict.ABORT_AND_REPORT:
                metrics.safety_checks_failed += 1
                reason = post_safety.triggered_rules[0].rule.description if post_safety.triggered_rules else "output safety guardrail"
                return await self._finalize_and_return(
                    user_input,
                    f"Output blocked by deterministic safety guardrail: {reason}",
                    TerminationStatus.FAILURE,
                    metrics, audit_anchor, trace, session_id,
                )
            metrics.safety_checks_passed += 1

            # Phase 5: Safety post-check (LLM-agent based)
            await self._run_safety_post_check(result_text, session_id, trace, metrics)

            # Phase 6: Final mutual check
            await self._run_mutual_check(result_text, session_id, trace, metrics)

            metrics.time_elapsed_ms = (time.perf_counter() - t_start) * 1000
            self.state.update(f"session:{session_id}", {
                "status": PipelineStatus.COMPLETED.value,
                "completed_at": time.time(),
            }, scope="session")

            return await self._finalize_and_return(
                user_input, result_text, TerminationStatus.SUCCESS,
                metrics, audit_anchor, trace, session_id,
            )

        except Exception as e:
            metrics.time_elapsed_ms = (time.perf_counter() - t_start) * 1000
            return await self._finalize_and_return(
                user_input, f"Pipeline failed: {e}", TerminationStatus.FAILURE,
                metrics, audit_anchor, trace, session_id,
            )
        finally:
            self._current_audit_anchor = None
            await self.bus.stop()

    async def _finalize_and_return(self, user_input: str, final_response: str,
                                   termination_status: TerminationStatus,
                                   metrics: SessionMetrics, audit_anchor: str,
                                   trace: list[IterationTrace], session_id: str) -> PipelineResult:
        if metrics.time_elapsed_ms <= 0:
            t_start = getattr(self, "_t_start", None)
            if t_start is not None:
                metrics.time_elapsed_ms = (time.perf_counter() - t_start) * 1000
            else:
                metrics.time_elapsed_ms = 0.0
        self._audit_logger.log_pipeline_end(
            session_id, audit_anchor, termination_status.value,
            {
                "iterations": metrics.iterations,
                "tools_used": metrics.tools_used,
                "safety_checks_passed": metrics.safety_checks_passed,
                "safety_checks_failed": metrics.safety_checks_failed,
                "time_elapsed_ms": round(metrics.time_elapsed_ms, 2),
            },
        )
        self._audit_logger.close()
        return PipelineResult(
            final_response=final_response,
            termination_status=termination_status,
            session_metrics=metrics,
            audit_anchor=audit_anchor,
            trace=trace,
        )

    async def _run_safety_pre_check(self, user_input: str, session_id: str,
                                    trace: list[IterationTrace], metrics: SessionMetrics) -> bool:
        context: dict[str, Any] = {
            "raw_user_input": user_input,
            "session_id": session_id,
            "project_rules": self._project_rules,
        }

        for agent_path in self.SAFETY_AGENTS:
            result = await self._invoke_agent(agent_path, context, trace, "safety_pre_check", metrics)
            if result and result.parsed:
                parsed = result.parsed
                blocked = (
                    parsed.get("blocked") is True
                    or parsed.get("status") == "blocked"
                    or parsed.get("verdict") == "block"
                    or parsed.get("review_status") == "rejected"
                    or parsed.get("compliance_status") in ("major_violation", "blocked")
                    or parsed.get("execution_recommendation") == "block"
                    or parsed.get("recommendation") == "escalate"
                    or parsed.get("action") == "block"
                )
                if blocked:
                    metrics.safety_checks_failed += 1
                    self._audit_logger.log_safety_blocked(
                        agent_path, session_id, self._current_audit_anchor or session_id,
                        str(parsed.get("reason", parsed.get("block_reason", "safety pre-check blocked"))),
                    )
                    return False
                metrics.safety_checks_passed += 1
                context.update(parsed)
        return True

    async def _run_design_intake(self, user_input: str, session_id: str,
                                 trace: list[IterationTrace], metrics: SessionMetrics) -> dict[str, Any] | None:
        """Classify request via design_intake.md and return intake result if design/client request."""
        result = await self._invoke_agent(
            "tooll_subagents/user/design_intake.md",
            {
                "raw_request": user_input,
                "source_channel": "cli",
                "session_id": session_id,
                "priority_hint": "normal",
                "project_rules": self._project_rules,
            },
            trace, "design_intake", metrics,
        )
        if not result or not result.parsed:
            return None
        request_type = result.parsed.get("request_type")
        parsed_request = result.parsed.get("parsed_request")
        design_descriptor = result.parsed.get("design_descriptor")
        return {
            "request_type": request_type,
            "parsed_request": parsed_request,
            "design_descriptor": design_descriptor,
        }

    async def _run_client_brief(self, user_input: str, session_id: str,
                                trace: list[IterationTrace], metrics: SessionMetrics,
                                design_descriptor: dict[str, Any] | None) -> dict[str, Any]:
        """Run PM-style client brief intake and return enriched descriptor + control flags."""
        result = await self._invoke_agent(
            "tooll_subagents/user/client_brief_agent.md",
            {
                "raw_request": user_input,
                "source_channel": "cli",
                "session_id": session_id,
                "project_rules": self._project_rules,
                "design_descriptor": design_descriptor,
            },
            trace, "design_intake", metrics,
        )
        if not result or not result.parsed:
            return {"design_descriptor": design_descriptor, "short_circuit": False}
        parsed = result.parsed
        client_brief = parsed.get("client_brief")
        next_action = (client_brief or {}).get("next_action") or parsed.get("next_action")
        questions = (client_brief or {}).get("questions", []) or parsed.get("questions", [])
        design_descriptor = parsed.get("design_descriptor") or design_descriptor
        if client_brief and design_descriptor:
            metadata = design_descriptor.get("metadata") or {}
            metadata["client_brief"] = client_brief
            design_descriptor["metadata"] = metadata
        return {
            "design_descriptor": design_descriptor,
            "client_brief": client_brief,
            "next_action": next_action,
            "questions": questions,
            "short_circuit": next_action == "ask_user",
            "response": "\n".join(questions) if next_action == "ask_user" else "",
        }

    def _write_spec_artifact(self, session_id: str, approved_spec: dict[str, Any]) -> Path | None:
        """Materialize an approved spec as a durable markdown artifact.

        The file is written inside `.agent_loop/specs/` so it is covered by the
        workspace filesystem guard and remains auditable outside session state.
        """
        if not approved_spec:
            return None
        specs_dir = Path(self.workspace) / ".agent_loop" / "specs"
        try:
            specs_dir.mkdir(parents=True, exist_ok=True)
        except Exception:
            return None
        spec_path = specs_dir / f"{session_id}_spec.md"
        now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        frontmatter = {
            "session_id": session_id,
            "approval_token": approved_spec.get("approval_token") or "",
            "approved_at": now,
            "scope_size": approved_spec.get("scope_size", "unknown"),
            "automation_mode": approved_spec.get("automation_mode", "none"),
        }
        lines = ["---"]
        for key, value in frontmatter.items():
            lines.append(f"{key}: {value}")
        lines.extend(["---", ""])

        def _section(title: str, content: Any) -> None:
            lines.append(f"## {title}")
            if isinstance(content, list):
                for item in content:
                    lines.append(f"- {item}")
            elif isinstance(content, dict):
                for key, value in content.items():
                    lines.append(f"- **{key}**: {value}")
            elif content:
                lines.append(str(content))
            else:
                lines.append("_not specified_")
            lines.append("")

        _section("Goal", approved_spec.get("goal"))
        _section("Scope", approved_spec.get("scope"))
        _section("Key decisions", approved_spec.get("key_decisions"))
        _section("Deliverables", approved_spec.get("deliverables"))
        _section("Success criteria", approved_spec.get("success_criteria"))
        _section("Human zones", approved_spec.get("human_zones"))
        _section("Assumptions", approved_spec.get("assumptions"))
        _section("Verification plan", approved_spec.get("verification_plan"))

        try:
            spec_path.write_text("\n".join(lines), encoding="utf-8")
            self._audit_logger.log_agent_completed(
                "spec_artifact_writer", session_id,
                self._current_audit_anchor or session_id,
                {"spec_path": str(spec_path)}, 0.0,
            )
            return spec_path
        except Exception as e:
            self._audit_logger.log_agent_failed(
                "spec_artifact_writer", session_id,
                self._current_audit_anchor or session_id, str(e),
            )
            return None

    async def _run_design_pipeline(self, design_descriptor: dict[str, Any],
                                   session_id: str) -> dict[str, Any]:
        """Trigger the full Figma-to-code pipeline via MCP figma_run_pipeline."""
        source_value = design_descriptor.get("source_value", "")
        backend_spec = design_descriptor.get("backend_spec") or {}
        image_enrichment = design_descriptor.get("image_enrichment") or {}
        dry_run = bool(design_descriptor.get("dry_run", False))
        args: dict[str, Any] = {
            "output_name": session_id[:8],
            "dry_run": dry_run,
            "figma_url": source_value if design_descriptor.get("design_source") == "figma_url" else "",
        }
        file_key = self._extract_figma_file_key(source_value)
        if file_key:
            args["file_key"] = file_key
        if design_descriptor.get("target_scope") == "single_section":
            node_id = self._extract_figma_node_id(source_value)
            if node_id:
                args["node_id"] = node_id
        if backend_spec:
            spec_type = backend_spec.get("spec_type")
            spec_path = backend_spec.get("spec_path", "")
            if spec_type == "openapi":
                args["openapi"] = spec_path
            elif spec_type == "prisma":
                args["prisma"] = spec_path
            else:
                args["backend_spec_text"] = spec_path
        if image_enrichment.get("enabled"):
            args["enable_image_enrichment"] = True
            args["image_provider"] = image_enrichment.get("provider", "unsplash")
            if image_enrichment.get("api_key"):
                args["image_provider_api_key"] = image_enrichment["api_key"]
            if image_enrichment.get("output_dir"):
                args["image_enrichment_output_dir"] = image_enrichment["output_dir"]
            if image_enrichment.get("max_images"):
                args["image_enrichment_max_images"] = image_enrichment["max_images"]
        return await self.execute_mcp_tool("figma_run_pipeline", args)

    def _extract_figma_file_key(self, source_value: str) -> str:
        import re
        match = re.search(r"figma\.com/(?:file|design)/([a-zA-Z0-9_-]+)", source_value)
        return match.group(1) if match else ""

    def _extract_figma_node_id(self, source_value: str) -> str:
        import re
        match = re.search(r"node-id=([0-9-:]+)", source_value)
        return match.group(1).replace("-", ":") if match else ""

    def _get_agent(self, path: str) -> AgentSpec:
        if path not in self._agent_cache:
            self._agent_cache[path] = self.loader.load_agent(path)
        return self._agent_cache[path]

    def _format_design_pipeline_result(self, design_descriptor: dict[str, Any],
                                       pipeline_result: dict[str, Any]) -> str:
        source = design_descriptor.get("source_value", "")
        mode = design_descriptor.get("output_mode", "full_code")
        result = pipeline_result.get("result", pipeline_result)
        status = result.get("status", "unknown")
        summary = f"Design pipeline triggered for {source} (mode={mode}).\nStatus: {status}.\n"
        if result.get("returncode") is not None:
            summary += f"Return code: {result['returncode']}.\n"
        if result.get("stdout"):
            summary += f"\nOutput:\n{result['stdout'][:2000]}"
        if result.get("stderr"):
            summary += f"\nErrors:\n{result['stderr'][:1000]}"
        return summary

    def _planning_flags(self, plan: dict[str, Any]) -> dict[str, bool]:
        """Extract planner flags; in coverage mode all conditional groups run."""
        if self._coverage_mode:
            return {flag: True for flag in PLANNING_FLAG_GROUPS}
        flags: dict[str, bool] = {}
        for flag in PLANNING_FLAG_GROUPS:
            value = plan.get(flag)
            flags[flag] = bool(value) and value not in ("false", "no", "0")
        return flags

    async def _run_conditional_agents(self, groups: list[str], inputs: dict[str, Any],
                                      trace: list[IterationTrace], metrics: SessionMetrics,
                                      phase: str) -> None:
        """Invoke all agents in the named phase groups, merging outputs into inputs."""
        for group in groups:
            for agent_path in phase_dispatch(group):
                if agent_path in self.EXECUTION_CORE and phase == "execution":
                    # Already handled in _run_execution core list.
                    continue
                result = await self._invoke_agent(agent_path, inputs, trace, phase, metrics)
                if result and result.parsed:
                    inputs.update(result.parsed)

    async def _run_planning(self, user_input: str, session_id: str,
                            trace: list[IterationTrace], metrics: SessionMetrics,
                            design_descriptor: dict[str, Any] | None = None,
                            approved_spec: dict[str, Any] | None = None) -> dict[str, Any]:
        client_brief = None
        if design_descriptor:
            metadata = design_descriptor.get("metadata") or {}
            client_brief = metadata.get("client_brief")

        plan = {
            "user_input": user_input,
            "session_id": session_id,
            "project_rules": self._project_rules,
            "mcp_categories": self.get_mcp_categories() if self.mcp_enabled else [],
            "design_descriptor": design_descriptor,
            "client_brief": client_brief,
            "approved_spec": approved_spec,
            "needs_copywriting": bool(client_brief),
            "needs_estimation": bool(client_brief),
            "needs_starter": bool(client_brief),
        }
        for agent_path in self.FLOW_SEQUENCE:
            result = await self._invoke_agent(agent_path, plan, trace, "planning", metrics)
            if result and result.parsed:
                plan.update(result.parsed)

        # Run general planning reviewers unconditionally.
        await self._run_conditional_agents(["planning_general"], plan, trace, metrics, "planning")

        # Run module-specific planners only when flagged by tool_plan_selection or in coverage mode.
        flags = self._planning_flags(plan)
        groups = conditional_groups_for_flags(flags)
        if groups:
            await self._run_conditional_agents(groups, plan, trace, metrics, "planning")

        # Spec-compliance: if a plan deviates from approved_spec.scope, mark it for re-approval.
        if approved_spec:
            aligned, misaligned, reason = self._is_plan_aligned_with_spec(plan, approved_spec)
            plan["spec_scope_aligned"] = aligned
            plan["spec_misaligned_tasks"] = misaligned
            plan["spec_alignment_reason"] = reason
            if not aligned:
                self._audit_logger.log_safety_blocked(
                    "plan_spec_alignment", session_id, self._current_audit_anchor or session_id,
                    reason,
                )
        return plan

    def _is_plan_aligned_with_spec(
        self, plan: dict[str, Any], approved_spec: dict[str, Any],
    ) -> tuple[bool, list[str], str]:
        """Compare the generated plan against the approved spec scope.

        Returns (aligned, misaligned_tasks, reason). A plan is aligned when every
        planned task or deliverable is covered by the approved spec scope and
        no approved deliverable is completely missing from the plan.
        """
        approved_scope = approved_spec.get("scope", [])
        if not approved_scope:
            return True, [], "no approved scope to compare"

        approved_deliverables = {d.lower().strip() for d in approved_spec.get("deliverables", []) if isinstance(d, str)}
        approved_scope_items = {s.lower().strip() for s in approved_scope if isinstance(s, str)}
        approved_keywords = approved_scope_items | approved_deliverables

        task_graph = plan.get("task_graph") or plan.get("tasks") or {}
        tasks: list[str] = []
        if isinstance(task_graph, list):
            tasks = [str(t) for t in task_graph]
        elif isinstance(task_graph, dict):
            for value in task_graph.values():
                if isinstance(value, list):
                    tasks.extend(str(v) for v in value)
                elif isinstance(value, dict):
                    tasks.extend(str(v) for v in value.values() if not isinstance(v, dict))
                else:
                    tasks.append(str(value))

        # If task_graph is empty but the plan carries module flags, derive tasks from flags.
        if not tasks:
            for flag, active in (plan.get("flags") or {}).items():
                if active and isinstance(active, bool):
                    tasks.append(flag.replace("needs_", "").replace("_", " "))

        misaligned: list[str] = []
        for task in tasks:
            task_lower = task.lower().strip()
            if not task_lower:
                continue
            if any(keyword in task_lower or task_lower in keyword for keyword in approved_keywords):
                continue
            misaligned.append(task)

        # Detect missing approved deliverables if the plan has explicit tasks/flags.
        if tasks:
            planned_keywords: set[str] = set()
            for task in tasks:
                task_lower = task.lower().strip()
                planned_keywords.update(task_lower.split())
                planned_keywords.add(task_lower)
            missing_deliverables = [
                d for d in approved_spec.get("deliverables", [])
                if isinstance(d, str) and d.lower().strip() not in planned_keywords
                and not any(word in planned_keywords for word in d.lower().strip().split())
            ]
            if missing_deliverables:
                if misaligned:
                    reason = f"plan contains {len(misaligned)} tasks outside approved scope and omits approved deliverables: {missing_deliverables[:3]}"
                else:
                    reason = f"plan omits approved deliverables: {missing_deliverables[:3]}"
                return False, misaligned, reason

        if misaligned:
            return False, misaligned, f"plan contains tasks outside approved scope: {misaligned[:3]}"
        return True, [], "plan aligns with approved spec scope"


    async def _run_phase(self, phase: str, state: dict[str, Any],
                         trace: list[IterationTrace], metrics: SessionMetrics) -> None:
        """Execute one ReAct phase and store results in the shared state."""
        if phase == "execution":
            await self._run_execution(state, trace, metrics)
        elif phase == "observability":
            await self._run_observation(state, trace, metrics)
        elif phase == "self_correction":
            await self._run_validation(state, trace, metrics)
            await self._run_termination_decision(state, trace, metrics)

    def _execution_agent_enabled(self, agent_path: str, flags: dict[str, bool]) -> bool:
        """Decide whether a conditional execution agent should run."""
        if self._coverage_mode:
            return True
        if agent_path in (
            "tooll_subagents/execution/human_approval.md",
            "tooll_subagents/execution/action_logging.md",
        ):
            return True
        stem = Path(agent_path).stem
        module_flags = {
            "i18n": "needs_i18n",
            "analytics": "needs_analytics",
            "cookie_consent": "needs_analytics",
            "auth": "needs_auth",
            "cms": "needs_cms",
            "accessibility": "needs_accessibility",
            "pwa": "needs_pwa",
            "design_token_docs": "needs_design_token_docs",
            "multi_page": "needs_multi_page",
            "storybook": "needs_storybook",
            "deploy": "needs_deploy",
            "preview": "needs_preview",
        }
        for prefix, flag in module_flags.items():
            if stem.startswith(prefix) and flags.get(flag):
                return True
        return False

    async def _run_execution(self, state: dict[str, Any],
                             trace: list[IterationTrace],
                             metrics: SessionMetrics) -> None:
        result: dict[str, Any] = {
            "plan": state.get("plan"),
            "user_input": state.get("user_input"),
            "iteration": state.get("iteration"),
            "session_id": state.get("session_id"),
            "mcp_categories": self.get_mcp_categories() if self.mcp_enabled else [],
        }
        for agent_path in self.EXECUTION_CORE:
            llm_result = await self._invoke_agent(agent_path, result, trace, "execution", metrics)
            if llm_result and llm_result.parsed:
                result.update(llm_result.parsed)

        flags = self._planning_flags(state.get("plan", {}))
        for agent_path in phase_dispatch("execution_conditional"):
            if not self._execution_agent_enabled(agent_path, flags):
                continue
            llm_result = await self._invoke_agent(agent_path, result, trace, "execution", metrics)
            if llm_result and llm_result.parsed:
                result.update(llm_result.parsed)

        # If the planner selected an MCP tool, execute it directly here.
        tool_call = result.get("tool_call") or result.get("tool")
        tool_name = tool_call.get("name", "") if isinstance(tool_call, dict) else ""
        if tool_name and self._is_registered_mcp_tool(tool_name):
            tool_output = await self.execute_mcp_tool(
                tool_name, tool_call.get("arguments", {})
            )
            result["tool_output"] = tool_output
            result["tool_result"] = tool_output.get("result")
            result["success"] = not tool_output.get("result", {}).get("is_error", False)
            if "result" in tool_output.get("result", {}):
                result["result"] = tool_output["result"]["result"]

        state["execution"] = result
        if "result" in result:
            state["result"] = result["result"]

    def _is_registered_mcp_tool(self, tool_name: str) -> bool:
        """Return True if tool_name is registered with an available MCP server."""
        if not self.mcp_enabled:
            return False
        registry = getattr(self._mcp_gateway, "_registry", None)
        if registry is None:
            return False
        return registry.find_tool(tool_name) is not None

    async def _run_observation(self, state: dict[str, Any],
                               trace: list[IterationTrace],
                               metrics: SessionMetrics) -> None:
        exec_result = state.get("execution", {})
        result: dict[str, Any] = dict(exec_result)
        for agent_path in self.OBSERVABILITY_CORE:
            llm_result = await self._invoke_agent(agent_path, result, trace, "observation", metrics)
            if llm_result and llm_result.parsed:
                result.update(llm_result.parsed)
        state["observation"] = result
        if "result" in result:
            state["result"] = result["result"]
        await self._run_skill_automation(state, trace, metrics)

    async def _run_skill_automation(self, state: dict[str, Any],
                                    trace: list[IterationTrace],
                                    metrics: SessionMetrics) -> None:
        """Route source-detector candidates through value analysis and surface proposals."""
        observation = state.get("observation", {})
        candidates = observation.get("source_candidates", [])
        recommendation = observation.get("recommendation", "ignore")
        if not candidates or recommendation != "propose_value_analysis":
            if observation.get("needs_update"):
                state["graphify_recommendation"] = {
                    "needs_update": True,
                    "command": observation.get("command"),
                    "reason": observation.get("reason"),
                    "warning_large_corpus": observation.get("warning_large_corpus", False),
                }
            return

        existing_skills = [
            str(p.parent.name)
            for p in sorted(Path(self.workspace).glob(".claude/skills/*/SKILL.md"))
        ]
        enriched: list[dict[str, Any]] = []
        for candidate in candidates:
            analysis = await self._invoke_agent(
                "tooll_subagents/planning/skill_value_analyst.md",
                {
                    "source_candidate": candidate,
                    "existing_skills": existing_skills,
                    "project_rules": self._project_rules,
                    "session_id": state.get("session_id", ""),
                },
                trace, "observation", metrics,
            )
            enriched_candidate = dict(candidate)
            if analysis and analysis.parsed:
                enriched_candidate.update(analysis.parsed)
            enriched.append(enriched_candidate)

        state["skill_automation_candidates"] = enriched
        state["graphify_recommendation"] = {
            "needs_update": bool(observation.get("needs_update")),
            "command": observation.get("command"),
            "reason": observation.get("reason"),
            "warning_large_corpus": observation.get("warning_large_corpus", False),
        }

    async def _run_self_correction_review(self, state: dict[str, Any],
                                          trace: list[IterationTrace],
                                          metrics: SessionMetrics) -> dict[str, Any]:
        """Run all self-correction validators except result_validation/recursion_or_termination."""
        review: dict[str, Any] = dict(state.get("observation", {}))
        # Provide the previous validation snapshot so cross-iteration guards (e.g. regression_guard)
        # can compare current artifacts against the prior ReAct cycle baseline.
        review["previous_validation"] = state.get("validation", {})
        review["iteration_count"] = state.get("iteration", 0)
        for agent_path in self.VALIDATION_CORE:
            if agent_path in (
                "tooll_subagents/self_correction/result_validation.md",
                "tooll_subagents/self_correction/recursion_or_termination.md",
            ):
                continue
            result = await self._invoke_agent(agent_path, review, trace, "validation", metrics)
            if result and result.parsed:
                review.update(result.parsed)
        return review

    async def _run_validation(self, state: dict[str, Any],
                              trace: list[IterationTrace], metrics: SessionMetrics) -> None:
        observation = state.get("observation", {})

        # Run all structured validators so every self-correction agent is reachable.
        review = await self._run_self_correction_review(state, trace, metrics)

        # Fast /goal evaluator: cheap critic checks whether the evidence satisfies the goal.
        goal_evaluation: dict[str, Any] | None = None
        if self._evaluator:
            try:
                evaluator_response = await self._evaluator.evaluate(
                    goal=state.get("user_input", ""),
                    artifacts=observation,
                    criteria=state.get("plan", {}).get("success_criteria"),
                )
                goal_evaluation = {
                    "verdict": {
                        "pass": evaluator_response.pass_,
                        "reason": evaluator_response.reason,
                        "confidence": evaluator_response.confidence,
                    },
                    "criteria_checklist": evaluator_response.criteria_checklist,
                }
            except Exception as e:
                goal_evaluation = {
                    "verdict": {"pass": False, "reason": f"Evaluator error: {e}", "confidence": 0.0},
                    "criteria_checklist": [],
                }

        result = await self._invoke_agent(
            "tooll_subagents/self_correction/result_validation.md",
            {
                "observation": observation,
                "self_correction_review": review,
                "original_request": state.get("user_input"),
                "goal_evaluation": goal_evaluation,
                "iteration_count": state.get("iteration", 0),
                "max_iterations": self._max_iterations,
                "plan": state.get("plan", {}),
            },
            trace, "validation", metrics,
        )
        validation: dict[str, Any] = dict(observation)
        if result and result.parsed:
            validation.update(result.parsed)
        validation["goal_evaluation"] = goal_evaluation
        state["validation"] = validation
        if "result" in validation:
            state["result"] = validation["result"]

    async def _run_termination_decision(self, state: dict[str, Any],
                                        trace: list[IterationTrace],
                                        metrics: SessionMetrics) -> None:
        validation = state.get("validation", {})
        result = await self._invoke_agent(
            "tooll_subagents/self_correction/recursion_or_termination.md",
            {"validation": validation, "iteration": state.get("iteration", 1), "max_iterations": self._max_iterations},
            trace, "self_correction", metrics,
        )
        if result and result.parsed:
            validation["decision"] = result.parsed.get("decision", result.parsed.get("next_action", "terminate_success"))
            if "next_phase_hint" in result.parsed:
                validation["next_phase_hint"] = result.parsed["next_phase_hint"]
            if "adjusted_plan" in result.parsed:
                state["adjusted_plan"] = result.parsed["adjusted_plan"]
        else:
            validation["decision"] = "terminate_success"
        state["validation"] = validation

    async def _run_result(self, state: dict[str, Any],
                          trace: list[IterationTrace],
                          metrics: SessionMetrics) -> None:
        """Invoke result-layer agents to format the final answer."""
        result_input: dict[str, Any] = {
            "result": state.get("result"),
            "validation": state.get("validation"),
            "user_input": state.get("user_input"),
            "session_id": state.get("session_id"),
            "source_candidates": state.get("skill_automation_candidates", []),
            "graphify_recommendation": state.get("graphify_recommendation"),
        }
        for agent_path in self.RESULT_AGENTS:
            llm_result = await self._invoke_agent(agent_path, result_input, trace, "result", metrics)
            if llm_result and llm_result.parsed:
                result_input.update(llm_result.parsed)
        if "result" in result_input:
            state["result"] = result_input["result"]

    async def _run_coverage_preflight(self, user_input: str, session_id: str,
                                      trace: list[IterationTrace], metrics: SessionMetrics) -> None:
        """Coverage-only path that exercises orchestrator/control/user agents not on the hot path."""
        inputs = {
            "user_input": user_input,
            "session_id": session_id,
            "project_rules": self._project_rules,
        }
        for agent_path in self.ORCHESTRATOR_AGENTS + self.CONTROL_AGENTS + phase_dispatch("user_intake"):
            if agent_path in self.FLOW_SEQUENCE or agent_path in self.SAFETY_AGENTS:
                continue
            result = await self._invoke_agent(agent_path, inputs, trace, "session_init", metrics)
            if result and result.parsed:
                inputs.update(result.parsed)

    async def _run_safety_post_check(self, result_text: str, session_id: str,
                                     trace: list[IterationTrace], metrics: SessionMetrics):
        for agent_path in self.SAFETY_POST_CHECK_AGENTS:
            await self._invoke_agent(agent_path, {"output": result_text}, trace, "safety_post_check", metrics)

    async def _run_mutual_check(self, result_text: str, session_id: str,
                                trace: list[IterationTrace], metrics: SessionMetrics):
        context: dict[str, Any] = {
            "result": result_text,
            "session_id": session_id,
            "iteration": metrics.iterations,
            "tools_used": metrics.tools_used,
            "time_elapsed_ms": metrics.time_elapsed_ms,
            "tokens_consumed": metrics.tokens_consumed,
        }
        for agent_path in self.MUTUAL_CHECK_AGENTS:
            await self._invoke_agent(agent_path, context, trace, "mutual_check", metrics)

    async def _invoke_agent(self, agent_path: str, inputs: dict[str, Any],
                            trace: list[IterationTrace], phase: str,
                            metrics: SessionMetrics | None = None) -> LLMResponse | None:
        t0 = time.perf_counter()
        session_id = inputs.get("session_id", "")
        audit_anchor = self._current_audit_anchor or session_id

        extra_context = self._system_context_for_phase(phase)
        self._audit_logger.log_agent_invoked(agent_path, session_id, audit_anchor, inputs)
        try:
            spec = self._get_agent(agent_path)
            result = await self.llm.execute(spec, inputs, extra_context=extra_context)
            latency = (time.perf_counter() - t0) * 1000
            trace.append(IterationTrace(
                iteration=len([t for t in trace if t.phase == phase]) + 1,
                phase=phase,
                agent_path=agent_path,
                inputs=inputs,
                outputs=result.parsed,
                latency_ms=latency,
                success=True,
            ))
            self._audit_logger.log_agent_completed(agent_path, session_id, audit_anchor, result.parsed, latency)
            iteration = inputs.get("iteration", metrics.iterations if metrics else 0)
            await self._publish_progress("agent.invoke", {
                "iteration": iteration, "phase": phase, "agent_path": agent_path,
                "session_id": session_id, "latency_ms": round(latency, 2), "success": True,
            })
            self._update_tui_from_trace(trace)
            return result
        except Exception as e:
            latency = (time.perf_counter() - t0) * 1000
            trace.append(IterationTrace(
                iteration=len([t for t in trace if t.phase == phase]) + 1,
                phase=phase,
                agent_path=agent_path,
                inputs=inputs,
                outputs=None,
                latency_ms=latency,
                success=False,
                error=str(e),
            ))
            self._audit_logger.log_agent_failed(agent_path, session_id, audit_anchor, str(e))
            iteration = inputs.get("iteration", metrics.iterations if metrics else 0)
            await self._publish_progress("agent.invoke", {
                "iteration": iteration, "phase": phase, "agent_path": agent_path,
                "session_id": session_id, "latency_ms": round(latency, 2), "success": False,
            })
            self._update_tui_from_trace(trace)
            return None

    async def _publish_progress(self, event_type: str, payload: dict[str, Any]):
        """Publish progress event for TUI and external observers."""
        msg = Message(
            message_type=MessageType.EVENT,
            topic=event_type,
            payload=payload,
            sender="pipeline_runner",
        )
        try:
            await self.bus.publish(msg)
        except Exception:
            pass

        # Emit a TUI dashboard frame on every phase boundary.
        if event_type in ("phase.start", "phase.end"):
            session_id = payload.get("session_id", "unknown")
            phase = payload.get("phase", "unknown")
            iteration = payload.get("iteration", 0)
            status = "running" if event_type == "phase.start" else "completed"
            dashboard_text = self._render_tui_dashboard(session_id, phase, iteration, status)
            try:
                await self.bus.publish(Message(
                    message_type=MessageType.EVENT,
                    topic="tui_dashboard.frame",
                    payload={
                        "session_id": session_id,
                        "phase": phase,
                        "iteration": iteration,
                        "status": status,
                        "dashboard_text": dashboard_text,
                    },
                    sender="pipeline_runner",
                ))
            except Exception:
                pass

    def _render_tui_dashboard(self, session_id: str, current_phase: str, iteration: int,
                              status: str = "running") -> str:
        """Render a live TUI dashboard frame from current pipeline state.

        Uses the most recent explicit resource checkpoint so rendering does not
        trigger additional resource sampling between guard points.
        """
        resource = self._last_resource_state or {
            "level": "unknown",
            "reason": "Resource checkpoint not reached yet",
            "snapshot": {},
        }
        agents: list[dict[str, Any]] = []
        for trace_item in getattr(self, "_last_trace_snapshot", []):
            agents.append({
                "name": Path(trace_item.agent_path).name.replace(".md", ""),
                "category": Path(trace_item.agent_path).parent.name if "/" in trace_item.agent_path else "",
                "duration_ms": round(trace_item.latency_ms, 1),
                "outcome": "pass" if trace_item.success else "fail",
            })

        safety_state = {
            "verdicts": [],
            "check_count": 0,
            "active_blocks": 0,
            "human_escalations": 0,
        }
        if self._safety_chain:
            for triggered in self._safety_chain.triggered_rules:
                verdict_str = "block" if triggered.severity == "aborted" else "warn"
                safety_state["verdicts"].append({
                    "verdict": verdict_str,
                    "rule": getattr(triggered.rule, "description", str(triggered.rule)) or "",
                })
            safety_state["check_count"] = len(safety_state["verdicts"])
            safety_state["active_blocks"] = sum(
                1 for v in safety_state["verdicts"] if v["verdict"] == "block"
            )

        pipeline_state = {
            "phase": current_phase,
            "iteration": iteration,
            "status": status,
            "agents": agents,
        }
        resource_state = {
            "cpu_level": resource.get("level", "normal"),
            "memory_level": resource.get("level", "normal"),
            "cpu_percent": resource.get("snapshot", {}).get("cpu_percent", 0.0) or 0.0,
            "memory_percent": resource.get("snapshot", {}).get("memory_percent", 0.0) or 0.0,
        }
        result = render_dashboard(
            session_id=session_id,
            pipeline_state=pipeline_state,
            resource_state=resource_state,
            safety_state=safety_state,
            start_time=getattr(self, "_t_start", 0.0),
            use_ansi=True,
        )
        return result.dashboard_text

    def _snapshot_trace(self, trace: list[IterationTrace]) -> None:
        self._last_trace_snapshot = list(trace[-10:])

    def _update_tui_from_trace(self, trace: list[IterationTrace]) -> None:
        self._snapshot_trace(trace)
