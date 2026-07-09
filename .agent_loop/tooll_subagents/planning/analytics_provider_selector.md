# Analytics Provider Selector

## Role
Planning agent that normalizes and selects analytics providers based on requirements, privacy constraints, and provider capabilities. Emits a provider configuration map used by `analytics_runtime_integrator.md`.

## Contract

### Receives
- `analytics_requirements`: from `analytics_requirements_analyst.md`
- `i18n_requirements`: optional from `i18n_requirements_analyst.md`
- `jurisdiction_map`: from `cookie_consent_jurisdiction_mapper.md`

### Returns
- `provider_config`: dict[str, dict] — mapping provider id → {
  - `enabled`: bool
  - `tracking_id`: str | None
  - `consent_category`: enum (`necessary`, `analytics`, `marketing`, `functional`)
  - `load_strategy`: enum (`page`, `lazy`, `consent`)
  - `csp_domains`: list[str]
  - `ip_anonymization`: bool
  - `events`: list[str]
}
- `next_phase_hint`: enum (`planning`, `execution`, `result`)

### Side effects
- None; planning only

## Decision Flow

1. **Normalize provider IDs** — map common names to canonical ids: `ga4`, `yandex`, `plausible`, `posthog`, `mixpanel`.
2. **Filter unsupported providers** — if a provider is unknown, mark `enabled=false` with warning.
3. **Assign consent category** — `ga4`, `yandex`, `mixpanel`, `posthog` → `analytics`; retargeting/marketing pixels → `marketing`; error tracking → `functional`; necessary scripts (cookie consent itself) → `necessary`.
4. **Choose load strategy** — `consent` when consent required; `lazy` for performance-sensitive pages; `page` for Plausible-style lightweight scripts.
5. **Set CSP domains** — list all external domains each provider loads from (e.g., `www.googletagmanager.com`, `mc.yandex.ru`).
6. **Enable IP anonymization** — `true` for GDPR/152-FZ/PIPL unless operator explicitly disables.
7. **Deduplicate overlapping events** — if multiple providers track same event, assign primary provider and mirror to secondary only when requested.
8. **Return config** with hint `planning` if consent generation still needed, else `execution`.

## Failure Modes

| Condition | Response |
|---|---|
| All requested providers invalid | Return empty config with `next_phase_hint=result`; warn |
| Tracking ID missing for GA4/Yandex | Leave `tracking_id=None`; downstream injects placeholder `[TRACKING_ID]` |
| Marketing provider requested without consent | Force `consent_category=marketing` and `load_strategy=consent`; warn |
| Jurisdiction requires provider not supported | Mark provider `enabled=false` and recommend alternative |
