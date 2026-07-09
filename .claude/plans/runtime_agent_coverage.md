# Plan — Close runtime invocation gap for every loaded agent

## Problem

Audit row 25 reports that many `.agent_loop/*.md` specs loaded by `AgentLoader.load_all_agents()` are not referenced from any runtime phase, MCP category, or tool. Current state:

- `AgentLoader` recursively loads **253** `.md` files under `.agent_loop/` (including `main_loop.md` and `TECHNICAL_ASSIGNMENT.md`).
- `PipelineRunner` directly hardcodes only **~32** agent paths in `FLOW_SEQUENCE`, `SAFETY_AGENTS`, `MUTUAL_CHECK_AGENTS`, `exec_agents`, and `obs_agents`.
- `tools_*` agents are conceptually reached through the MCP gateway, but `mcp_servers/registry.py` and `bootstrap.py` register tool names without string references to the underlying `.md` specs.
- `main_loop.md` and many module-specific agents (i18n, analytics, auth, CMS, accessibility, PWA, design-token docs, Headroom, Memanto, Mem0, Ponytail, Figma/backend, Lighthouse) are documented in `ARCHITECTURE.md` as conditionally dispatched, but that dispatch is not implemented in the Python runtime.

The cross-reference validator checks markdown-level links (0 isolated), and the consistency validator checks the Algorithmic template, but neither checks whether every loaded spec has a concrete runtime invocation path.

## Goal

Every `.md` spec that `AgentLoader` loads must be traceable to at least one concrete invocation source:
- a runtime phase in `PipelineRunner`,
- the runtime entry point in `runtime/main.py`,
- an MCP category/tool registration in `mcp_servers/`, or
- a documented conditional dispatch branch in the new invocation map.

Add an automated validator that fails the build if any loaded agent becomes unreachable.

## Proposed implementation

### 1. Central invocation map (`runtime/engine/agent_invocation_map.py`)

Create a single source of truth: a `dict[str, list[str]]` mapping invocation contexts to ordered agent path lists. The map is derived from `ARCHITECTURE.md` and the existing hardcoded lists.

Contexts to cover:
- `entry` — `main_loop.md` (the head spec implemented by `runtime/main.py`).
- `safety_pre_check` — existing `SAFETY_AGENTS`.
- `design_intake` — `tooll_subagents/user/design_intake.md`.
- `planning_core` — existing `FLOW_SEQUENCE`.
- `planning_conditional` — module planners, grouped by capability flag (i18n, analytics, auth, cms, accessibility, pwa, design-token docs, headroom, memanto, mem0, ponytail, figma/backend, cost/risk, internal monologue).
- `execution_core` — `tool_invocation.md`, `safety_guardrails.md`.
- `execution_conditional` — `human_approval.md`, `action_logging.md`, and module runtime integrators.
- `mcp_tools` — mapping from each MCP category/tool name to the corresponding `tools_*/*.md` agent path(s).
- `observability` — all observability agents (memory, audit, headroom, file context, etc.).
- `self_correction` — all validators, `goal_evaluator.md`, `plan_adjustment.md`, `ponytail_review.md`, `assistance_request.md`.
- `result` — result-layer agents.
- `safety_post_check` — post-check agents.
- `mutual_check` — existing `MUTUAL_CHECK_AGENTS`.

Each conditional group will also carry the flag key the planner must emit to trigger it.

### 2. `AgentLoader` filter for real agent specs

Update `load_all_agents()` to skip files that are not agent specs:
- already skips `ARCHITECTURE.md`; add `TECHNICAL_ASSIGNMENT.md`.
- require the presence of `## Role` and `## Contract` (Algorithmic template markers) before loading; skip and log others.
- keep `main_loop.md` because it is a valid head-agent spec.

This removes documentation files from the loaded set so the coverage validator only counts actual agents.

### 3. Refactor `PipelineRunner` to use the map

Replace the hardcoded lists in `pipeline_runner.py` with imports from `agent_invocation_map`. The existing `FLOW_SEQUENCE`, `SAFETY_AGENTS`, `MUTUAL_CHECK_AGENTS`, etc., become derived from the map so the coverage validator can read the same data.

Extend the phase runners with conditional dispatch helpers:
- `_run_planning`: after the core sequence, inspect the plan for module flags (`needs_i18n`, `needs_analytics`, `needs_auth`, `needs_cms`, `needs_accessibility`, `needs_pwa`, `needs_design_token_docs`, `needs_headroom`, `needs_memanto`, `needs_mem0`, `needs_figma`, `needs_backend`, `needs_ponytail`, etc.) and dispatch the relevant planning agents. Also run `cost_risk_assessment.md` and `internal_monologue.md`.
- `_run_execution`: dispatch `human_approval.md` and `action_logging.md` plus any runtime integrators flagged by the plan.
- `_run_observation`: dispatch all observability agents in parallel (read-only/cheap). Skip memory/headroom agents when their optional MCP layer is disabled.
- `_run_validation`: dispatch all self-correction validators plus `goal_evaluator.md` in parallel, bounded by timeout.
- `_run_result`: dispatch result agents when building the final response.

All conditional dispatch respects the three-circuit safety flow and does not block on disabled optional modules.

### 4. MCP category → agent spec wiring

Add an `AGENT_PATHS` mapping to the MCP layer so every `tools_*/*.md` spec is reachable from Python/MCP code:
- create `mcp_servers/agent_paths.py` (or class-level `AGENT_PATHS` in each server) mapping each category and each tool name to the relative `.agent_loop` path(s).
- update `bootstrap.py` to inject `metadata["agent_paths"]` into each `ServerInfo` registration.
- keep the Python tool implementations unchanged; the mapping is metadata for coverage and debugging only.

### 5. Runtime coverage validator

Add `.agent_loop/scripts/validate_runtime_coverage.py`:
- load all agents via `AgentLoader`.
- collect all referenced agent paths from `agent_invocation_map`, `PipelineRunner`, MCP registry metadata, and `runtime/main.py`.
- report unreachable agents and the invocation source count per agent.
- exit code `0` when coverage is 100%, otherwise nonzero.
- support `--json` for CI/health check consumption.

### 6. Tests and health check

- Add `tests/runtime/test_runtime_coverage.py` that runs the validator with the `mock` LLM provider and asserts 100% coverage.
- Update `.agent_loop/scripts/health_check.py` with a new `Runtime coverage` check that runs the validator.
- Update `EXPECTED_AGENTS` in health check if the filtered loader count changes.

### 7. Validation and cleanup

- Run `node .agent_loop/scripts/validate_cross_references.js` and `validate_consistency.js`.
- Run `pytest -m core`.
- Run `.agent_loop/scripts/health_check.py`.
- Fix any regressions.
- Run `graphify update .` to refresh the knowledge graph.

## Risks and mitigations

| Risk | Mitigation |
|------|------------|
| Invoking all observability/validation agents every iteration becomes expensive | Run them in parallel with a phase timeout; skip optional agents when disabled; keep core ReAct path unchanged. |
| Conditional flags from the planner may not exist yet | Add sensible defaults: dispatch a lightweight planning agent only when its requirement is detected in the request or when the flag is explicitly set. |
| Adding 100+ agents to normal runs could break mock tests | Use the mock provider and deterministic responses; the coverage test validates reachability, not semantic correctness. |
| `AgentLoader` filter accidentally skips a real agent | Only skip files that lack both `## Role` and `## Contract`; add a test that loaded count matches the architecture count. |
| Changes to `ARCHITECTURE.md` or `CLAUDE.md` | Update `ARCHITECTURE.md` flow section to mention `agent_invocation_map.py` as the runtime source of truth; do not touch `CLAUDE.md` unless explicitly required. |

## Acceptance criteria

1. `AgentLoader.load_all_agents()` loads only real agent specs (no `TECHNICAL_ASSIGNMENT.md`).
2. `runtime/engine/agent_invocation_map.py` references every loaded agent in at least one context.
3. `PipelineRunner` imports its dispatch lists from the invocation map and conditionally dispatches module-specific agents.
4. MCP registry metadata contains string references to every `tools_*/*.md` agent.
5. `validate_runtime_coverage.py` reports 0 unreachable agents and exits 0.
6. Health check reports `[OK] Runtime coverage`.
7. `pytest -m core` passes.
8. Knowledge graph is updated with `graphify update .`.

## Next step

Implement the plan above after approval.
