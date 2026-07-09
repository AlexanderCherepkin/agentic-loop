# Storybook Validator

## Role
Self-correction agent that validates the Storybook integration report against the original requirements and the generated project state. Translates missing stories or misconfigured Storybook setup into concrete corrective actions for `plan_adjustment.md`.

## Contract

### Receives
- `storybook_requirements`: from `tooll_subagents/planning/storybook_planner.md`
- `storybook_integration_report`: from `tooll_subagents/execution/storybook_runtime_integrator.md`

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

1. **Short-circuit if no requirements** — if `storybook_requirements.needs_storybook` is false, return `not_applicable`.
2. **Check Storybook config** — verify `.storybook/main.ts` and `.storybook/preview.ts` were written or pre-existed.
3. **Check stories coverage** — every discovered component in `storybook_integration_report.stories` must have a matching `.stories.tsx` file.
4. **Check package.json** — verify `storybook` and `build-storybook` scripts exist and required devDependencies are declared.
5. **Check excluded files** — ensure no stories were generated for `page.tsx`, `layout.tsx`, `loading.tsx`, `error.tsx`, or `not-found.tsx`.
6. **Emit refinement actions** — missing config first, then missing stories, then package.json issues.
7. **Return report** with hint `execution` if violations exist, `result` if passed.

## Failure Modes

| Condition | Response |
|---|---|
| StorybookEngine not reachable | `failed`; action = verify runtime dependencies |
| Storybook config missing | `needs_refinement`; route to `storybook_runtime_integrator.md` |
| Required story missing | `needs_refinement`; route to `storybook_runtime_integrator.md` |
| package.json scripts/devDeps missing | `needs_refinement`; route to `storybook_runtime_integrator.md` |
| Invalid story generated for page/layout | `needs_refinement`; action = remove invalid story |
| All checks pass | `passed`; hint `result` |
