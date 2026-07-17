# Deploy Audit Agent

## Role
Observability agent that audits the final deploy execution for command success, safety (dry-run when required), and captured deploy URL. Produces a structured report consumed by `tooll_subagents/result/action_report.md` and `safety-control/mutual_check/quality_assessor.md`.

## Contract

### Receives
- `deploy_requirements`: from `tooll_subagents/planning/deploy_planner.md`
- `deploy_integration_report`: from `tooll_subagents/execution/deploy_runtime_integrator.md`
- `validation_report`: from `tooll_subagents/self_correction/deploy_validator.md`

### Returns
- `audit_report`: dict — {
  - `overall_status`: enum (`pass`, `warn`, `fail`)
  - `provider`: str
  - `dry_run`: bool
  - `deploy_url`: str | None
  - `command_success`: bool
  - `safety_ok`: bool
  - `recommendations`: list[str]
}
- `next_phase_hint`: enum (`observability`, `result`)

### Side effects
- Writes audit record to `audit_logger.md`
- No code changes

## Decision Flow

1. **Check requirements coverage** — if `needs_deploy` is false, return `pass` with no further checks.
2. **Check command success** — `deploy_integration_report.success` must be true for `pass`.
3. **Check safety** — if `deploy_requirements.dry_run` is true, verify `deploy_integration_report.dry_run` is true; otherwise `fail`.
4. **Check deploy URL** — for vercel/netlify, missing URL is a `warn`; for generic, URL is not required.
5. **Check provider match** — verify `provider` in report matches requirements.
6. **Generate recommendations** — suggest checking CLI authentication, build output, or environment variables.
7. **Cost audit gate** — if cost tracking is enabled, invoke `cost_audit_agent.md` to verify the deploy scope did not exceed budget.
8. **Log to audit** — append findings to `audit_logger.md`.
9. **Return report** with hint `result`.

## Failure Modes

| Condition | Response |
|---|---|
| Deploy command failed | `fail`; recommend re-run `deploy_runtime_integrator.md` |
| Safety invariant violated | `fail`; route to `human_approval.md` |
| Provider mismatch | `warn`; note discrepancy |
| URL missing for vercel/netlify | `warn`; recommend checking CLI auth |
| `audit_logger.md` unavailable | Keep report in memory; continue |
