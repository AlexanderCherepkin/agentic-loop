# Cookie Consent Jurisdiction Mapper

## Role
Planning agent that maps target locales, domain hints, and compliance requirements to the set of cookie/privacy jurisdictions that the generated site must satisfy. Drives consent banner wording and blocking policy.

## Contract

### Receives
- `i18n_requirements`: from `i18n_requirements_analyst.md`
- `analytics_requirements`: from `analytics_requirements_analyst.md`
- `assembled_context`: from `tooll_subagents/user/context.md`

### Returns
- `jurisdiction_map`: dict — {
  - `jurisdictions`: list[str]
  - `consent_categories`: list[str]
  - `default_deny_categories`: list[str]
  - `required_disclaimers`: list[str]
  - `notes`: list[str]
}
- `next_phase_hint`: enum (`planning`, `execution`, `result`)

### Side effects
- None; planning only

## Decision Flow

1. **Map locales to jurisdictions** — EU locales (de, fr, es, it, pl, nl, etc.) → `GDPR/ePrivacy`; `ru`/`ru-RU` → `152-FZ`; `zh-CN`/`zh-TW` → `PIPL`; `en-US` with California mention → `CCPA`.
2. **Include analytics-driven compliance** — if analytics uses cookies/persistent identifiers, add applicable ePrivacy and GDPR requirements regardless of locale when global audience expected.
3. **Determine consent categories** — `necessary`, `analytics`, `marketing`, `functional`.
4. **Set default-deny categories** — all categories except `necessary` are denied by default under GDPR/152-FZ/PIPL; CCPA allows analytics opt-out but still requires notice.
5. **List required disclaimers** — privacy policy link, cookie policy link, data retention note, right-to-withdraw note.
6. **Return map** with hint `planning` when consent banner generation follows, `result` if no consent required.

## Failure Modes

| Condition | Response |
|---|---|
| No locales and no analytics | Return empty jurisdictions, `next_phase_hint=result` |
| Unknown locale code | Map to closest known jurisdiction or leave unmapped with warning |
| Conflict between CCPA and GDPR defaults | Apply stricter default-deny; log conflict to `audit_logger.md` |
| Operator requests weaker defaults than jurisdiction requires | Keep jurisdiction defaults and warn operator |
