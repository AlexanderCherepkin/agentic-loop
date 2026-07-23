# Temporal Memory Runtime Integrator

## Role
Execution-layer agent that materializes temporal memory facts and queries using `runtime/temporal_memory/TemporalMemoryEngine`. Runs the tracking plan produced by `tooll_subagents/planning/temporal_memory_planner.md` and stores or reads facts as part of the ReAct execution phase.

## Contract

### Receives
- `temporal_tracking_plan`: list of `{label, kind, why, expected_change_frequency}` from `temporal_memory_planner.md`
- `operation`: enum (`record_fact`, `record_state_change`, `query_at_time`, `query_evolution`, `find_contradictions`, `consolidate`)
- `payload`: operation-specific data
- `audit_anchor`: session audit anchor for provenance

### Returns
- `status`: enum (`ok`, `not_found`, `disabled`, `error`)
- `result`: `TemporalMemoryResult` serialized as JSON
- `summary`: human-readable one-line summary

### Side Effects
- Calls `runtime/temporal_memory/TemporalMemoryEngine`
- Logs operation to `audit_logger.md`

## Decision Flow

1. **Check enabled** — if `TEMPORAL_MEMORY_ENABLED=false`, return `status=disabled` and skip.
2. **Initialize engine** — get or create `TemporalMemoryEngine` for the workspace.
3. **Route operation**:
   - `record_fact` → create a new fact node.
   - `record_state_change` → create a new state and wire `replaces` edge to previous node.
   - `query_at_time` → follow replacement chain up to the requested timestamp.
   - `query_evolution` → return the full replacement chain.
   - `find_contradictions` → return contradicting fact pairs.
   - `consolidate` → collapse chain into a summary node.
4. **Tag provenance** — include `audit_anchor` and source agent in metadata.
5. **Handle degradation** — if DB write fails, engine falls back to in-memory graph; log warning.
6. **Return** — emit structured result and summary.

## Failure Modes

| Condition | Response |
|---|---|
| Engine disabled by env | `status=disabled`; no side effects |
| DB write fails | `status=ok` with in-memory fallback; log warning to `audit_logger.md` |
| Query label not found | `status=not_found`; suggest recording the fact first |
| State change without previous node_id | Record as a new fact; log that no chain was linked |
| Contradiction found during write | `status=ok` but append contradiction note; route to `temporal_memory_audit_agent.md` |
