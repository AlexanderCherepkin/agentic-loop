# Cookie Consent Policy Generator

## Role
Planning agent that generates cookie consent policy text and banner copy for all target locales. Produces localized dictionaries consumed by `cookie_consent_banner_planner.md` and `analytics_runtime_integrator.md`.

## Contract

### Receives
- `jurisdiction_map`: from `cookie_consent_jurisdiction_mapper.md`
- `i18n_requirements`: from `i18n_requirements_analyst.md`
- `provider_config`: from `analytics_provider_selector.md`

### Returns
- `consent_policies`: dict[str, dict] — locale → {
  - `banner_title`: str
  - `banner_description`: str
  - `accept_label`: str
  - `reject_label`: str
  - `manage_label`: str
  - `save_label`: str
  - `category_labels`: dict[str, str]
  - `privacy_link_text`: str
  - `required_disclaimers`: list[str]
}
- `next_phase_hint`: enum (`planning`, `execution`, `result`)

### Side effects
- May call LLM for locale-aware phrasing
- No filesystem writes

## Decision Flow

1. **Determine target locales** — use `i18n_requirements.target_locales` or `["en"]` if none.
2. **Build base template** — title, description, accept/reject/manage/save labels, category labels.
3. **Localize per locale** — translate base template while preserving legal meaning and default-deny stance. For Russian and Chinese, add jurisdiction-specific disclaimers.
4. **Inject provider names** — mention enabled providers in description (e.g., "Google Analytics and Yandex.Metrica").
5. **Add required disclaimers** — based on `jurisdiction_map.required_disclaimers`.
6. **Return policies** with hint `planning` when banner planner follows, `execution` if direct integration.

## Failure Modes

| Condition | Response |
|---|---|
| LLM unavailable | Return English policies for all locales; warn |
| Jurisdiction requires disclaimer not in template | Add generic disclaimer and flag for human review |
| Provider list empty | Keep generic description without provider names |
| Translation output malformed | Fall back to English for that locale; warn |
