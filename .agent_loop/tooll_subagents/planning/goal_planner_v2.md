# Goal Planner V2

## Role

`/goal` planning agent that coordinates one-shot, verifiable task execution using a two-model split. Dispatches cheap `claude-haiku-4-5` workers for bulk evidence gathering and candidate generation, then routes to an expensive `claude-opus-4-8` verifier with at least two adversarial critics before declaring the goal satisfied.

## Contract

### Receives

- `parsed_goal_intent`: from `main_loop.md` or `tooll_subagents/user/request.md`
- `goal`: string — explicit success condition
- `criteria`: optional list[str] of explicit success criteria
- `budget`: object from `runtime/cost_tracking/` with `max_tokens`, `max_cost_usd`, `max_iterations`
- `trust_level`: enum (`L1`, `L2`, `L3`) from session or default `L1`
- `iteration_count`: integer — current ReAct iteration
- `max_iterations`: integer
- `project_rules`: dict | None

### Returns

- `goal_plan`: ordered task graph containing:
  - `trust_gate`: invocation of `control/loop_trust_levels.md`
  - `cost_check`: invocation of `runtime/cost_tracking/` or `tooll_subagents/self_correction/cost_audit_agent.md`
  - `cheap_worker_steps`: parallel `claude-haiku-4-5` sub-tasks for read/search/audit/score
  - `verifier_step`: `runtime/loop_engine/loop_verifier.py` with ≥2 adversarial critics
  - `adjustment_route`: fallback to `tooll_subagents/self_correction/plan_adjustment.md` or human escalation
- `effective_trust_level`: enum (`L1`, `L2`, `L3`) after gate
- `model_tier_plan`: map of step → model tier (`fast`, `balanced`, `strong`)
- `estimated_cost`: dict with `tokens`, `usd`, `budget_ok`
- `next_action`: enum (`execute`, `ask_user`, `escalate_human`)

### Side Effects

- Writes the plan to session state under `goal_plan`
- Logs cheap/expensive model split, cost estimate, and trust gate result to `audit_logger.md`
- If the goal is approved, may persist constraints to `.agent_loop/CONSTRAINTS.md` via `runtime/loop_engine/constraints_manager.py`

## Decision Flow

1. **Normalize goal** — if `goal` is missing, try to extract it from `parsed_goal_intent.goal`. If still missing, set `next_action=ask_user` and request a goal.
2. **Infer criteria** — if `criteria` is absent, derive 1–3 verifiable criteria from `goal` and `project_rules`. Each criterion must have a deterministic pass/fail signal.
3. **Consult trust levels** — invoke `control/loop_trust_levels.md` with the inferred operation list and requested `trust_level`. Capture `effective_trust_level` and `blocked_operations`.
4. **Check budget** — call `runtime/cost_tracking/CostTrackingEngine` or `tooll_subagents/self_correction/cost_audit_agent.md`. If `budget.max_cost_usd` or `budget.max_tokens` would be exceeded by the cheap+verifier plan, propose reduction or escalation.
5. **Assign model tiers** — mark all read/search/audit/score sub-tasks as `fast` (`claude-haiku-4-5`); mark synthesis, architecture, and final verification as `strong` (`claude-opus-4-8`). Use `balanced` only for planning steps that are not verification.
6. **Build cheap worker phase** — create parallel `claude-haiku-4-5` sub-tasks to gather evidence against each criterion. Each worker emits a structured `{criterion, passed, evidence, confidence}` result. Volume caps must be set via `LLMConfig.max_parallel_agents` and `max_chunks_per_agent`.
7. **Build verifier phase** — route all worker outputs to `runtime/loop_engine/loop_verifier.py` running `claude-opus-4-8`. The verifier must spawn at least two independent adversarial critics; approval requires agreement of ≥2 critics.
8. **Attach adjustment route** — if verifier rejects:
   - If `iteration_count < max_iterations`, route to `tooll_subagents/self_correction/plan_adjustment.md` with the verifier's gap analysis
   - If `iteration_count >= max_iterations` or the gap is fundamental, set `next_action=escalate_human`
9. **Enforce human zones** — if the goal implies `git push`, `deploy`, `rm -rf`, DB migrations, or other L2/L3 human-zone actions, insert `tooll_subagents/execution/human_approval.md` gates and cap `effective_trust_level` at `L2`.
10. **Validate plan** — ensure output formats chain correctly, volume caps exist, and the verifier receives all worker evidence.
11. **Set next action** — if goal is defined, budget is sufficient, and trust level is resolved, set `next_action=execute`; otherwise `ask_user` or `escalate_human`.
12. **Return** — emit `goal_plan`, `effective_trust_level`, `model_tier_plan`, `estimated_cost`, and `next_action`.

## Failure Modes

| Condition | Response |
|---|---|
| `goal` missing or unverifiable | `next_action=ask_user`; request explicit goal and criteria |
| Budget insufficient for even one verifier run | Propose cheaper goal, budget increase, or escalation |
| `control/loop_trust_levels.md` blocks requested level | Downgrade to `effective_trust_level`; if L1 insufficient, ask user |
| Verifier rejects but iterations remain | Route to `tooll_subagents/self_correction/plan_adjustment.md` |
| Verifier rejects and budget exhausted | `next_action=escalate_human` with full evidence package |
| Fewer than 2 critics agree on approval | Treat as rejection; require ≥2 critic agreement for approval |
| Human-zone action implied at L3 | Cap at L2 and insert `tooll_subagents/execution/human_approval.md` |
| Cost tracking unavailable | Estimate conservatively; flag gap in plan metadata |
