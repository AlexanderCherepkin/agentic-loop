#!/usr/bin/env python3
"""Generate runtime/engine/agent_invocation_map.py from the .agent_loop tree.

Run from the project root:
    python .agent_loop/scripts/generate_agent_invocation_map.py
"""

from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
AGENT_DIR = PROJECT_ROOT / ".agent_loop"
TARGET = PROJECT_ROOT / "runtime" / "engine" / "agent_invocation_map.py"

# Hardcoded agents that already have explicit runtime dispatch.
ENTRY = ["main_loop.md"]

PLANNING_CORE = [
    "tooll_subagents/user/request.md",
    "tooll_subagents/user/context.md",
    "safety-control/input_sanitizer.md",
    "safety-control/threat_detector.md",
    "control/scope_manager.md",
    "tooll_subagents/planning/task_decomposition.md",
    "tooll_subagents/planning/tool_plan_selection.md",
]

SAFETY_PRE_CHECK = [
    "safety-control/input_sanitizer.md",
    "safety-control/threat_detector.md",
    "safety-control/permission_checker.md",
    "safety-control/command_guard.md",
    "safety-control/data_leak_preventer.md",
    "safety-control/output_reviewer.md",
    "safety-control/bias_detector.md",
    "safety-control/content_checker.md",
    "safety-control/safety_assessor.md",
    "control/scope_manager.md",
    "control/policy_enforcer.md",
]

SAFETY_POST_CHECK = [
    "safety-control/output_reviewer.md",
    "safety-control/data_leak_preventer.md",
    "safety-control/content_checker.md",
]

EXECUTION_CORE = [
    "tooll_subagents/execution/tool_invocation.md",
    "tooll_subagents/execution/safety_guardrails.md",
]

OBSERVABILITY_CORE = [
    "tooll_subagents/observability/environment_result.md",
    "tooll_subagents/observability/runtime_output.md",
]

VALIDATION_CORE = [
    "tooll_subagents/self_correction/result_validation.md",
    "tooll_subagents/self_correction/recursion_or_termination.md",
]


def discover_agents() -> list[str]:
    paths = []
    for p in sorted(AGENT_DIR.rglob("*.md")):
        rel = p.relative_to(AGENT_DIR).as_posix()
        if rel in ("ARCHITECTURE.md", "TECHNICAL_ASSIGNMENT.md"):
            continue
        content = p.read_text(encoding="utf-8")
        if "## Role" not in content or "## Contract" not in content:
            continue
        paths.append(rel)
    return paths


def classify(agents: list[str]) -> dict[str, list[str]]:
    phase: dict[str, list[str]] = {
        "entry": list(ENTRY),
        "orchestrator": [],
        "control": [],
        "user_intake": [],
        "safety_pre_check": list(SAFETY_PRE_CHECK),
        "safety_post_check": list(SAFETY_POST_CHECK),
        "mutual_check": [],
        "planning_core": list(PLANNING_CORE),
        "planning_general": [],
        "planning_figma": [],
        "planning_backend": [],
        "planning_i18n": [],
        "planning_analytics": [],
        "planning_auth": [],
        "planning_cms": [],
        "planning_accessibility": [],
        "planning_pwa": [],
        "planning_design_token_docs": [],
        "planning_multi_page": [],
        "planning_storybook": [],
        "planning_deploy": [],
        "planning_preview": [],
        "planning_copywriting": [],
        "planning_estimation": [],
        "planning_starter": [],
        "planning_headroom": [],
        "planning_memanto": [],
        "planning_mem0": [],
        "planning_ponytail": [],
        "execution_core": list(EXECUTION_CORE),
        "execution_conditional": [],
        "observability": list(OBSERVABILITY_CORE),
        "self_correction": list(VALIDATION_CORE),
        "result": [],
        "lighthouse_audit": [],
    }

    mcp: dict[str, list[str]] = {
        "tools_read": [],
        "tools_search": [],
        "tools_replace": [],
        "tools_runcom": [],
        "tools_runtest": [],
        "tools_terminal": [],
        "tools_manangr": [],
        "tools_database": [],
        "tools_web": [],
        "tools_memory": [],
        "tools_browser": [],
        "tools_lighthouse": [],
        "figma": [],
        "backend": [],
        "headroom": [],
        "memanto": [],
        "mem0": [],
        "security_scanner": [],
        "git_publisher": [],
        "cost_tracking": [],
        "notifications": [],
    }

    for a in agents:
        if a == "main_loop.md":
            continue

        if a.startswith("orchestrator/"):
            phase["orchestrator"].append(a)
            continue

        if a.startswith("control/"):
            phase["control"].append(a)
            continue

        if a.startswith("safety-control/mutual_check/"):
            phase["mutual_check"].append(a)
            continue

        if a.startswith("safety-control/"):
            # Already listed explicitly above; skip duplicates.
            continue

        if a.startswith("tooll_subagents/user/"):
            phase["user_intake"].append(a)
            continue

        if a.startswith("tooll_subagents/planning/"):
            name = Path(a).stem
            if a in PLANNING_CORE:
                continue
            if name in ("cost_risk_assessment", "internal_monologue", "design_to_code_planner"):
                phase["planning_general"].append(a)
            elif name.startswith("figma") or name in ("asset_agent", "image_enrichment_agent", "responsive_composer", "component_registry", "component_mapper"):
                phase["planning_figma"].append(a)
                mcp["figma"].append(a)
            elif name == "backend_spec_bridge":
                phase["planning_backend"].append(a)
                mcp["backend"].append(a)
            elif name.startswith("i18n"):
                phase["planning_i18n"].append(a)
            elif name.startswith("analytics") or name.startswith("cookie_consent"):
                phase["planning_analytics"].append(a)
            elif name.startswith("auth"):
                phase["planning_auth"].append(a)
            elif name.startswith("cms"):
                phase["planning_cms"].append(a)
            elif name.startswith("accessibility"):
                phase["planning_accessibility"].append(a)
            elif name.startswith("pwa"):
                phase["planning_pwa"].append(a)
            elif name.startswith("design_token_docs"):
                phase["planning_design_token_docs"].append(a)
            elif name.startswith("multi_page"):
                phase["planning_multi_page"].append(a)
            elif name.startswith("storybook"):
                phase["planning_storybook"].append(a)
            elif name.startswith("deploy"):
                phase["planning_deploy"].append(a)
            elif name.startswith("preview"):
                phase["planning_preview"].append(a)
            elif name == "copywriting_agent":
                phase["planning_copywriting"].append(a)
            elif name == "estimation_proposal_agent":
                phase["planning_estimation"].append(a)
            elif name == "project_starter_agent":
                phase["planning_starter"].append(a)
            elif name.startswith("headroom"):
                phase["planning_headroom"].append(a)
            elif name.startswith("ponytail"):
                phase["planning_ponytail"].append(a)
            else:
                phase["planning_general"].append(a)
            continue

        if a.startswith("tooll_subagents/execution/"):
            if a in EXECUTION_CORE:
                continue
            phase["execution_conditional"].append(a)
            name = Path(a).stem
            if name == "git_publish_runtime_integrator":
                mcp["git_publisher"].append(a)
            elif name == "notification_runtime_integrator":
                mcp["notifications"].append(a)
            continue

        if a.startswith("tooll_subagents/observability/"):
            if a in OBSERVABILITY_CORE:
                continue
            phase["observability"].append(a)
            # Also classify optional memory agents into their MCP category.
            name = Path(a).stem
            if name.startswith("memanto"):
                phase["planning_memanto"].append(a)
                mcp["memanto"].append(a)
            elif name.startswith("mem0"):
                phase["planning_mem0"].append(a)
                mcp["mem0"].append(a)
            elif name.startswith("headroom"):
                mcp["headroom"].append(a)
            continue

        if a.startswith("tooll_subagents/self_correction/"):
            if a in VALIDATION_CORE:
                continue
            phase["self_correction"].append(a)
            name = Path(a).stem
            if name == "security_scan_validator":
                mcp["security_scanner"].append(a)
            elif name == "cost_audit_agent":
                mcp["cost_tracking"].append(a)
            continue

        if a.startswith("tooll_subagents/result/"):
            phase["result"].append(a)
            continue

        if a.startswith("tools_"):
            parts = a.split("/")
            category = parts[0]
            if category == "tools_lighthouse":
                phase["lighthouse_audit"].append(a)
            mcp.setdefault(category, []).append(a)
            continue

    return phase, mcp


def render(phase: dict[str, list[str]], mcp: dict[str, list[str]]) -> str:
    def quote_list(items: list[str]) -> str:
        lines = [f'        "{item}",' for item in items]
        return "\n".join(lines)

    phase_blocks = []
    for key, items in phase.items():
        phase_blocks.append(f'    "{key}": [\n{quote_list(items)}\n    ],')

    mcp_blocks = []
    for key, items in mcp.items():
        mcp_blocks.append(f'    "{key}": [\n{quote_list(items)}\n    ],')

    return f'''"""Central invocation map for the Agentic Loop runtime.

This file is generated by `.agent_loop/scripts/generate_agent_invocation_map.py`.
Do not hand-edit; regenerate after adding or moving agents.
"""

from __future__ import annotations

PHASE_AGENTS: dict[str, list[str]] = {{
{chr(10).join(phase_blocks)}
}}

MCP_CATEGORY_AGENT_PATHS: dict[str, list[str]] = {{
{chr(10).join(mcp_blocks)}
}}

# Conditional planner flags -> phase keys that should be dispatched.
PLANNING_FLAG_GROUPS: dict[str, list[str]] = {{
    "needs_figma": ["planning_figma"],
    "needs_backend": ["planning_backend"],
    "needs_i18n": ["planning_i18n"],
    "needs_analytics": ["planning_analytics"],
    "needs_auth": ["planning_auth"],
    "needs_cms": ["planning_cms"],
    "needs_accessibility": ["planning_accessibility"],
    "needs_pwa": ["planning_pwa"],
    "needs_design_token_docs": ["planning_design_token_docs"],
    "needs_multi_page": ["planning_multi_page"],
    "needs_storybook": ["planning_storybook"],
    "needs_deploy": ["planning_deploy"],
    "needs_preview": ["planning_preview"],
    "needs_copywriting": ["planning_copywriting"],
    "needs_estimation": ["planning_estimation"],
    "needs_starter": ["planning_starter"],
    "needs_headroom": ["planning_headroom"],
    "needs_memanto": ["planning_memanto"],
    "needs_mem0": ["planning_mem0"],
    "needs_ponytail": ["planning_ponytail"],
    "needs_lighthouse": ["lighthouse_audit"],
}}


def all_referenced_paths() -> set[str]:
    """Return every agent path referenced by the runtime or MCP layer."""
    paths: set[str] = set()
    for items in PHASE_AGENTS.values():
        paths.update(items)
    for items in MCP_CATEGORY_AGENT_PATHS.values():
        paths.update(items)
    return paths


def phase_dispatch(phase: str) -> list[str]:
    """Agents directly invoked by a named runtime phase."""
    return list(PHASE_AGENTS.get(phase, []))


def conditional_groups_for_flags(flags: dict[str, bool]) -> list[str]:
    """Resolve conditional planning/execution groups from planner flags."""
    groups: list[str] = []
    for flag, active in flags.items():
        if active and flag in PLANNING_FLAG_GROUPS:
            groups.extend(PLANNING_FLAG_GROUPS[flag])
    return groups
'''


def main() -> int:
    agents = discover_agents()
    phase, mcp = classify(agents)

    # Deduplicate within each list while preserving order.
    for key in phase:
        seen: set[str] = set()
        deduped: list[str] = []
        for p in phase[key]:
            if p not in seen:
                seen.add(p)
                deduped.append(p)
        phase[key] = deduped
    for key in mcp:
        seen = set()
        deduped = []
        for p in mcp[key]:
            if p not in seen:
                seen.add(p)
                deduped.append(p)
        mcp[key] = deduped

    TARGET.parent.mkdir(parents=True, exist_ok=True)
    TARGET.write_text(render(phase, mcp), encoding="utf-8")

    referenced = set()
    for items in phase.values():
        referenced.update(items)
    for items in mcp.values():
        referenced.update(items)
    unreachable = sorted(set(agents) - referenced)

    print(f"Generated {TARGET}")
    print(f"  Loaded agents: {len(agents)}")
    print(f"  Referenced: {len(referenced)}")
    print(f"  Unreachable: {len(unreachable)}")
    for p in unreachable:
        print(f"    - {p}")
    return 0 if not unreachable else 1


if __name__ == "__main__":
    raise SystemExit(main())
