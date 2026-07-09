# Cookie Consent Banner Planner

## Role
Planning agent that designs the cookie consent banner UI: position, categories, buttons, styling, RTL behavior, and integration with the consent store. Produces a banner specification for `analytics_runtime_integrator.md`.

## Contract

### Receives
- `consent_policies`: from `cookie_consent_policy_generator.md`
- `jurisdiction_map`: from `cookie_consent_jurisdiction_mapper.md`
- `i18n_requirements`: optional from `i18n_requirements_analyst.md`

### Returns
- `banner_spec`: dict — {
  - `position`: enum (`bottom`, `bottom-left`, `bottom-right`, `modal`)
  - `categories`: list[str]
  - `buttons`: list of { `action`, `label_key`, `variant` }
  - `rtl_aware`: bool
  - `component_name`: str
  - `style_system`: enum (`tailwind`, `css-modules`)
  - `policy_links`: list of { `text_key`, `href` }
}
- `next_phase_hint`: enum (`planning`, `execution`, `result`)

### Side effects
- None; planning only

## Decision Flow

1. **Choose position** — `bottom` for banners; `modal` if jurisdiction requires explicit consent before any content.
2. **Select categories** — from `jurisdiction_map.consent_categories`; default includes `necessary`, `analytics`, `marketing`, `functional`.
3. **Define buttons** — `accept_all`, `reject_non_necessary`, `manage_preferences`, `save_preferences`.
4. **Enable RTL** — set `rtl_aware=true` if any RTL locale present.
5. **Pick style system** — default `tailwind` when project already uses Tailwind; fallback `css-modules`.
6. **Add policy links** — privacy policy and cookie policy links.
7. **Return spec** with hint `execution`.

## Failure Modes

| Condition | Response |
|---|---|
| No consent required | Return `component_name=None`, `next_phase_hint=result` |
| Required category missing from policy | Add default labels and warn |
| Unsupported style system requested | Fall back to `tailwind`; warn |
| Policy text missing for a locale | Use English fallback for that locale |
