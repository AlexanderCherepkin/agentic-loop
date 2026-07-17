# Cost Risk Assessment

## Role
Pre-execution estimator that evaluates token cost, latency, failure probability, and blast radius for the proposed task graph. Enables informed trade-offs between thoroughness, speed, and resource consumption before committing to execution.

## Contract

### Receives
- `task_graph`: decomposition output from `task_decomposition.md`
- `assembled_context`: context object from `context.md`
- `budget_constraints`: optional limits (`max_tokens`, `max_time_ms`, `max_api_calls`, `max_cost_usd`)
- `risk_tolerance`: enum (`conservative`, `moderate`, `aggressive`)

### Returns
- `cost_estimate`: map of resource_type → projected consumption
- `risk_score`: float 0.0–1.0 — composite probability of failure or deviation
- `risk_breakdown`: per-sub-task risk contributions (execution, safety, dependency, environment)
- `recommendation`: enum (`proceed`, `optimize`, `reduce_scope`, `escalate`)
- `next_phase_hint`: enum (`execution`, `planning`, `result`) — suggested next ReAct phase based on risk verdict
- `optimization_suggestions`: list of concrete ways to reduce cost or risk
- `model_tier_recommendations`: map of sub-task → recommended model tier (`fast`, `balanced`, `strong`)
- `proposed_volume_caps`: map of batched/parallel sub-task → cap value (`MAX`, `CHUNK`, `MAX_CHUNKS`)

### Side Effects
- Stores cost model feedback for future calibration
- Logs assessment to `audit_logger.md`

## Decision Flow

1. **Load historical costs** — retrieve average cost per tool call type from telemetry database.
2. **Estimate per sub-task** — multiply historical cost by context size factor and operation complexity.
3. **Sum totals** — aggregate across task graph to produce `cost_estimate` for each resource type.
4. **Compare against budgets** — if any estimate exceeds `budget_constraints`, mark as over-budget.
5. **Assess execution risk** — for each sub-task: probability of tool failure, timeout, or unexpected result based on historical error rates.
6. **Assess safety risk** — probability that safety layer will block or escalate the sub-task based on content sensitivity.
7. **Assess dependency risk** — probability that upstream failure cascades to downstream tasks (critical path amplification).
8. **Assess environment risk** — probability of external changes (network, filesystem, third-party API) during execution.
9. **Composite scoring** — combine risks with weights: execution 0.3, safety 0.3, dependency 0.25, environment 0.15.
10. **Determine recommendation** — `proceed` if within budget and risk < 0.3; `optimize` if within budget but risk 0.3–0.6; `reduce_scope` if over-budget or risk > 0.6; `escalate` if risk > 0.8 or contains irreversible operations.
11. **Generate optimizations** — suggest parallelization, caching, scope reduction, or fallback tool substitution.
12. **Assign model tiers** — for each sub-task, recommend a model tier based on workload type: fast/cheap (`claude-haiku-4-5`) for bulk read/search/web/memory extraction and scoring; balanced (`claude-sonnet-4-6`) for planning, analysis, and synthesis; strong (`claude-opus-4-8`) for architecture, final review, and complex self-correction. Pass `model_tier_recommendations` to `tool_plan_selection.md`.
13. **Propose volume caps** — if the plan includes batched, chunked, or parallel agents, propose `MAX`, `CHUNK`, or `MAX_CHUNKS` caps tied to `budget_constraints.max_api_calls` and `LLMConfig.max_parallel_agents`. Do not approve plans with unbounded growth.
14. **Return** — emit cost estimate, risk score, breakdown, recommendation, optimizations, `model_tier_recommendations`, and `proposed_volume_caps`.

## Failure Modes

| Condition | Response |
|---|---|
| Historical cost data missing for novel tool | Use conservative 3× upper bound; `risk_score` increased by 0.1; flag for calibration |
| Budget constraints impossible (e.g., 0 tokens) | `recommendation=reduce_scope`, `cost_estimate` shows minimum achievable |
| Risk model produces score > 1.0 | Clamp to 1.0; flag model calibration error to `feedback_aggregator.md` |
| Critical path risk exceeds tolerance but parallel path exists | Suggest rerouting via `optimization_suggestions`; if no alternative, `recommendation=escalate` |
| Assessment latency exceeds deadline | Return cached conservative estimate; `risk_score=0.5`, `recommendation=optimize` |
| Model tier recommendation conflicts with `execution_policy` | Prefer the cheaper tier when `execution_policy=cost_priority`; prefer the stronger tier when `execution_policy=accuracy_priority`; default to balanced |
| Volume cap would truncate required work | Flag the conflict in `optimization_suggestions`; propose scope reduction or budget increase |
