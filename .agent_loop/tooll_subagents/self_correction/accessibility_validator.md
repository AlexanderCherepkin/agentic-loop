# Accessibility Validator

## Role
Self-correction agent that validates the accessibility audit report against the original requirements and decides whether generated front-end code needs refinement. Translates violations into concrete corrective actions for `plan_adjustment.md`.

## Contract

### Receives
- `accessibility_requirements`: from `accessibility_requirements_analyst.md`
- `checker_plan`: from `accessibility_checker_planner.md`
- `accessibility_report`: from `accessibility_runtime_integrator.md`
- `lighthouse_audit_report`: optional structured report from `tools_lighthouse/audit/` pipeline containing `category_scores` and `failure_summary`

### Returns
- `validation_report`: dict — {
  - `status`: enum (`passed`, `failed`, `needs_refinement`, `not_applicable`)
  - `violations`: list of { `severity`, `file`, `line`, `check`, `message`, `suggestion` }
  - `refinement_actions`: list[str]
}
- `next_phase_hint`: enum (`self_correction`, `execution`, `result`)

### Side effects
- No writes; emits refinement actions for `plan_adjustment.md`
- Logs to `audit_logger.md`

## Decision Flow

1. **Short-circuit if no requirements** — if `accessibility_requirements` is empty, return `not_applicable`.
2. **Check engine status** — if `accessibility_report.status=failed`, route to `assistance_request.md`.
3. **Cross-reference with Lighthouse** — if `lighthouse_audit_report` shows accessibility score < 1.0, merge failing audits into violations with severity `warning`.
4. **Evaluate violations** — for each violation, build a concrete refinement action referencing the file, line, and suggested fix.
5. **Apply level-specific thresholds** — for `WCAG21_AA`, block on contrast, focus visible, alt text, and heading hierarchy; for `WCAG21_A`, block on alt text and focus order only; for `WCAG21_AAA`, block additionally on AAA contrast.
6. **Emit refinement actions** — group by check type and prioritize `contrast` and `alt_text` fixes first.
7. **Return report** with hint `execution` if violations exist, `result` if passed.

## Failure Modes

| Condition | Response |
|---|---|
| AccessibilityEngine not reachable | `failed`; action = verify runtime dependencies |
| Critical violation unresolved | `needs_refinement`; route to `plan_adjustment.md` |
| Lighthouse a11y score < 1.0 with no engine violations | `needs_refinement`; action = run browser audit |
| All checks pass | `passed`; hint `result` |
