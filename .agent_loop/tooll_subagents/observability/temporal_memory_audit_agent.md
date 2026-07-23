# Temporal Memory Audit Agent

## Role
Observability-layer agent that audits the temporal memory graph for consistency, contradictions, and coverage. Flags facts that overlap in validity without a clear `replaces`/`supersedes` relationship and reports temporal gaps.

## Contract

### Receives
- `audit_scope`: enum (`all`, `label`, `kind`)
- `label` / `kind`: optional filters
- `temporal_memory_stats`: output from `TemporalMemoryEngine.stats()`

### Returns
- `status`: enum (`passed`, `needs_review`, `failed`)
- `findings`: list of inconsistency reports
- `recommended_actions`: ranked remediation steps

### Side Effects
- Reads from `TemporalMemoryEngine`
- Logs audit to `audit_logger.md`

## Decision Flow

1. **Load graph stats** — confirm engine is enabled and nodes/edges are readable.
2. **Find contradictions** — invoke `find_contradictions(label_prefix=label)` if scope is label-specific.
3. **Detect orphans** — flag nodes with no incoming or outgoing edges that are older than the newest node by the same label (possible missing `replaces` link).
4. **Check validity windows** — flag overlapping facts of the same label without a replacement edge.
5. **Assess coverage** — compare tracked labels to the `temporal_tracking_plan`; flag planned labels not present.
6. **Return** — emit status, findings, and recommended actions.

## Failure Modes

| Condition | Response |
|---|---|
| Temporal memory disabled | `status=passed` (no data to audit); note disabled state |
| Engine returns no nodes | `status=passed`; recommend populating graph if temporal tracking was planned |
| Contradiction detected | `status=needs_review`; route contradiction pair to `self_correction/assistance_request.md` if unresolved |
| Orphan nodes exceed threshold | `status=needs_review`; suggest running `consolidate` or adding `replaces` edges |
| Audit scope invalid | `status=failed`; return error |
