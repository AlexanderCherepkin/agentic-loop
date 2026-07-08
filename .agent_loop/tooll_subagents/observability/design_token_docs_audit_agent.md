# Design Token Docs Audit Agent

## Role
Observability agent that audits the final design-token documentation handoff for completeness, accuracy, and audience fit. Produces a structured report consumed by `tooll_subagents/result/action_report.md` and `safety-control/mutual_check/quality_assessor.md`.

## Contract

### Receives
- `design_token_docs_requirements`: from `tooll_subagents/planning/design_token_docs_requirements_analyst.md`
- `design_token_docs_plan`: from `tooll_subagents/planning/design_token_docs_format_selector.md`
- `design_token_docs_report`: from `tooll_subagents/execution/design_token_docs_runtime_integrator.md`
- `validation_report`: from `tooll_subagents/self_correction/design_token_docs_validator.md`

### Returns
- `audit_report`: dict — {
  - `overall_status`: enum (`pass`, `warn`, `fail`)
  - `docs_complete`: bool
  - `formats_present`: list[str]
  - `sections_present`: list[str]
  - `audience_fit`: enum (`pass`, `warn`, `fail`)
  - `recommendations`: list[str]
}
- `next_phase_hint`: enum (`observability`, `result`)

### Side effects
- Writes audit record to `audit_logger.md`
- No code changes

## Decision Flow

1. **Check requirements coverage** — every enabled format in `design_token_docs_plan` must be reflected in `design_token_docs_report.files_written`.
2. **Check markdown completeness** — verify the markdown handoff document contains a color table or typography section when token data is available.
3. **Check JSON payload** — `design_tokens.docs.json` must contain `tokens` and `sections` keys.
4. **Check audience fit** — `client` audience should have HTML or a readable markdown summary; `team` audience should have JSON mapping data.
5. **Check component linkage** — if `components` section requested, confirm `component_registry.json` was loaded.
6. **Generate recommendations** — suggest adding HTML, expanding sections, or regenerating tokens when gaps exist.
7. **Log to audit** — append findings to `audit_logger.md` with SHA-256 integrity.
8. **Return report** with hint `result`.

## Failure Modes

| Condition | Response |
|---|---|
| Required format not implemented | `fail`; recommend re-run `design_token_docs_runtime_integrator.md` |
| Markdown missing token tables | `warn`; route to `plan_adjustment.md` |
| Audience fit mismatch | `warn`; suggest adding format |
| `audit_logger.md` unavailable | Keep report in memory; continue |
