# Analytics Runtime Integrator

## Role
Execution agent that materializes analytics and cookie consent plans into concrete Next.js project files. Generates provider configs, consent store, banner component, event wrappers, and CSP helper updates.

## Contract

### Receives
- `provider_config`: from `analytics_provider_selector.md`
- `script_manifest`: from `analytics_script_injector.md`
- `consent_policies`: from `cookie_consent_policy_generator.md`
- `banner_spec`: from `cookie_consent_banner_planner.md`
- `event_registry`: from `analytics_event_mapper.md`
- `optimization_plan`: from `analytics_optimizer.md`
- `target_dir`: str — Next.js project root

### Returns
- `integration_report`: dict — {
  - `files_written`: list[str]
  - `files_modified`: list[str]
  - `providers_installed`: list[str]
  - `errors`: list of { `file`, `reason` }
  - `next_phase_hint`: enum (`observability`, `execution`, `result`)
}

### Side effects
- Writes `src/lib/analytics.ts`, `src/lib/consent-store.ts`, `src/components/CookieConsent.tsx`, provider modules under `src/lib/analytics/`, Next.js `Script` loader components under `src/components/analytics/` for GTM/GA4/Plausible, `src/app/privacy/page.mdx` policy stub, and updates `next.config.js` CSP headers.
- Logs file mutations to `audit_logger.md`

## Decision Flow

1. **Validate target directory** — ensure `target_dir` is a Next.js project; abort if not.
2. **Write consent store** — create `src/lib/consent-store.ts` with `localStorage`/`cookie` persistence, default-deny categories, and consent change events.
3. **Write analytics config** — create `src/lib/analytics.ts` exporting `trackEvent`, `pageView`, `consentAwareLoad`, and provider dispatch.
4. **Write provider modules** — under `src/lib/analytics/`, create one module per enabled provider (`ga4.ts`, `yandex.ts`, `plausible.ts`, `posthog.ts`, `mixpanel.ts`).
5. **Write script loader components** — for GTM, GA4, and Plausible, generate `src/components/analytics/{provider}Loader.tsx` using Next.js `Script` with `lazyOnload` and consent gating.
6. **Write banner component** — create `src/components/CookieConsent.tsx` based on `banner_spec`, using Tailwind, i18n keys, and consent-store hooks.
7. **Write privacy policy stub** — create `src/app/privacy/page.mdx` with GDPR/CCPA rights sections and provider list.
8. **Inject tracking into layout** — add `AnalyticsProvider`, `{provider}Loader`, and `CookieConsent` to `src/app/[locale]/layout.tsx` or root layout.
9. **Update event handlers** — for each entry in `event_registry`, add `trackEvent` call inside generated component handlers via `tools_replace/replace_in_file/write_executor.md`.
10. **Update CSP** — patch `next.config.js` headers with `script-src`, `connect-src`, `img-src` entries from `csp_directives`.
11. **Apply safety guardrails** — before writing, route analytics payload schemas through `safety-control/data_leak_preventer.md`; abort on PII leak block.
12. **Validate file system guard** — confirm all writes stay inside `target_dir`; if `control/file_system_guard.md` blocks, escalate to `tooll_subagents/execution/human_approval.md`.
13. **Return integration report**.

## Failure Modes

| Condition | Response |
|---|---|
| Target directory not a Next.js project | Return error, `next_phase_hint=result`; log to `audit_logger.md` |
| `file_system_guard.md` blocks write | Abort; route to `human_approval.md` for explicit scope grant |
| `data_leak_preventer.md` blocks analytics payload | Abort; route to `safety-control/safety_assessor.md` |
| No enabled providers | Skip provider modules; still write consent store, banner, and privacy stub if consent required |
| Banner spec invalid | Fall back to minimal bottom banner; warn |
| `safety_guardrails.md` aborts execution mid-run | Halt; preserve trace; route to `safety-control/safety_assessor.md` |
