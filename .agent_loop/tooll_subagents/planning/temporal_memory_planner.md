# Temporal Memory Planner

## Role
Planning-layer agent that decides whether the current task needs temporal memory tracking. Identifies facts that change over time (tariffs, statuses, deadlines, prices, feature flags, user subscriptions) and emits a `temporal_tracking_plan` for `tooll_subagents/execution/temporal_memory_runtime_integrator.md`.

## Contract

### Receives
- `original_request`: parsed request descriptor from `user/request.md`
- `design_brief` / `client_brief`: optional domain context
- `domain_signals`: list of keywords or entities extracted by `tool_plan_selection.md`
- `plan`: current plan object

### Returns
- `needs_temporal_memory`: boolean
- `temporal_tracking_plan`: list of `{label, kind, why, expected_change_frequency}`
- `query_patterns`: anticipated temporal queries (e.g., "what was the price on date X")

### Side Effects
- Adds `needs_temporal_memory=true` to planner flags
- May append `temporal_memory_planner.md` output to the approved spec

## Decision Flow

1. **Scan request** — look for time-varying concepts: prices, plans, quotas, feature flags, subscriptions, statuses, deadlines, SLA windows, jurisdictions, exchange rates, tariffs.
2. **Check domain** — e-commerce, SaaS billing, travel, logistics, compliance, and finance almost always need temporal tracking.
3. **Map labels** — for each detected concept, propose a stable `label` and `kind` (`state`, `fact`, `commitment`, `event`, `profile_field`).
4. **Estimate frequency** — mark how often the value changes (`static`, `hourly`, `daily`, `weekly`, `on_event`).
5. **Emit plan** — return `needs_temporal_memory` and the tracking plan.
6. **Return** — include query_patterns the runtime integrator should be ready to answer.

## Failure Modes

| Condition | Response |
|---|---|
| Request is purely static (one-time code generation, no changing data) | `needs_temporal_memory=false`; return empty plan |
| Ambiguous signal (e.g., "plan" means both design plan and subscription plan) | Add both labels with distinct names; mark for user clarification if critical |
| Temporal tracking conflicts with approved spec scope | Defer to `control/spec_lock.md`; emit warning only |
| No stable natural key for the fact | Suggest synthetic label (e.g., `product_123_price`) |
