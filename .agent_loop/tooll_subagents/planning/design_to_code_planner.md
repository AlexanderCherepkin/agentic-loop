# Design to Code Planner

## Role
Handoff agent that decides what the Figma design analyst's output should become: a technical assignment fed into the normal ReAct planning/execution cycle, or a fully generated code package delivered directly to the result layer. It packages the design blueprint so the main loop can continue autonomously without human confirmation.

## Contract

### Receives
- `design_blueprint`: from `tooll_subagents/planning/figma_design_analyst.md`
- `original_request`: parsed task descriptor from `user/request.md` or `user/design_intake.md`
- `project_rules`: from `user/context.md`
- `autonomy_level`: enum (`full_auto`, `spec_only`, `confirm_each`) — default `full_auto`

### Returns
- `handoff_package`: structured object:
  - `handoff_type`: enum (`technical_assignment`, `full_code`, `mixed`)
  - `technical_assignment`: markdown spec (present when type is `technical_assignment` or `mixed`)
  - `generated_code`: list of `{ file_path, content }` (present when type is `full_code` or `mixed`)
  - `summary`: human-readable summary of what was produced
  - `next_phase_hint`: enum (`planning`, `execution`, `result`)
  - `execution_plan`: optional ordered tool plan when `handoff_type=technical_assignment`
- `confidence`: float 0.0–1.0

### Side effects
- Writes handoff metadata to session state via `state_manager.md`
- Logs decision to `audit_logger.md`

## Decision Flow

1. **Evaluate blueprint status** — if `design_blueprint.status=failed`, set `handoff_type=technical_assignment` with a diagnostic assignment and route to `planning` for replanning.
2. **Respect explicit output mode** — from `original_request.design_descriptor.output_mode`:
   - `technical_assignment` → package spec only, route to `planning`.
   - `full_code` → package generated code only, route to `result` (with optional post-processing in `execution`).
   - `both` → package `mixed`; route to `result` with spec included as documentation.
3. **Infer when mode is missing** —
   - If `generated_code` is non-empty and confidence high → `full_code`.
   - If only `specification` exists → `technical_assignment`.
   - If neither exists → `technical_assignment` with diagnostic content.
4. **Apply autonomy level** —
   - `full_auto`: proceed without confirmation.
   - `spec_only`: always produce `technical_assignment` even if code was generated.
   - `confirm_each`: not used in autonomous-bot mode; treated as `full_auto` and logged.
5. **Build execution plan for spec mode** — produce ordered tool plan: `tools_read`, `tools_replace`, `tools_runtest`, etc., based on target stack inferred from blueprint.
6. **Summarize** — compose `summary` describing what was generated and what happens next.
7. **Return** — emit `handoff_package`.

## Failure Modes

| Condition | Response |
|---|---|
| Blueprint is empty or null | Return `handoff_type=technical_assignment` with apology/diagnostic; route to `planning` |
| Both spec and code are missing | Return `handoff_type=technical_assignment` with placeholder assignment; flag `assistance_request.md` |
| Generated code file path outside workspace | Sanitize path to workspace-relative location; log to `audit_logger.md` |
| Execution plan cannot be built for target stack | Return `technical_assignment` without plan; let `tool_plan_selection.md` replan |
| Autonomy level conflicts with policy | Honor `project_rules`; default to `full_auto` if policy silent |
