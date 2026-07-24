---
name: 4-tier-memory-architecture
description: Reference note mapping the four-tier Agentic Loop memory architecture (MD core, vector semantic, temporal graph, Reflexion) and the Hermes memory bridge.
metadata:
  type: reference
---

# Agentic Loop — 4-tier memory architecture

## Tier 1 — MD core
- Files: `MEMORY.md` + project `memory/*.md`.
- Purpose: rules, user profile, project facts, feedback notes.
- Limits: ~2000 characters per note; human-readable and diff-friendly.
- Hermes equivalent: `~/.hermes/memory/*.md`.

## Tier 2 — Vector semantic memory
- Modules: `runtime/engine/memanto_client.py`, `runtime/engine/mem0_client.py`.
- Backends: Memanto local REST / SDK; Mem0 embedded Chroma/Qdrant or cloud API.
- Agents: `tooll_subagents/observability/memanto_remember.md`, `memanto_recall.md`, `memanto_answer.md`; `mem0_remember.md`, `mem0_recall.md`, `mem0_list.md`.
- Purpose: search by meaning, not keyword; long-term recall across sessions.

## Tier 3 — Temporal memory graph
- Module: `runtime/temporal_memory/TemporalMemoryEngine` (networkx + SQLite).
- Agents:
  - `tooll_subagents/planning/temporal_memory_planner.md`
  - `tooll_subagents/execution/temporal_memory_runtime_integrator.md`
  - `tooll_subagents/observability/temporal_memory_audit_agent.md`
- Node kinds: `fact`, `state`, `event`, `commitment`, `profile_field`.
- Edge kinds: `replaces`, `supersedes`, `causes`, `contradicts`, `valid_between`.
- Purpose: answer "what was true at time T?" and detect contradictions over time.
- Env: `TEMPORAL_MEMORY_ENABLED`, `TEMPORAL_MEMORY_DB_PATH`.

## Tier 4 — Reflexion cycle
- Agents:
  - `tooll_subagents/observability/feedback_collector.md`
  - `tooll_subagents/observability/feedback_writer.md`
  - `tooll_subagents/observability/feedback_recall.md`
- Storage: `memory/feedback_<topic>.md` under the project.
- Format: `trigger`, `symptom`, `root_cause`, `fix`, `how_to_detect_early`, `related_agents`, `last_seen`.
- Integration: triggered by `self_correction/result_validation.md`; consumed by `tooll_subagents/observability/gotcha_extractor.md` for skill packaging.

## Hermes memory bridge
- Server: `mcp_servers/hermes_memory_server.py` (category `hermes_memory`).
- Client: `runtime/engine/hermes_memory_client.py`.
- Tools: `hermes_memory_list`, `hermes_memory_read`, `hermes_memory_write`, `hermes_memory_search`, `hermes_journey_query`.
- Workspace: `~/.hermes/memory/` or `HERMES_DIR`.
- Degrades cleanly if Hermes is not installed.

## When to use which tier
| Situation | Tier |
|---|---|
| Stable rules, profile, project conventions | 1 — MD core |
| Search by meaning across many sessions | 2 — vector |
| Tariffs, statuses, prices, deadlines that change | 3 — temporal graph |
| Agent learned from a mistake and should not repeat it | 4 — Reflexion |
| User already uses Hermes for memory | Hermes bridge |
