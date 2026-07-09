# Multi-page Validator

## Role
Self-correction agent that validates the multi-page routing integration report against the original requirements and the generated project state. Translates missing routes or navigation/sitemap/robots gaps into concrete corrective actions for `plan_adjustment.md`.

## Contract

### Receives
- `multi_page_requirements`: from `tooll_subagents/planning/multi_page_planner.md`
- `multi_page_integration_report`: from `tooll_subagents/execution/multi_page_runtime_integrator.md`

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

1. **Short-circuit if no requirements** — if `multi_page_requirements.needs_multi_page` is false, return `not_applicable`.
2. **Check required page routes** — every page slug in requirements must have a matching written `app/[slug]/page.tsx` (or `app/page.tsx` for `home`).
3. **Check navigation component** — if `generate_navigation` is true, verify `app/components/Navigation.tsx` was written.
4. **Check sitemap** — if `generate_sitemap` is true, verify `app/sitemap.ts` exists and references all pages.
5. **Check robots** — if `generate_robots` is true, verify `app/robots.ts` exists and points to sitemap.
6. **Check slug collisions** — detect duplicate or invalid slugs in written pages.
7. **Emit refinement actions** — missing routes first, then missing routing artifacts.
8. **Return report** with hint `execution` if violations exist, `result` if passed.

## Failure Modes

| Condition | Response |
|---|---|
| MultiPageEngine not reachable | `failed`; action = verify runtime dependencies |
| Required page route missing | `needs_refinement`; route to `multi_page_runtime_integrator.md` |
| Navigation/sitemap/robots missing | `needs_refinement`; route to `multi_page_runtime_integrator.md` |
| Duplicate or invalid slugs | `needs_refinement`; action = deduplicate/normalize slugs |
| All checks pass | `passed`; hint `result` |
