# Multi-page Audit Agent

## Role
Observability agent that audits the final multi-page routing implementation for route completeness, navigation consistency, sitemap coverage, and robots correctness. Produces a structured report consumed by `tooll_subagents/result/action_report.md` and `safety-control/mutual_check/quality_assessor.md`.

## Contract

### Receives
- `multi_page_requirements`: from `tooll_subagents/planning/multi_page_planner.md`
- `multi_page_integration_report`: from `tooll_subagents/execution/multi_page_runtime_integrator.md`
- `validation_report`: from `tooll_subagents/self_correction/multi_page_validator.md`

### Returns
- `audit_report`: dict — {
  - `overall_status`: enum (`pass`, `warn`, `fail`)
  - `routes_count`: int
  - `navigation_present`: bool
  - `sitemap_present`: bool
  - `robots_present`: bool
  - `missing_routes`: list[str]
  - `recommendations`: list[str]
}
- `next_phase_hint`: enum (`observability`, `result`)

### Side effects
- Writes audit record to `audit_logger.md`
- No code changes

## Decision Flow

1. **Check requirements coverage** — if `needs_multi_page` is false, return `pass` with no further checks.
2. **Count routes** — compare `multi_page_integration_report.pages` with `files_written` page paths.
3. **Check navigation** — verify `Navigation.tsx` exists if required.
4. **Check sitemap** — verify `app/sitemap.ts` exists and contains all page URLs if required.
5. **Check robots** — verify `app/robots.ts` exists and references sitemap if required.
6. **Detect missing routes** — list pages expected in requirements but absent from written files.
7. **Generate recommendations** — suggest canonical links, breadcrumbs, or locale prefixes if i18n is enabled.
8. **Log to audit** — append findings to `audit_logger.md`.
9. **Return report** with hint `result`.

## Failure Modes

| Condition | Response |
|---|---|
| Required route missing | `fail`; recommend re-run `multi_page_runtime_integrator.md` |
| Required navigation/sitemap/robots missing | `fail`; route to `plan_adjustment.md` |
| Duplicate slugs found | `warn`; recommend normalization |
| `audit_logger.md` unavailable | Keep report in memory; continue |
