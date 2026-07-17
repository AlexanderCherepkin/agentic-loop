# Anti-Slop Validator

## Role
Hard-gate validator that inspects a premium design system's `DESIGN.md` and `design_tokens.json` against deterministic anti-slop rules. A fail verdict blocks handoff to code agents and emits structured refinement actions.

## Contract

### Receives
- `design_system_package`: from `tooll_subagents/planning/premium_design_system_generator.md`
- `premium_design_proposal`: confirmed proposal from `tooll_subagents/planning/premium_design_analyst.md`
- `forbidden_fonts`: list from project memory / policy
- `allowed_fonts`: list from project memory / policy

### Returns
- `anti_slop_report`: structured object:
  - `verdict`: enum (`pass`, `fail`)
  - `checks`: list of 10 checks with `id`, `name`, `status`, `reason`
  - `refinement_actions`: list of concrete fixes when `status=fail`
  - `blocked`: boolean — true if code handoff must not proceed
  - `notes`: optional context
- `next_phase_hint`: enum (`planning`, `execution`, `result`) — `execution` only when `verdict=pass`

### Side effects
- Logs verdict to `audit_logger.md`
- Updates `design_tokens.json` `anti_slop.verdict` field when it passes
- Triggers `plan_adjustment.md` when `verdict=fail`

## Decision Flow

1. **Load artifacts** — read `DESIGN.md` and `design_tokens.json`. If either is missing, fail immediately with `blocked=true`.
2. **Run 10 hard-gate checks**:
   1. **Fonts** — no forbidden font appears; base UI font is not Inter/Roboto/Arial/Space Grotesk/Open Sans/Helvetica/Segoe UI/San Francisco/Myriad Pro/Calibri/Verdana/Century Gothic.
   2. **Card shadows** — no standard decorative shadows (`0 4px 6px`, `0 10px 15px`, etc.) in tokens or prose. Focus/elevation shadows are allowed if explicitly justified.
   3. **Centered buttons** — `DESIGN.md` components section must not specify "centered CTA" without hierarchy/asymmetry rationale. Brutalist asymmetry is the only accepted default for centered buttons.
   4. **Gradient blobs** — no meaningless background gradient blobs in color system or mood. Gradients must serve a function (heatmap, depth, data viz).
   5. **Uniform padding** — spacing scale must have ≥ 3 distinct rhythmic levels; no one-size-fits-all section padding.
   6. **Generic 3-column** — if a 3-column layout is mentioned, it must include asymmetric grid or intentional disruption rule; otherwise fail.
   7. **Gray on white** — body text color must not be flat mid-gray (`#666`–`#999`) on `#ffffff`. Accept off-white base, warm/cool gray, or inverted.
   8. **Layout animations** — motion tokens must forbid animating `width`/`height`/`top`/`left`. Only `transform`, `opacity`, `filter`, `clip-path` allowed.
   9. **Hover banality** — component concepts must require more than `opacity: 0.8` on hover; must include transform, color shift, or underline logic.
   10. **Mass fade-in** — scroll animations must be staggered/transform-based with easing; no blanket fade-in of all content.
3. **Aggregate verdict** — any `fail` check makes overall `verdict=fail` and `blocked=true`.
4. **Build refinement_actions** — for each failed check, emit a concrete instruction (e.g. "Replace Inter with Adisan Richard in base_ui font", "Remove `box-shadow: 0 4px 6px` from card concept", "Add asymmetric grid rule to 3-column layout").
5. **Update tokens** — if pass, set `design_tokens.json` `anti_slop.verdict=pass` and append check list.
6. **Return** — emit report. If fail, route to `tooll_subagents/self_correction/plan_adjustment.md`. If pass, route to `execution` or to `tooll_subagents/planning/design_to_code_planner.md` depending on context.

## Failure Modes

| Condition | Response |
|---|---|
| DESIGN.md or design_tokens.json missing | `verdict=fail`, `blocked=true`, `refinement_action=generate missing artifact` |
| Forbidden font found | `fail`; action = replace with allowed font from [[allowed-fonts]] |
| User explicitly overrides an anti-slop rule | Log override; require `human_approval.md` for the exception; otherwise keep fail |
| Check logic is ambiguous | Default to fail-safe (stricter) interpretation |
| Validator cannot parse tokens | `fail`; action = re-run `premium_design_system_generator.md` |
| All checks pass but contrast is borderline | Add warning note; do not block if tokens pass numeric threshold |
