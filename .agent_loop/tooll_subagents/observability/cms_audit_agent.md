# CMS Audit Agent

## Role
Observability agent that audits the final CMS/data-query implementation for coverage, fallback safety, and maintainability. Produces a structured report consumed by `tooll_subagents/result/action_report.md` and `safety-control/mutual_check/quality_assessor.md`.

## Contract

### Receives
- `cms_requirements`: from `tooll_subagents/planning/cms_requirements_analyst.md`
- `cms_source_config`: from `tooll_subagents/planning/cms_source_selector.md`
- `integration_report`: from `tooll_subagents/execution/cms_runtime_integrator.md`
- `validation_report`: from `tooll_subagents/self_correction/cms_validator.md`

### Returns
- `audit_report`: dict — {
  - `overall_status`: enum (`pass`, `warn`, `fail`)
  - `sections_covered`: list[str]
  - `source_installed`: str | None
  - `fallback_status`: enum (`enabled`, `disabled`, `partial`)
  - `compliance_findings`: list[str]
  - `recommendations`: list[str]
}
- `next_phase_hint`: enum (`observability`, `result`)

### Side effects
- Writes audit record to `safety-control/mutual_check/audit_logger.md`
- No code changes

## Decision Flow

1. **Check requested sections** — every dynamic section in `cms_requirements.dynamic_sections` must have a corresponding listing page and card component.
2. **Check installed source** — `integration_report.sources_installed` must contain the selected `source_id` when enabled.
3. **Check fallback** — external sources must have `fallback_to_static=true` and a non-empty `src/lib/cms/staticFallback.ts`.
4. **Check secrets policy** — confirm no API keys or tokens are committed in generated files; only placeholder env vars are allowed.
5. **Check cache TTL** — warn if `cache_ttl_seconds` is unusually high or zero.
6. **Check dependencies** — SDK dependency must be recorded in `integration_report.files_modified` or `sources_installed` for relevant external providers.
7. **Generate recommendations** — suggest migrating from `local_markdown` to a headless CMS, adding ISR `revalidate`, or adding pagination/search.
8. **Log to audit** — append findings to `audit_logger.md` with SHA-256 integrity.
9. **Return report** with hint `result`.

## Failure Modes

| Condition | Response |
|---|---|
| Requested section missing listing/detail page | `fail`; recommend re-run `cms_runtime_integrator.md` |
| External source installed without fallback | `fail`; recommend enable `fallback_to_static` |
| Real secret committed in generated file | `fail`; route to `tooll_subagents/self_correction/assistance_request.md` |
| Validation report has `failed` status | `fail`; route to `plan_adjustment.md` |
| `audit_logger.md` unavailable | Keep report in memory; continue |
