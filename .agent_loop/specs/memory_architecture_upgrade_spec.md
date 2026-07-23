---
session_id: memory_architecture_upgrade_2026_07_23
approval_token: pending
approved_at: pending
scope_size: large
automation_mode: autonomous
---

## Goal

Upgrade the Agentic Loop memory layer from a static file-based core plus two optional vector stores (Memanto/Mem0) into a four-tier memory architecture:

1. **MD core** — preserved, lightweight rules/profile/facts (~2000 chars).
2. **Semantic vector memory** — Memanto/Mem0 already implemented.
3. **Temporal memory graph** — new runtime + agents that track facts changing over time and answer "what was true at time T".
4. **Reflexion cycle** — new observability agents that collect failures, write durable `feedback_*.md` notes, and recall them before planning.

Also add a new optional MCP provider `hermes_memory` that wraps the local Hermes memory workspace (`~/.hermes/memory/*.md`, `~/.hermes/config.yaml`, `hermes journey` CLI) so Agentic Loop can read/write Hermes-managed memories without duplicating them.

Finally, persist a cross-session reference note in `memory/` documenting the 4-tier architecture and the Hermes mapping.

## Scope

### A. Temporal memory graph runtime
- New runtime module `runtime/temporal_memory/TemporalMemoryEngine.py` with:
  - `TemporalMemoryGraph` built on networkx + local SQLite edge store.
  - Nodes: `fact`, `state`, `event`, `commitment`, `profile_field`.
  - Edges: `replaces`, `supersedes`, `causes`, `contradicts`, `valid_between(t1, t2)`.
  - Operations: `record_fact`, `record_state_change`, `query_at_time`, `query_evolution`, `find_contradictions`, `consolidate`.
  - Config from env: `TEMPORAL_MEMORY_ENABLED`, `TEMPORAL_MEMORY_DB_PATH` (default `{workspace}/.temporal_memory/graph.db`).
  - Deterministic, no external API required; degrades to in-memory graph if DB write fails.
- New runtime config/result dataclasses: `TemporalMemoryConfig`, `TemporalMemoryResult`.

### B. Temporal memory ReAct agents
- `tooll_subagents/planning/temporal_memory_planner.md` — decides when a task needs temporal tracking (tariffs, statuses, deadlines).
- `tooll_subagents/execution/temporal_memory_runtime_integrator.md` — materializes and queries the graph.
- `tooll_subagents/observability/temporal_memory_audit_agent.md` — checks consistency and flags contradictions.
All three follow the Algorithmic template (Role, Contract, Decision Flow, Failure Modes).

### C. Reflexion feedback pipeline
- New observability agents:
  - `tooll_subagents/observability/feedback_collector.md` — gathers failures, user corrections, validator outputs, and goal evaluator verdicts.
  - `tooll_subagents/observability/feedback_writer.md` — writes compact `feedback_<topic>.md` notes under the workspace `memory/` directory (or project memory path) with canonical structure: trigger, symptom, root cause, fix, how to detect early.
  - `tooll_subagents/observability/feedback_recall.md` — searches prior `feedback_*.md` by semantic similarity before planning/execution.
- Integration:
  - `tooll_subagents/self_correction/result_validation.md` emits `feedback_payload` on `failed`/`needs_refinement` verdicts.
  - `tooll_subagents/observability/gotcha_extractor.md` consumes feedback notes and promotes reusable ones to project skills or `memory/`.

### D. Hermes memory MCP provider
- New MCP server `mcp_servers/hermes_memory_server.py` exposing:
  - `hermes_memory_read` — read a Hermes memory `.md` by name.
  - `hermes_memory_list` — list Hermes memory entries.
  - `hermes_memory_search` — semantic search via Hermes `memory.provider` if configured, otherwise fallback to local substring scan.
  - `hermes_memory_write` — append a new memory note (`.md` only, path-constrained).
  - `hermes_journey_query` — read the journey graph if Hermes provides it; otherwise degraded.
- Runtime client `runtime/engine/hermes_memory_client.py` mirrors the tools with filesystem/CLI fallback.
- Lazy registration in `mcp_servers/bootstrap.py` and `mcp_servers/registry.py` as category `hermes_memory`.
- Degrades gracefully if Hermes is not installed/configured.

### E. Memory architecture reference note
- Write `memory/4-tier-memory-architecture.md` summarizing:
  - Tier 1: MD core (`MEMORY.md` + `memory/*.md`).
  - Tier 2: Vector semantic (`Memanto`, `Mem0`).
  - Tier 3: Temporal graph (`TemporalMemoryEngine`).
  - Tier 4: Reflexion (`feedback_*.md` + `gotcha_extractor.md`).
  - Hermes bridge (`hermes_memory` MCP).
- Update `MEMORY.md` index with a one-line pointer.

## Out of Scope
- Replacing Memanto/Mem0.
- Adding external paid vector/temporal providers (Zep, Graphiti) as defaults.
- Changing the existing `project_rules.md` approval process.

## Key Decisions

1. Temporal graph uses networkx + SQLite locally so it works offline and in CI without external dependencies.
2. Reflexion feedback files are Markdown so they remain human-readable and diff-friendly under VCS when placed in the project memory path.
3. Hermes provider is optional and lazy; no hard dependency on Hermes CLI.
4. New agents are wired into `runtime/engine/agent_invocation_map.py` and counted by the existing health check and validators.
5. All changes follow the Algorithmic template and existing model-tiering conventions.

## Deliverables

| # | Deliverable | Location |
|---|---|---|
| 1 | TemporalMemoryEngine runtime | `runtime/temporal_memory/__init__.py`, `config.py`, `engine.py`, `result.py` |
| 2 | Temporal memory agents | `tooll_subagents/planning/temporal_memory_planner.md`, `tooll_subagents/execution/temporal_memory_runtime_integrator.md`, `tooll_subagents/observability/temporal_memory_audit_agent.md` |
| 3 | Reflexion feedback agents | `tooll_subagents/observability/feedback_collector.md`, `feedback_writer.md`, `feedback_recall.md` |
| 4 | Result validation integration | Edit `tooll_subagents/self_correction/result_validation.md` to emit `feedback_payload` |
| 5 | Hermes MCP server | `mcp_servers/hermes_memory_server.py` |
| 6 | Hermes runtime client | `runtime/engine/hermes_memory_client.py` |
| 7 | MCP bootstrap wiring | Edit `mcp_servers/bootstrap.py`, `mcp_servers/registry.py`, `runtime/engine/agent_invocation_map.py` |
| 8 | Tests | `tests/temporal_memory/test_engine.py`, `tests/mcp/test_hermes_memory_server.py`, `tests/observability/test_feedback_pipeline.py` |
| 9 | Memory reference note | `memory/4-tier-memory-architecture.md` + `MEMORY.md` update |

## Success Criteria

- [ ] `python -m pytest tests/temporal_memory tests/mcp/test_hermes_memory_server.py tests/observability/test_feedback_pipeline.py -v` passes.
- [ ] `python .agent_loop/scripts/health_check.py` returns HEALTHY after all new agents are wired.
- [ ] `node .agent_loop/scripts/validate_cross_references.js` reports 0 broken links and 0 isolated agents.
- [ ] `python -m mcp_servers.bootstrap --test` reports all servers operational, including `hermes_memory` (degraded acceptable if Hermes not installed).
- [ ] Temporal engine can record a state change, query the fact at a past timestamp, and detect a contradiction.
- [ ] Reflexion pipeline can convert a synthetic validation failure into a `feedback_*.md` note and recall it by query.
- [ ] Hermes memory server read/write falls back cleanly when `~/.hermes/` is absent.

## Human Zones

- None. All operations are local file/DB writes inside the workspace and optional external memory reads; no deploy, payment, or bulk notification.

## Assumptions

- `networkx` is acceptable as a new optional dependency in `runtime/requirements.txt` (or isolated to `runtime/requirements-temporal.txt`).
- Hermes CLI/config path is `~/.hermes/`; if Hermes changes this path in future versions, the client will need a config override.
- Existing `feedback_aggregator.md` in `safety-control/mutual_check/` remains unchanged; the new Reflexion pipeline lives in `tooll_subagents/observability/` and complements it.

## Verification Plan

1. Run new unit tests for temporal engine and Hermes MCP fallback.
2. Run feedback pipeline tests with mocked validation failure.
3. Run health check and validators.
4. Run MCP bootstrap self-test.
5. Update `ARCHITECTURE.md` agent counts dynamically via health_check.py (no manual count edits).
6. Commit and push to `finish-increment-check`.
