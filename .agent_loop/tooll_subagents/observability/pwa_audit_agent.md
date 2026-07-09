# PWA Audit Agent

## Role
Observability agent that audits the final PWA implementation for manifest completeness, service-worker registration, offline support, and performance-budget compliance. Produces a structured report consumed by `tooll_subagents/result/action_report.md` and `safety-control/mutual_check/quality_assessor.md`.

## Contract

### Receives
- `pwa_requirements`: from `tooll_subagents/planning/pwa_requirements_analyst.md`
- `pwa_plan`: from `tooll_subagents/planning/pwa_optimizer.md`
- `pwa_integration_report`: from `tooll_subagents/execution/pwa_runtime_integrator.md`
- `validation_report`: from `tooll_subagents/self_correction/pwa_validator.md`
- `lighthouse_audit_report`: optional structured report from `tools_lighthouse/audit/` pipeline

### Returns
- `audit_report`: dict — {
  - `overall_status`: enum (`pass`, `warn`, `fail`)
  - `manifest_complete`: bool
  - `service_worker_present`: bool
  - `offline_page_present`: bool
  - `budget_status`: enum (`pass`, `warn`, `fail`)
  - `budget_violations_count`: int
  - `recommendations`: list[str]
}
- `next_phase_hint`: enum (`observability`, `result`)

### Side effects
- Writes audit record to `audit_logger.md`
- No code changes

## Decision Flow

1. **Check requirements coverage** — every enabled feature in `pwa_plan` must be reflected in `pwa_integration_report.files_written` or `files_modified`.
2. **Check manifest completeness** — verify required manifest keys and at least one icon.
3. **Check service-worker presence** — if enabled, `public/sw.js` must exist.
4. **Check offline page** — if enabled, `public/offline.html` must exist.
5. **Check budget** — `pass` if no violations; `warn` if violations are suggestions-only (e.g. image count); `fail` if JS/CSS exceeds budget by more than 2x.
6. **Check Lighthouse alignment** — if `lighthouse_audit_report` exists, Performance score must be 1.0 for `pass`; otherwise `warn`.
7. **Generate recommendations** — suggest image optimization, font subsetting, code splitting, or third-party reduction based on violations.
8. **Log to audit** — append findings to `audit_logger.md` with SHA-256 integrity.
9. **Return report** with hint `result`.

## Failure Modes

| Condition | Response |
|---|---|
| Required feature not implemented | `fail`; recommend re-run `pwa_runtime_integrator.md` |
| Manifest missing required keys | `fail`; route to `plan_adjustment.md` |
| Budget violation exceeds 2x threshold | `fail`; route to `plan_adjustment.md` |
| Lighthouse Performance score < 1.0 | `warn`; recommend runtime profiling |
| `audit_logger.md` unavailable | Keep report in memory; continue |
