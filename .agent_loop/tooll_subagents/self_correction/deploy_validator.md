# Deploy Validator

## Role
Self-correction agent that validates the deploy execution report against the original requirements. Translates failed deploys, missing URLs, or unsafe dry-run overrides into concrete corrective actions for `plan_adjustment.md`.

## Contract

### Receives
- `deploy_requirements`: from `tooll_subagents/planning/deploy_planner.md`
- `deploy_integration_report`: from `tooll_subagents/execution/deploy_runtime_integrator.md`

### Returns
- `validation_report`: dict — {
  - `status`: enum (`passed`, `failed`, `needs_refinement`, `not_applicable`)
  - `violations`: list of { `type`, `severity`, `message`, `suggestion` }
  - `refinement_actions`: list[str]
}
- `next_phase_hint`: enum (`self_correction`, `execution`, `result`)

### Side effects
- No writes; emits refinement actions for `plan_adjustment.md`
- Logs to `audit_logger.md`

## Decision Flow

1. **Short-circuit if no requirements** — if `deploy_requirements.needs_deploy` is false, return `not_applicable`.
2. **Check command success** — `deploy_integration_report.success` must be true. If false, report command output as evidence.
3. **Check safety invariant** — if `deploy_requirements.dry_run` is true, verify `deploy_integration_report.dry_run` is also true; reject unsafe live deploys that bypassed approval.
4. **Check deploy URL** — for `vercel`/`netlify`, a URL should be extractable; if missing, flag as warning, not failure.
5. **Check build artifact presence** — for `generic` provider, verify `dist/` exists after build.
6. **Emit refinement actions** — command failures first, then missing artifacts, then URL warnings.
7. **Return report** with hint `execution` if violations exist, `result` if passed or dry-run completed.

## Failure Modes

| Condition | Response |
|---|---|
| DeployEngine not reachable | `failed`; action = verify runtime dependencies |
| Deploy command failed | `needs_refinement`; route to `deploy_runtime_integrator.md` |
| Dry-run safety violated | `failed`; route to `human_approval.md` |
| Generic provider missing dist/ | `needs_refinement`; action = run build first |
| URL missing for vercel/netlify | `warn`; continue with hint `result` |
| All checks pass | `passed`; hint `result` |
