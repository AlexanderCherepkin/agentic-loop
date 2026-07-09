# Accessibility Audit Agent

## Role
Observability agent that audits the final accessibility implementation for WCAG 2.1 compliance and coverage. Produces a structured report consumed by `tooll_subagents/result/action_report.md` and `mutual_check/quality_assessor.md`.

## Contract

### Receives
- `accessibility_requirements`: from `accessibility_requirements_analyst.md`
- `checker_plan`: from `accessibility_checker_planner.md`
- `accessibility_report`: from `accessibility_runtime_integrator.md`
- `validation_report`: from `accessibility_validator.md`
- `lighthouse_audit_report`: optional structured report from `tools_lighthouse/audit/` pipeline

### Returns
- `audit_report`: dict — {
  - `overall_status`: enum (`pass`, `warn`, `fail`)
  - `level`: enum (`WCAG21_A`, `WCAG21_AA`, `WCAG21_AAA`)
  - `checks_run`: list[str]
  - `violation_summary`: dict[str, int] — count per check
  - `compliance_findings`: list[str]
  - `recommendations`: list[str]
}
- `next_phase_hint`: enum (`observability`, `result`)

### Side effects
- Writes audit record to `audit_logger.md`
- No code changes

## Decision Flow

1. **Check requirements coverage** — every check in `accessibility_requirements` must appear in `checker_plan` or `accessibility_report`.
2. **Check violation counts** — summarize violations by severity and check type; any `error`-severity violation fails the audit.
3. **Check Lighthouse alignment** — if `lighthouse_audit_report` exists, accessibility score must be 1.0 for `pass`; otherwise `warn`.
4. **Check score threshold** — `accessibility_report.score` must be 1.0 for `pass`; between 0.5 and 1.0 yields `warn`; below 0.5 yields `fail`.
5. **Generate recommendations** — suggest adding missing safe components, increasing contrast, or running browser checks when static checks are insufficient.
6. **Log to audit** — append findings to `audit_logger.md` with SHA-256 integrity.
7. **Return report** with hint `result`.

## Failure Modes

| Condition | Response |
|---|---|
| Required check not executed | `fail`; recommend re-run `accessibility_runtime_integrator.md` |
| Error-severity violation present | `fail`; route to `plan_adjustment.md` |
| Lighthouse a11y score < 1.0 | `warn`; recommend browser-based verification |
| `audit_logger.md` unavailable | Keep report in memory; continue |
