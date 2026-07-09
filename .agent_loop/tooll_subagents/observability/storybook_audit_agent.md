# Storybook Audit Agent

## Role
Observability agent that audits the final Storybook implementation for config completeness, stories coverage, and package.json setup. Produces a structured report consumed by `tooll_subagents/result/action_report.md` and `safety-control/mutual_check/quality_assessor.md`.

## Contract

### Receives
- `storybook_requirements`: from `tooll_subagents/planning/storybook_planner.md`
- `storybook_integration_report`: from `tooll_subagents/execution/storybook_runtime_integrator.md`
- `validation_report`: from `tooll_subagents/self_correction/storybook_validator.md`

### Returns
- `audit_report`: dict — {
  - `overall_status`: enum (`pass`, `warn`, `fail`)
  - `config_present`: bool
  - `stories_count`: int
  - `expected_stories_count`: int
  - `package_json_updated`: bool
  - `recommendations`: list[str]
}
- `next_phase_hint`: enum (`observability`, `result`)

### Side effects
- Writes audit record to `audit_logger.md`
- No code changes

## Decision Flow

1. **Check requirements coverage** — if `needs_storybook` is false, return `pass` with no further checks.
2. **Check config** — verify `.storybook/main.ts` and `.storybook/preview.ts` exist.
3. **Count stories** — compare `stories_count` with expected components discovered by engine.
4. **Check package.json** — verify Storybook scripts and devDependencies are present.
5. **Check quality** — ensure no stories exist for Next.js-only files (page/layout/loading/error/not-found).
6. **Generate recommendations** — suggest adding controls/argTypes or auto-generated docs if components expose props.
7. **Log to audit** — append findings to `audit_logger.md`.
8. **Return report** with hint `result`.

## Failure Modes

| Condition | Response |
|---|---|
| Storybook config missing | `fail`; recommend re-run `storybook_runtime_integrator.md` |
| Stories count < expected | `warn`; recommend re-run discovery |
| package.json scripts/devDeps missing | `fail`; route to `plan_adjustment.md` |
| Invalid stories for page/layout | `warn`; recommend cleanup |
| `audit_logger.md` unavailable | Keep report in memory; continue |
