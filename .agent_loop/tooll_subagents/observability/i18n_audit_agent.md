# i18n Audit Agent

## Role
Observability agent that audits the final i18n implementation for coverage, compliance, and quality. Produces a structured report consumed by `tooll_subagents/result/action_report.md` and `mutual_check/quality_assessor.md`.

## Contract

### Receives
- `i18n_requirements`: from `tooll_subagents/planning/i18n_requirements_analyst.md`
- `dictionaries`: from `tooll_subagents/planning/i18n_dictionary_generator.md`
- `integration_report`: from `tooll_subagents/execution/i18n_runtime_integrator.md`
- `missing_key_report`: from `tooll_subagents/self_correction/i18n_missing_key_guard.md`
- `rtl_report`: from `tooll_subagents/self_correction/i18n_rtl_validator.md`

### Returns
- `audit_report`: dict — {
  - `overall_status`: enum (`pass`, `warn`, `fail`)
  - `locale_coverage`: dict[str, int] — locale → key count
  - `compliance_findings`: list[str]
  - `quality_findings`: list[str]
  - `recommendations`: list[str]
}
- `next_phase_hint`: enum (`observability`, `result`)

### Side effects
- Writes audit record to `audit_logger.md`
- No code changes

## Decision Flow

1. **Check coverage** — every target locale must have the same key count as default locale (allowing fallback markers). Count per locale.
2. **Check compliance** — verify that jurisdiction requirements (GDPR/ePrivacy, 152-FZ, PIPL) map to correct locale list and privacy disclaimers.
3. **Check quality** — review `missing_key_report` and `rtl_report`; any unresolved missing keys or RTL issues downgrade status to `warn` or `fail`.
4. **Check consistency** — ensure `routing_plan.locales`, `dictionaries` keys, and middleware config align.
5. **Generate recommendations** — suggest locale switcher placement, RTL CSS improvements, and translation review workflow.
6. **Log to audit** — append findings to `audit_logger.md` with SHA-256 integrity.
7. **Return report** with hint `result` when audit complete.

## Failure Modes

| Condition | Response |
|---|---|
| Coverage gap > 5% of keys | `fail`; recommend re-run dictionary generation |
| Compliance jurisdiction unsupported | `warn`; add note requiring human review |
| Audit inputs contradictory | `warn`; log contradiction to `audit_logger.md` |
| `audit_logger.md` unavailable | Keep report in memory and continue; emit warning |
