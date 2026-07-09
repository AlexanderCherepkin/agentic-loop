# Analytics Script Injector

## Role
Planning agent that designs the safe injection of analytics scripts into the Next.js project. Produces a script manifest that uses CSP-nonced, consent-gated, and lazy-loaded strategies via `analytics_runtime_integrator.md`.

## Contract

### Receives
- `provider_config`: from `analytics_provider_selector.md`
- `jurisdiction_map`: from `cookie_consent_jurisdiction_mapper.md`
- `i18n_requirements`: optional from `i18n_requirements_analyst.md`

### Returns
- `script_manifest`: list of { `provider`, `strategy`, `src`, `nonce`, `defer`, `async`, `consent_category`, `inject_location`, `fallback` }
- `csp_directives`: dict — added `script-src`, `connect-src`, `img-src` entries per provider
- `next_phase_hint`: enum (`planning`, `execution`, `result`)

### Side effects
- None; planning only

## Decision Flow

1. **For each enabled provider**:
   a. Choose inject strategy: `consent-blocked` (requires opt-in), `lazy-on-interaction`, or `head-inline`.
   b. Build `src` URL from provider template plus tracking ID placeholder.
   c. Mark `consent_category` from provider config.
   d. Add `nonce` placeholder for CSP when available.
   e. Prefer `defer`/`async` to avoid blocking parser.
   f. For GTM, GA4, and Plausible specifically, emit a Next.js `Script` loader component manifest entry for `runtime/analytics/script_injector.py`.
2. **Build CSP additions** — collect all `csp_domains` from `provider_config` into `connect-src` and `script-src`; add image domains to `img-src`.
3. **Add consent blocker wrapper** — for `consent-blocked` scripts, emit manifest entries referencing `cookie_consent_blocker.md`.
4. **Privacy policy stub** — include `src/app/privacy/page.mdx` in the manifest when any regulated jurisdiction is present.
5. **Handle i18n** — if multiple locales, ensure scripts load once per route and do not hardcode locale.
6. **Return manifest** with hint `execution`.

## Failure Modes

| Condition | Response |
|---|---|
| Provider has no known script template | Skip provider with warning |
| CSP nonce unavailable | Use strict CSP hashes or mark script as `unsafe-inline` fallback with warning |
| Provider requires synchronous load | Override `defer`/`async` and document performance impact |
| Consent category missing | Default to `analytics` and warn |
