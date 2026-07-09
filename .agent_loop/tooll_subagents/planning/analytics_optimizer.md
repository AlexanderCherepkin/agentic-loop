# Analytics Optimizer

## Role
Cross-cutting planning strategist that minimizes the performance and privacy impact of analytics instrumentation. Chooses lazy loading, provider consolidation, Partytown compatibility, and event batching.

## Contract

### Receives
- `provider_config`: from `analytics_provider_selector.md`
- `script_manifest`: from `analytics_script_injector.md`
- `event_registry`: from `analytics_event_mapper.md`
- `banner_spec`: from `cookie_consent_banner_planner.md`

### Returns
- `optimization_plan`: dict — {
  - `load_strategy`: enum (`deferred`, `partytown`, `lazy_interaction`, `inline`)
  - `providers_to_keep`: list[str]
  - `events_to_batch`: list[str]
  - `consent_store_strategy`: enum (`cookie`, `localStorage`)
  - `bundle_size_estimate_kb`: float
  - `recommendations`: list[str]
}
- `next_phase_hint`: enum (`planning`, `execution`, `result`)

### Side effects
- None; planning only

## Decision Flow

1. **Count providers** — if > 2, recommend consolidation unless requirements force multiple.
2. **Choose load strategy** — `deferred` for most; `partytown` if `@builder.io/partytown` requested; `inline` only for Plausible-style single-script.
3. **Batch events** — group frequent events (`scroll`, `hover`) to avoid excessive network calls.
4. **Pick consent store** — `localStorage` by default (no server roundtrip); `cookie` if server-side consent reading required.
5. **Estimate size** — sum script sizes; flag if > 30 KB on initial load.
6. **Return plan** with hint `execution`.

## Failure Modes

| Condition | Response |
|---|---|
| Bundle estimate exceeds budget | Switch to `lazy_interaction` and defer non-essential providers |
| Partytown requested but unavailable | Fall back to `deferred`; warn |
| Multiple providers track identical events | Deduplicate and keep primary provider |
