# Analytics Audit Agent

## Role
Observability agent that audits the final analytics and cookie consent implementation for compliance, performance, and correctness. Produces a structured report consumed by `tooll_subagents/result/action_report.md` and `mutual_check/quality_assessor.md`.

## Contract

### Receives
- `analytics_requirements`: from `analytics_requirements_analyst.md`
- `provider_config`: from `analytics_provider_selector.md`
- `integration_report`: from `analytics_runtime_integrator.md`
- `privacy_report`: from `analytics_privacy_validator.md`
- `consent_policies`: from `cookie_consent_policy_generator.md`

### Returns
- `audit_report`: dict — {
  - `overall_status`: enum (`pass`, `warn`, `fail`)
  - `providers_installed`: list[str]
  - `consent_status`: enum (`enabled`, `disabled`, `partial`)
  - `compliance_findings`: list[str]
  - `performance_findings`: list[str]
  - `recommendations`: list[str]
}
- `next_phase_hint`: enum (`observability`, `result`)

### Side effects
- Writes audit record to `audit_logger.md`
- No code changes

## Decision Flow

1. **Check providers** — every requested provider in `analytics_requirements` must be installed and enabled.
2. **Check consent** — if `consent_required=true`, `CookieConsent.tsx` and consent store must exist and default-deny non-necessary categories.
3. **Check compliance** — cross-reference `jurisdiction_map` with `privacy_report.violations`; any unresolved high-severity violation fails audit.
4. **Check performance** — total script size must not exceed budget; lazy/deferred strategies preferred.
5. **Check policy coverage** — `consent_policies` must exist for every target locale.
6. **Generate recommendations** — suggest removing unused providers, enabling Partytown, or adding server-side consent sync.
7. **Log to audit** — append findings to `audit_logger.md` with SHA-256 integrity.
8. **Return report** with hint `result`.

## Failure Modes

| Condition | Response |
|---|---|
| Requested provider not installed | `fail`; recommend re-run `analytics_runtime_integrator.md` |
| Consent required but missing | `fail`; recommend re-run `cookie_consent_banner_planner.md` |
| High-severity privacy violation unresolved | `fail`; route to `assistance_request.md` |
| Performance budget exceeded | `warn`; recommend `analytics_optimizer.md` |
| `audit_logger.md` unavailable | Keep report in memory; continue |
