from __future__ import annotations

import asyncio
import importlib.util
import sys
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

from ..contracts.agent_spec import AgentSpec
from ..contracts.message import Message, MessageType
from .agent_loader import AgentLoader
from .llm_engine import LLMEngine, LLMConfig, LLMProvider, LLMResponse
from .message_bus import MessageBus
from .state_manager import StateManager, OperationStatus

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

# Optional Worker Pool for context isolation
try:
    from ..workers.worker_pool import WorkerPool, WorkerJob, WorkerResult
    from ..workers.context_isolator import ContextIsolator
    HAS_WORKER_POOL = True
except ImportError:
    HAS_WORKER_POOL = False

# Optional Context Compression
try:
    from ..workers.context_compressor import ContextCompressor
    HAS_CONTEXT_COMPRESSOR = True
except ImportError:
    HAS_CONTEXT_COMPRESSOR = False

# Optional Memory Manager
try:
    from ..memory.memory_manager import MemoryManager
    HAS_MEMORY = True
except ImportError:
    HAS_MEMORY = False

# Optional Observability
try:
    from ..observability import get_logger, MetricsCollector
    HAS_OBS = True
except ImportError:
    HAS_OBS = False


class TerminationStatus(str, Enum):
    SUCCESS = "success"
    PARTIAL = "partial"
    FAILURE = "failure"
    ESCALATED_HUMAN = "escalated_human"


class PipelineStatus(str, Enum):
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    STALLED = "stalled"


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

    DEFAULT_SEQUENCE = ["planning", "execution", "observability", "self_correction", "result"]

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
    agent_latencies: dict[str, list[float]] = field(default_factory=dict)  # agent_path -> [latencies]

    def record_agent_latency(self, agent_path: str, latency_ms: float) -> None:
        self.agent_latencies.setdefault(agent_path, []).append(latency_ms)

    @property
    def latency_summary(self) -> dict[str, dict[str, float]]:
        """Return {agent: {count, avg_ms, max_ms, min_ms}} for all agents invoked."""
        summary: dict[str, dict[str, float]] = {}
        for path, times in self.agent_latencies.items():
            if times:
                summary[path] = {
                    "count": len(times),
                    "avg_ms": round(sum(times) / len(times), 2),
                    "max_ms": round(max(times), 2),
                    "min_ms": round(min(times), 2),
                }
        return summary


@dataclass
class PipelineResult:
    final_response: str
    termination_status: TerminationStatus
    session_metrics: SessionMetrics
    audit_anchor: str
    trace: list[IterationTrace] = field(default_factory=list)


class PipelineRunner:
    FLOW_SEQUENCE = [
        "tooll_subagents/user/request.md",
        "tooll_subagents/user/context.md",
        "safety-control/input_sanitizer.md",
        "safety-control/threat_detector.md",
        "control/scope_manager.md",
        "tooll_subagents/planning/task_decomposition.md",
        "tooll_subagents/planning/tool_plan_selection.md",
    ]

    SAFETY_AGENTS = [
        "safety-control/input_sanitizer.md",
        "safety-control/threat_detector.md",
        "safety-control/permission_checker.md",
        "control/scope_manager.md",
        "control/policy_enforcer.md",
    ]

    MUTUAL_CHECK_AGENTS = [
        "safety-control/mutual_check/consistency_checker.md",
        "safety-control/mutual_check/result_validator.md",
        "safety-control/mutual_check/quality_assessor.md",
    ]

    def __init__(self, loader: AgentLoader, llm: LLMEngine, bus: MessageBus, state: StateManager,
                 workspace_root: str = ".", max_workers: int = 4, max_iterations: int = 5):
        self.loader = loader
        self.llm = llm
        self.bus = bus
        self.state = state
        self.workspace = workspace_root
        self._max_iterations = max_iterations
        self._agent_cache: dict[str, AgentSpec] = {}
        self._project_rules = self._load_project_rules()
        self._mcp_registry = None
        self._worker_pool = None
        self._isolator = None
        self._compressor = None

        self._mcp_gateway = None
        if HAS_MCP:
            try:
                registry = create_registry(workspace_root, eager=False)
                self._mcp_gateway = MCPGateway(registry)
            except Exception:
                pass

        if HAS_WORKER_POOL:
            self._isolator = ContextIsolator()
            self._worker_pool = WorkerPool(max_workers=max_workers, isolator=self._isolator)

        if HAS_CONTEXT_COMPRESSOR:
            self._compressor = ContextCompressor(llm_engine=llm, compress_every_n=5)
            self._compressor_next_idx = 0
        else:
            self._compressor_next_idx = 0

        self._memory: MemoryManager | None = None
        if HAS_MEMORY and llm.config.provider != LLMProvider.MOCK:
            try:
                self._memory = MemoryManager(llm_engine=llm)
            except Exception:
                pass

    def _load_project_rules(self) -> dict[str, Any] | None:
        """Load lightweight project rules from workspace root."""
        path = Path(self.workspace) / "project_rules.md"
        if not path.exists():
            return None
        try:
            text = path.read_text(encoding="utf-8")
            return {
                "source": str(path),
                "content_hash": hash(text) & 0xFFFFFFFF,
                "sections": self._parse_project_rules(text),
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

    @property
    def worker_pool_enabled(self) -> bool:
        return self._worker_pool is not None

    async def execute_mcp_tool(self, tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        """Execute a tool via MCP servers directly — bypasses LLM for actual I/O operations."""
        if not self._mcp_gateway:
            return {"error": "MCP not available", "is_error": True}

        result = await self._mcp_gateway.execute(tool_name, arguments)
        return {"tool": tool_name, "result": result, "mcp_executed": True}

    def get_mcp_categories(self) -> list[str]:
        """Return MCP category metadata without loading servers.

        Filters out the Figma category if Figma is not configured so the planner
        does not waste tokens on tools that cannot execute.
        """
        if not self._mcp_gateway:
            return []
        categories = self._mcp_gateway.categories()
        if "figma" in categories and not self.figma_available:
            categories = [c for c in categories if c != "figma"]
        return categories

    # Priority mapping: lower number = higher priority (safety first)
    _TASK_PRIORITIES: dict[str, int] = {
        "safety": 1,
        "validation": 2,
        "planning": 3,
        "execution": 4,
        "read": 5,
        "search": 5,
        "replace": 6,
        "memory": 6,
        "runcom": 7,
        "runtest": 7,
        "terminal": 7,
        "database": 7,
        "web": 7,
        "browser": 7,
        "figma": 5,
        "manangr": 8,
        "self_correction": 3,
    }

    async def execute_isolated(self, agent_path: str, inputs: dict[str, Any],
                               task_category: str = "read") -> WorkerResult | None:
        """Execute an agent in an isolated worker process.

        The agent runs in a separate subprocess. Raw output stays there.
        Only a JSON summary returns — the parent context window stays clean.
        """
        if not self._worker_pool:
            return None

        spec = self._get_agent(agent_path)
        complexity = "heavy" if len(str(inputs)) > 5000 else "normal"
        priority = self._TASK_PRIORITIES.get(task_category, 5)

        job = WorkerJob(
            agent_path=agent_path,
            agent_spec={
                "name": spec.name,
                "role": spec.role,
                "decision_flow": [
                    {"number": s.number, "title": s.title, "description": s.description}
                    for s in spec.decision_flow
                ],
                "failure_modes": [
                    {"condition": f.condition, "response": f.response}
                    for f in spec.failure_modes
                ],
                "contract": {
                    "receives": [
                        {"name": p.name, "type_hint": p.type_hint, "description": p.description}
                        for p in spec.contract.receives
                    ],
                    "returns": [
                        {"name": p.name, "type_hint": p.type_hint, "description": p.description}
                        for p in spec.contract.returns
                    ],
                    "side_effects": spec.contract.side_effects,
                },
            },
            inputs=inputs,
            task_category=task_category,
            complexity=complexity,
            priority=priority,
        )

        return await self._worker_pool.dispatch(job)

    def _get_agent(self, path: str) -> AgentSpec:
        if path not in self._agent_cache:
            self._agent_cache[path] = self.loader.load_agent(path)
        return self._agent_cache[path]

    async def run(self, user_input: str, session_id: str | None = None,
                  max_iterations: int = 5) -> PipelineResult:
        self._max_iterations = max_iterations
        session_id = session_id or uuid.uuid4().hex
        t_start = time.perf_counter()
        metrics = SessionMetrics(session_id=session_id)
        trace: list[IterationTrace] = []
        audit_anchor = uuid.uuid4().hex

        # Observability: mark session start
        if HAS_OBS:
            from ..observability import get_logger, MetricsCollector
            _obs_log = get_logger("pipeline_runner")
            _obs_metrics = MetricsCollector()
        else:
            _obs_log = None
            _obs_metrics = None

        if _obs_log:
            _obs_log.info("Pipeline run started", session_id=session_id, max_iterations=max_iterations)
        if _obs_metrics:
            _obs_metrics.gauge("sessions.active").inc()

        await self.bus.start()
        if self._worker_pool:
            await self._worker_pool.start()

        try:
            self.state.create(f"session:{session_id}", {
                "user_input": user_input,
                "status": PipelineStatus.RUNNING.value,
                "started_at": t_start,
            }, scope="session")

            await self._publish_progress("phase.start", {"phase": "session_init", "session_id": session_id})

            # Cross-session memory enrichment
            memory_context: list[dict[str, Any]] = []
            if self._memory:
                memory_context = self._memory.get_relevant_memories(user_input, limit=5)
                await self._publish_progress("memory.loaded", {
                    "count": len(memory_context), "session_id": session_id,
                })
            augmented_input = self._augment_with_memory(user_input, memory_context)

            # Phase 1: Safety pre-check
            safety_passed = await self._run_safety_pre_check(augmented_input, session_id, trace, metrics)
            if not safety_passed:
                return PipelineResult(
                    final_response="Request blocked by safety pre-check.",
                    termination_status=TerminationStatus.ESCALATED_HUMAN,
                    session_metrics=metrics,
                    audit_anchor=audit_anchor,
                    trace=trace,
                )

            await self._publish_progress("phase.end", {"phase": "safety_pre_check", "session_id": session_id})

            # Phase 2: Plan
            await self._publish_progress("phase.start", {"phase": "planning", "session_id": session_id})
            plan = await self._run_planning(augmented_input, session_id, trace, metrics)
            await self._publish_progress("phase.end", {"phase": "planning", "session_id": session_id})

            # Phase 3: ReAct loop with conditional edges
            transition_manager = PhaseTransitionManager(max_iterations=max_iterations)
            state: dict[str, Any] = {
                "plan": plan,
                "user_input": augmented_input,
                "session_id": session_id,
                "iteration": 0,
            }
            current_phase = "execution"
            result_text = ""

            while current_phase != "result":
                # Handle replanning requests from conditional edges
                if current_phase == "planning":
                    await self._publish_progress("phase.start", {"phase": "planning", "session_id": session_id})
                    plan = await self._run_planning(augmented_input, session_id, trace, metrics)
                    state["plan"] = plan
                    await self._publish_progress("phase.end", {"phase": "planning", "session_id": session_id})
                    # After replanning, always move to execution unless overridden
                    current_phase = "execution"
                    continue

                state["iteration"] += 1
                metrics.iterations = state["iteration"]

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

                # Context Compression: feed new traces to compressor
                if self._compressor:
                    while self._compressor_next_idx < len(trace):
                        self._compressor.add_trace(trace[self._compressor_next_idx].__dict__)
                        self._compressor_next_idx += 1
                    if self._compressor.should_compress(state["iteration"]):
                        summary = await self._compressor.compress()
                        if summary:
                            trace.append(IterationTrace(
                                iteration=state["iteration"],
                                phase="context_compression",
                                agent_path="tools_memory/memory_store/context_compressor.md",
                                inputs={"original_count": summary.original_count},
                                outputs={
                                    "summary": summary.summary,
                                    "compressed_tokens": summary.compressed_tokens_estimate,
                                    "fidelity": summary.fidelity_estimate,
                                    "tokens_saved": self._compressor.stats.get("total_tokens_saved", 0),
                                },
                                latency_ms=0,
                                success=True,
                            ))
                            await self._publish_progress("context.compression", {
                                "iteration": state["iteration"],
                                "tokens_saved": self._compressor.stats.get("total_tokens_saved", 0),
                                "session_id": session_id,
                            })

                current_phase = transition.next_phase

            # Phase 4: Safety post-check
            await self._run_safety_post_check(result_text, session_id, trace, metrics)

            # Phase 5: Final mutual check
            await self._run_mutual_check(result_text, session_id, trace, metrics)

            metrics.time_elapsed_ms = (time.perf_counter() - t_start) * 1000
            self.state.update(f"session:{session_id}", {
                "status": PipelineStatus.COMPLETED.value,
                "completed_at": time.time(),
            }, scope="session")

            if _obs_log:
                _obs_log.info("Pipeline completed", session_id=session_id, status="success", time_ms=metrics.time_elapsed_ms)
            if _obs_metrics:
                _obs_metrics.gauge("sessions.active").dec()
                _obs_metrics.histogram("session.duration_ms").observe(metrics.time_elapsed_ms)
            return await self._finalize_and_return(
                user_input, result_text, TerminationStatus.SUCCESS,
                metrics, audit_anchor, trace, session_id,
            )

        except Exception as e:
            metrics.time_elapsed_ms = (time.perf_counter() - t_start) * 1000
            if _obs_log:
                _obs_log.error("Pipeline failed", session_id=session_id, error=str(e), time_ms=metrics.time_elapsed_ms)
            if _obs_metrics:
                _obs_metrics.gauge("sessions.active").dec()
                _obs_metrics.histogram("session.duration_ms").observe(metrics.time_elapsed_ms)
            return await self._finalize_and_return(
                user_input, f"Pipeline failed: {e}", TerminationStatus.FAILURE,
                metrics, audit_anchor, trace, session_id,
            )
        finally:
            if self._worker_pool:
                await self._worker_pool.stop()
            await self.bus.stop()

    def _augment_with_memory(self, user_input: str, memories: list[dict[str, Any]]) -> str:
        if not memories:
            return user_input
        lines = ["[Relevant past memories]"]
        for m in memories:
            snippet = m.get("body", "") or m.get("title", "")
            if snippet:
                lines.append(f"  - [{m.get('type', 'mem')}] {snippet[:180]}")
        lines.append("")
        lines.append("[Current request]")
        lines.append(user_input)
        return "\n".join(lines)

    async def _finalize_and_return(self, user_input: str, final_response: str,
                                   termination_status: TerminationStatus,
                                   metrics: SessionMetrics, audit_anchor: str,
                                   trace: list[IterationTrace], session_id: str) -> PipelineResult:
        result = PipelineResult(
            final_response=final_response,
            termination_status=termination_status,
            session_metrics=metrics,
            audit_anchor=audit_anchor,
            trace=trace,
        )
        if self._memory:
            try:
                await asyncio.to_thread(
                    self._memory.enrich_session,
                    {
                        "user_input": user_input,
                        "final_response": final_response,
                        "trace": [t.__dict__ for t in trace],
                        "metrics": metrics.__dict__,
                        "termination_status": termination_status.value,
                    },
                )
                await self._publish_progress("memory.stored", {"session_id": session_id})
            except Exception:
                pass
        return result

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
                blocked = result.parsed.get("blocked", result.parsed.get("status") == "blocked")
                if blocked:
                    metrics.safety_checks_failed += 1
                    return False
                metrics.safety_checks_passed += 1
                context.update(result.parsed)
        return True

    async def _run_planning(self, user_input: str, session_id: str,
                            trace: list[IterationTrace], metrics: SessionMetrics) -> dict[str, Any]:
        plan = {
            "user_input": user_input,
            "session_id": session_id,
            "project_rules": self._project_rules,
            "mcp_categories": self.get_mcp_categories() if self.mcp_enabled else [],
        }
        for agent_path in self.FLOW_SEQUENCE:
            result = await self._invoke_agent(agent_path, plan, trace, "planning", metrics)
            if result and result.parsed:
                plan.update(result.parsed)
        return plan


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

    async def _run_execution(self, state: dict[str, Any],
                             trace: list[IterationTrace],
                             metrics: SessionMetrics) -> None:
        exec_agents = [
            "tooll_subagents/execution/tool_invocation.md",
            "tooll_subagents/execution/safety_guardrails.md",
        ]
        result: dict[str, Any] = {
            "plan": state.get("plan"),
            "user_input": state.get("user_input"),
            "iteration": state.get("iteration"),
            "session_id": state.get("session_id"),
            "mcp_categories": self.get_mcp_categories() if self.mcp_enabled else [],
        }
        for agent_path in exec_agents:
            llm_result = await self._invoke_agent(agent_path, result, trace, "execution", metrics)
            if llm_result and llm_result.parsed:
                result.update(llm_result.parsed)

        # If the planner selected a Figma MCP tool, execute it directly here.
        tool_call = result.get("tool_call") or result.get("tool")
        if isinstance(tool_call, dict) and tool_call.get("name", "").startswith("figma_"):
            tool_output = await self.execute_mcp_tool(
                tool_call["name"], tool_call.get("arguments", {})
            )
            result["tool_output"] = tool_output
            result["tool_result"] = tool_output.get("result")
            result["success"] = not tool_output.get("result", {}).get("is_error", False)
            if "result" in tool_output.get("result", {}):
                result["result"] = tool_output["result"]["result"]

        state["execution"] = result
        if "result" in result:
            state["result"] = result["result"]

    async def _run_observation(self, state: dict[str, Any],
                               trace: list[IterationTrace],
                               metrics: SessionMetrics) -> None:
        obs_agents = [
            "tooll_subagents/observability/environment_result.md",
            "tooll_subagents/observability/runtime_output.md",
        ]
        exec_result = state.get("execution", {})
        result: dict[str, Any] = dict(exec_result)
        for agent_path in obs_agents:
            llm_result = await self._invoke_agent(agent_path, result, trace, "observation", metrics)
            if llm_result and llm_result.parsed:
                result.update(llm_result.parsed)
        state["observation"] = result
        if "result" in result:
            state["result"] = result["result"]

    async def _run_validation(self, state: dict[str, Any],
                              trace: list[IterationTrace], metrics: SessionMetrics) -> None:
        observation = state.get("observation", {})
        result = await self._invoke_agent(
            "tooll_subagents/self_correction/result_validation.md",
            {"observation": observation, "original_request": state.get("user_input")},
            trace, "validation", metrics,
        )
        validation: dict[str, Any] = dict(observation)
        if result and result.parsed:
            validation.update(result.parsed)
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

    async def _run_safety_post_check(self, result_text: str, session_id: str,
                                     trace: list[IterationTrace], metrics: SessionMetrics):
        for agent_path in [
            "safety-control/output_reviewer.md",
            "safety-control/data_leak_preventer.md",
            "safety-control/content_checker.md",
        ]:
            await self._invoke_agent(agent_path, {"output": result_text}, trace, "safety_post_check", metrics)

    async def _run_mutual_check(self, result_text: str, session_id: str,
                                trace: list[IterationTrace], metrics: SessionMetrics):
        for agent_path in self.MUTUAL_CHECK_AGENTS:
            await self._invoke_agent(agent_path, {"result": result_text, "session_id": session_id},
                                     trace, "mutual_check", metrics)

    def _is_tool_agent(self, agent_path: str) -> bool:
        """Determine if agent is a tools_* agent that should run isolated."""
        return agent_path.startswith("tools_")

    def _extract_category(self, agent_path: str) -> str:
        """Extract task category from agent path: tools_read/... -> read"""
        if agent_path.startswith("tools_"):
            parts = agent_path.replace("\\", "/").split("/")
            if parts:
                return parts[0].replace("tools_", "")
        if agent_path.startswith("figma_"):
            return "figma"
        if "execution" in agent_path:
            return "execution"
        if "planning" in agent_path:
            return "planning"
        if "safety" in agent_path:
            return "safety"
        if "self_correction" in agent_path:
            return "self_correction"
        return "read"

    async def _invoke_agent(self, agent_path: str, inputs: dict[str, Any],
                            trace: list[IterationTrace], phase: str,
                            metrics: SessionMetrics | None = None) -> LLMResponse | None:
        t0 = time.perf_counter()

        # Route tools_* agents through isolated worker processes
        if self._worker_pool and self._is_tool_agent(agent_path):
            return await self._invoke_isolated(agent_path, inputs, trace, phase, t0, metrics)

        # Reasoning agents use LLM Engine directly
        try:
            spec = self._get_agent(agent_path)
            result = await self.llm.execute(spec, inputs)
            latency = (time.perf_counter() - t0) * 1000
            if metrics:
                metrics.record_agent_latency(agent_path, latency)
            trace.append(IterationTrace(
                iteration=len([t for t in trace if t.phase == phase]) + 1,
                phase=phase,
                agent_path=agent_path,
                inputs=inputs,
                outputs=result.parsed,
                latency_ms=latency,
                success=True,
            ))
            session_id = inputs.get("session_id", "")
            iteration = inputs.get("iteration", metrics.iterations if metrics else 0)
            await self._publish_progress("agent.invoke", {
                "iteration": iteration, "phase": phase, "agent_path": agent_path,
                "session_id": session_id, "latency_ms": round(latency, 2), "success": True,
            })
            await self._publish_audit(agent_path, inputs, result.parsed, "success")
            return result
        except Exception as e:
            latency = (time.perf_counter() - t0) * 1000
            if metrics:
                metrics.record_agent_latency(agent_path, latency)
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
            session_id = inputs.get("session_id", "")
            iteration = inputs.get("iteration", metrics.iterations if metrics else 0)
            await self._publish_progress("agent.invoke", {
                "iteration": iteration, "phase": phase, "agent_path": agent_path,
                "session_id": session_id, "latency_ms": round(latency, 2), "success": False,
            })
            await self._publish_audit(agent_path, inputs, None, f"failed: {e}")
            return None

    async def _invoke_isolated(self, agent_path: str, inputs: dict[str, Any],
                               trace: list[IterationTrace], phase: str,
                               t0: float, metrics: SessionMetrics | None = None) -> LLMResponse | None:
        """Invoke agent in isolated worker process. Returns summary only."""
        category = self._extract_category(agent_path)
        try:
            worker_result = await self.execute_isolated(agent_path, inputs, category)

            if worker_result and worker_result.is_success:
                latency = (time.perf_counter() - t0) * 1000
                if metrics:
                    metrics.record_agent_latency(agent_path, latency)
                # Build LLMResponse-compatible result from worker summary
                parsed = worker_result.parsed_output or {}
                parsed["_summary"] = worker_result.summary
                parsed["_tokens_saved"] = self._worker_pool._estimate_saved_tokens(worker_result) if self._worker_pool else 0
                parsed["_isolated"] = True
                parsed["_worker_id"] = worker_result.worker_id
                parsed["_model"] = worker_result.model

                trace.append(IterationTrace(
                    iteration=len([t for t in trace if t.phase == phase]) + 1,
                    phase=phase,
                    agent_path=agent_path,
                    inputs=inputs,
                    outputs=parsed,
                    latency_ms=latency,
                    success=True,
                ))
                session_id = inputs.get("session_id", "")
                iteration = inputs.get("iteration", metrics.iterations if metrics else 0)
                await self._publish_progress("agent.invoke", {
                    "iteration": iteration, "phase": phase, "agent_path": agent_path,
                    "session_id": session_id, "latency_ms": round(latency, 2), "success": True, "isolated": True,
                })
                await self._publish_audit(agent_path, inputs, parsed, "success_isolated")

                return LLMResponse(
                    content=worker_result.summary,
                    parsed=parsed,
                    model=worker_result.model,
                    tokens_used=worker_result.tokens_used,
                    latency_ms=latency,
                )
            else:
                error_msg = worker_result.error if worker_result else "Worker returned no result"
                raise RuntimeError(error_msg)
        except Exception as e:
            latency = (time.perf_counter() - t0) * 1000
            if metrics:
                metrics.record_agent_latency(agent_path, latency)
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
            session_id = inputs.get("session_id", "")
            iteration = inputs.get("iteration", metrics.iterations if metrics else 0)
            await self._publish_progress("agent.invoke", {
                "iteration": iteration, "phase": phase, "agent_path": agent_path,
                "session_id": session_id, "latency_ms": round(latency, 2), "success": False, "isolated": True,
            })
            await self._publish_audit(agent_path, inputs, None, f"isolated_failed: {e}")
            return None

    async def _publish_audit(self, agent_path: str, inputs: dict[str, Any],
                             outputs: dict[str, Any] | None, status: str):
        msg = Message(
            message_type=MessageType.EVENT,
            topic="audit",
            payload={"agent": agent_path, "inputs": inputs, "outputs": outputs, "status": status},
        )
        await self.bus.publish(msg)

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
