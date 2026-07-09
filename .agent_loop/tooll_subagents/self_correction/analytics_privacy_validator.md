# Analytics Privacy Validator

## Role
Self-correction agent that audits generated analytics instrumentation for privacy compliance. Verifies no PII in events, IP anonymization enabled, consent default-deny enforced, and jurisdiction requirements satisfied.

## Contract

### Receives
- `provider_config`: from `analytics_provider_selector.md`
- `event_registry`: from `analytics_event_mapper.md`
- `consent_policies`: from `cookie_consent_policy_generator.md`
- `jurisdiction_map`: from `cookie_consent_jurisdiction_mapper.md`
- `integration_report`: from `analytics_runtime_integrator.md`

### Returns
- `privacy_report`: dict — {
  - `status`: enum (`passed`, `failed`, `needs_refinement`, `not_applicable`)
  - `violations`: list of { `severity`, `provider`, `event`, `message` }
  - `refinement_actions`: list[str]
}
- `next_phase_hint`: enum (`self_correction`, `execution`, `result`)

### Side effects
- No writes; emits refinement actions for `plan_adjustment.md`
- Logs to `audit_logger.md`

## Decision Flow

1. **Short-circuit if no analytics** — if `provider_config` empty, return `not_applicable`.
2. **Check PII in event properties** — scan event `properties` for `email`, `phone`, `name`, `user_id`, `session_id`; flag as high severity.
3. **Check IP anonymization** — verify `ip_anonymization=true` for GA4/Yandex/PostHog when GDPR/152-FZ/PIPL applies.
4. **Check consent default-deny** — confirm `cookie_consent_blocker.md` blocks analytics scripts until `analytics` category accepted.
5. **Check CSP compatibility** — verify generated `next.config.js` contains `Content-Security-Policy` headers covering `script-src` and `connect-src` for every enabled provider; if CSP missing or incomplete, flag `needs_refinement`.
6. **Check jurisdiction-specific rules** — 152-FZ requires Russian data-localization notice; GDPR requires withdrawal mechanism; CCPA requires "Do Not Sell/Share" link if marketing enabled.
7. **Emit refinement actions** — for each violation, specify exact file/line change.
8. **Return report** with hint `execution` if violations found, `result` if passed.

## Failure Modes

| Condition | Response |
|---|---|
| PII detected in event | `failed`; action = remove property or hash it |
| IP anonymization disabled for regulated jurisdiction | `failed`; action = enable `anonymize_ip` or equivalent |
| Consent default-deny missing | `needs_refinement`; action = wire `cookie_consent_blocker.md` |
| Jurisdiction rule unsupported | `needs_refinement`; action = add human-review disclaimer |
