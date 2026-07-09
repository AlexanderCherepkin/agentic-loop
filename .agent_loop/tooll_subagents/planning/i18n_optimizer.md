# i18n Optimizer

## Role
Cross-cutting planning strategist that reduces the runtime cost and bundle size of the generated i18n layer. Chooses between SSG pre-translation, dynamic locale loading, partial dictionaries, and Partytown-compatible loading where applicable.

## Contract

### Receives
- `i18n_requirements`: from `i18n_requirements_analyst.md`
- `dictionaries`: from `i18n_dictionary_generator.md`
- `routing_plan`: from `i18n_routing_planner.md`
- `rewrite_manifest`: from `i18n_component_rewriter.md`

### Returns
- `optimization_plan`: dict — {
  - `load_strategy`: enum (`ssg`, `dynamic`, `lazy_namespace`, `full_bundle`)
  - `split_namespaces`: list[str]
  - `preload_locales`: list[str]
  - `bundle_size_estimate_kb`: float
  - `recommendations`: list[str]
}
- `next_phase_hint`: enum (`planning`, `execution`, `result`)

### Side effects
- None; planning only

## Decision Flow

1. **Measure dictionary size** — estimate JSON size per locale from key count and average string length.
2. **Choose load strategy** — `ssg` for static marketing sites (< 3 locales, < 500 keys); `lazy_namespace` for larger apps; `full_bundle` only when operator explicitly opts in.
3. **Split namespaces** — group keys by section (`hero`, `nav`, `footer`) so `next-intl` can load only active namespace per route when lazy mode enabled.
4. **Select preload locales** — preload default locale plus top 1–2 locales by expected traffic; defer others.
5. **Estimate bundle impact** — sum expected locale JSON sizes; compare against Lighthouse performance budget (recommend splitting if > 50 KB per route).
6. **Recommend tooling** — suggest `next-intl` version, middleware matcher tuning, and RTL CSS strategy.
7. **Return plan** with hint `execution`.

## Failure Modes

| Condition | Response |
|---|---|
| Dictionary size exceeds budget | Switch to `lazy_namespace` and list split recommendations |
| Only one locale | Return `full_bundle` with zero optimizations; no warnings |
| Dynamic strategy requested for static site | Honor request but recommend `ssg` in `recommendations` |
