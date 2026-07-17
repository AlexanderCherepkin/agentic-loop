# Cost Audit Agent

## Role
Self-correction agent that verifies LLM cost tracking records and budget compliance using `runtime/cost_tracking/CostTrackingEngine`.

## Contract

### Receives
- `scope`: str — tenant/user scope to audit (default `default`)
- `window_seconds`: int | None — time window for usage report (None = all time)
- `budget_limit`: float | None — optional expected budget to enforce
- `cost_report`: optional dict from `runtime/cost_tracking/CostTrackingEngine.get_report`

### Returns
- `cost_audit_verdict`: dict — {
  - `allowed`: bool
  - `spent`: float
  - `limit`: float | None
  - `remaining`: float | None
  - `total_cost`: float
  - `calls`: int
  - `findings`: list[str]
  - `next_phase_hint`: enum (`result`, `self_correction`)
}

### Side effects
- Reads from `data/cost_tracking.db` via the cost backend.
- May write a budget record if `budget_limit` is provided.

## Decision Flow

1. **Load cost engine** — instantiate `CostTrackingEngine` for the scope.
2. **Fetch usage report** — call `get_report(scope, window_seconds)`.
3. **Check budget** — if `budget_limit` given, set it and run `check_budget(scope)`; otherwise use existing budget.
4. **Evaluate** — `allowed=true` when no budget exists or `spent <= limit`.
5. **Return verdict** with hint `result` if allowed, `self_correction` if budget exceeded.

## Failure Modes

| Condition | Response |
|---|---|
| Cost tracking disabled | `allowed=true`; note that tracking is off |
| Database unreadable | `allowed=true`; log warning |
| Budget exceeded | `allowed=false`; route to `plan_adjustment.md` |
| Negative remaining budget | Clamp to 0; flag as overage |
