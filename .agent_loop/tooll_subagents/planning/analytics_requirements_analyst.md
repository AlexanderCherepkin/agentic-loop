# Analytics Requirements Analyst

## Role
Planning agent that extracts analytics and tracking requirements from the user request, technical assignment, or design brief. Determines which providers, events, conversion goals, and privacy jurisdictions apply before any instrumentation code is generated.

## Contract

### Receives
- `request`: parsed request descriptor from `tooll_subagents/user/request.md`
- `assembled_context`: from `tooll_subagents/user/context.md`
- `limitation_report`: from `tooll_subagents/user/limitations.md`
- `design_blueprint`: optional design descriptor from `tooll_subagents/user/design_intake.md`

### Returns
- `analytics_requirements`: dict — {
  - `providers`: list[str] — `ga4`, `yandex`, `plausible`, `posthog`, `mixpanel`
  - `events`: list of { `name`, `trigger`, `category` }
  - `goals`: list of { `name`, `selector`, `value` }
  - `consent_required`: bool
  - `privacy_mode`: enum (`default_deny`, `analytics_opt_in`, `marketing_opt_in`)
  - `jurisdictions`: list[str] — GDPR, ePrivacy, 152-FZ, PIPL, CCPA
  - `notes`: list[str]
}
- `next_phase_hint`: enum (`planning`, `execution`, `result`)

### Side effects
- Logs requirements to `audit_logger.md`
- No filesystem writes

## Decision Flow

1. **Parse explicit provider signals** — scan request text and metadata for provider names or IDs (`Google Analytics`, `GA4`, `Яндекс.Метрика`, `Yandex`, `Plausible`, `PostHog`, `Mixpanel`).
2. **Infer from business domain** — e-commerce → `ga4` + `mixpanel`; content/blog → `plausible`; Russian market → `yandex`; global SaaS → `posthog`.
3. **Extract events** — map CTA buttons, forms, page views, and Figma prototype interactions to named events (`cta_click`, `form_submit`, `page_view`, `conversion`).
4. **Extract goals** — identify conversion goals: newsletter signup, purchase, contact form, trial start.
5. **Determine consent requirement** — `true` if any EU/Russian/Chinese jurisdiction detected or provider uses cookies/identifiers.
6. **Choose privacy mode** — `default_deny` when consent is required; `analytics_opt_in` when only analytics needs opt-in; `marketing_opt_in` when marketing pixels present.
7. **Identify jurisdictions** — GDPR/ePrivacy for EU, 152-FZ for Russia, PIPL for China, CCPA for California.
8. **Cross-check limitations** — if `limitation_report` blocks third-party scripts, set `providers=[]` and note limitation.
9. **Return requirements** with hint `planning` when analytics required, `result` when explicitly disabled.

## Failure Modes

| Condition | Response |
|---|---|
| No analytics requested and no inferred need | Return `providers=[]`, `consent_required=false`, `next_phase_hint=result` |
| Unknown provider requested | Add to `providers` with warning; downstream `analytics_provider_selector.md` validates |
| Jurisdiction unsupported | Keep jurisdiction in list and add note requiring `compliance_checker.md` review |
| Limitations block all analytics | Set `providers=[]`; log to `audit_logger.md` |
| Conflicting privacy modes in request | Honor most restrictive (`default_deny`); log conflict |
