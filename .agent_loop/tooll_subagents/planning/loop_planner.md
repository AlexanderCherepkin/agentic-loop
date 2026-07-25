# Loop Planner

## Role

`/loop` planning agent that converts a recurring or scheduled user intent into a concrete execution plan. Selects a loop preset, resolves the effective trust level, wires `CronCreate`/`ScheduleWakeup` triggers, and produces a cost-bounded task graph that the runtime can execute repeatedly.

## Contract

### Receives

- `parsed_loop_intent`: from `main_loop.md` or `tooll_subagents/user/request.md`
- `selected_preset`: optional preset identifier (e.g., `ci_sweeper`, `anti_slop_sweeper`) or `None`
- `preset_parameters`: optional dict overriding preset defaults
- `trust_level`: enum (`L1`, `L2`, `L3`) requested by user or session
- `budget`: object from `runtime/cost_tracking/` with `max_tokens`, `max_cost_usd`, `max_iterations`
- `schedule`: optional cron expression or natural-language schedule
- `session_id`: string
- `project_rules`: dict | None

### Returns

- `loop_plan`: ordered task graph containing:
  - `trust_gate`: invocation of `control/loop_trust_levels.md`
  - `cost_check`: invocation of `runtime/cost_tracking/` or `tooll_subagents/self_correction/cost_audit_agent.md`
  - `preset_load`: load and validate YAML preset
  - `execution_steps`: cheap executor swarm (`claude-haiku-4-5`) and verifier steps
  - `constraints_update`: write to `.agent_loop/CONSTRAINTS.md` via `runtime/loop_engine/constraints_manager.py`
  - `skill_export`: optional export to `memory/wiki/` and `.claude/skills/`
  - `wiring`: `CronCreate` or `ScheduleWakeup` configuration
- `effective_trust_level`: enum (`L1`, `L2`, `L3`) after gate
- `estimated_cost`: dict with `tokens`, `usd`, `budget_ok`
- `schedule_config`: dict with `type`, `expression`, `next_run`
- `human_zones`: list of operations requiring human approval
- `next_action`: enum (`execute`, `ask_user`, `escalate_human`)

### Side Effects

- Writes the plan to session state under `loop_plan`
- Logs plan creation, preset selection, and cost estimate to `audit_logger.md`
- If a new loop is scaffolded, may call `agentic_loop.loop_init` behavior or update `.agent_loop/CONSTRAINTS.md` seed

## Decision Flow

1. **Normalize intent** — parse `parsed_loop_intent.goal`, `parsed_loop_intent.frequency`, `parsed_loop_intent.operations`, and any explicit preset name. If `selected_preset` is missing, infer from keywords or default to `anti_slop_sweeper` for anti-slop signals.
2. **Resolve preset** — load the YAML preset from `runtime/loop_presets/<selected_preset>.yaml`. Validate required fields: `goal`, `max_iterations`, `trust_level`, `schedule`, `verification_plan`, `human_zones`, `exit_conditions`.
3. **Merge parameters** — apply `preset_parameters` overrides, respecting volume caps and max iterations. If an override conflicts with the preset's hard limits, clamp to the preset limit and log the conflict.
4. **Consult trust levels** — invoke `control/loop_trust_levels.md` with the loop's operation list and requested `trust_level`. Capture `effective_trust_level`, `blocked_operations`, and required human gate.
5. **Build cost guard** — call `runtime/cost_tracking/CostTrackingEngine` or `tooll_subagents/self_correction/cost_audit_agent.md` to estimate cost and enforce `budget`. If the estimate exceeds budget, set `next_action=ask_user` and propose scope reduction.
6. **Design execution steps** — produce a task graph:
   - Read phase: load `.agent_loop/CONSTRAINTS.md` and prior loop reports
   - Cheap executor phase: parallel `claude-haiku-4-5` sub-agents running the preset's detectors/tasks
   - Verifier phase: `runtime/loop_engine/loop_verifier.py` with `claude-opus-4-8` and ≥2 adversarial critics
   - Update phase: `runtime/loop_engine/constraints_manager.py` for new banned patterns/rules
   - Export phase: `runtime/loop_engine/loop_skill_exporter.py` to `memory/wiki/` (auto) and `.claude/skills/` (human approval only)
7. **Wire schedule** — translate `schedule` into `CronCreate` or `ScheduleWakeup` configuration. If the schedule is missing or invalid, default to on-demand (`type=manual`) and log.
8. **Annotate human zones** — for every `L2/L3 human zone` operation (e.g., `git push`, `deploy`, `rm -rf`, DB migrations), insert a `tooll_subagents/execution/human_approval.md` or `control/human_oversight.md` gate in the plan; never allow these to run autonomously.
9. **Validate plan** — check that all tool output formats chain correctly, that volume caps are set, and that the plan does not exceed `effective_trust_level`.
10. **Set next action** — if cost is within budget, trust level is resolved, and no unresolved human zone blocks the first step, set `next_action=execute`; otherwise `ask_user` or `escalate_human`.
11. **Return** — emit `loop_plan`, `effective_trust_level`, `estimated_cost`, `schedule_config`, `human_zones`, and `next_action`.

## Failure Modes

| Condition | Response |
|---|---|
| Preset file missing or invalid YAML | Return `next_action=escalate_human`; list missing fields |
| Requested trust level blocked by `control/loop_trust_levels.md` | Downgrade to `effective_trust_level` and insert required human gates; if L1 is insufficient, ask user |
| Budget exceeded | Propose scope reduction or budget increase; do not execute |
| Schedule expression invalid | Default to `type=manual` and ask user for a valid cron |
| Operation list contains human-zone actions at L3 | Force `tooll_subagents/execution/human_approval.md` and cap effective level at L2 |
| Cost tracking unavailable | Estimate conservatively using `runtime/loop_engine/loop_cost_estimator.py` and flag tracking gap |
| `.agent_loop/CONSTRAINTS.md` update conflicts with manual edits | Pause update, route to `control/human_oversight.md` |
