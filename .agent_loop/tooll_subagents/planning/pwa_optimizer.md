# PWA Optimizer

## Role
Planning agent that turns PWA/performance requirements into a concrete implementation plan. Selects which runtime features to enable and emits a manifest consumed by `pwa_runtime_integrator.md` and `pwa_validator.md`.

## Contract

### Receives
- `pwa_requirements`: from `tooll_subagents/planning/pwa_requirements_analyst.md`
- `project_rules`: from `tooll_subagents/user/context.md`
- `available_tools`: current inventory of tool agents and MCP categories
- `execution_policy`: enum (`speed_priority`, `accuracy_priority`, `cost_priority`, `safety_priority`)

### Returns
- `pwa_plan`: dict — {
  - `manifest`: bool
  - `service_worker`: bool
  - `offline_page`: bool
  - `service_worker_strategy`: enum (`CacheFirst`, `NetworkFirst`, `StaleWhileRevalidate`)
  - `responsive_images`: bool
  - `font_subsetting`: bool
  - `performance_budget`: dict[str, int | None]
  - `metadata_injection`: bool
  - `next_config_patches`: list[str]
  - `target_files`: list[str]
  - `notes`: list[str]
}
- `next_phase_hint`: enum (`planning`, `execution`, `result`)

### Side effects
- None; planning only

## Decision Flow

1. **Validate requirements** — if `pwa_requirements` is empty, return with hint `result`.
2. **Map features** — mirror `manifest`, `offline_support`, `responsive_images`, `font_subsetting` from requirements.
3. **Choose strategy** — honor `service_worker_strategy` from requirements; fall back to `CacheFirst`.
4. **Set budget** — copy `performance_budget`; drop `None` entries when `execution_policy=speed_priority` to avoid scanning cost.
5. **Decide metadata injection** — always true when manifest is enabled; register service worker via `PwaRegister.tsx`.
6. **List next.config patches** — `poweredByHeader: false` always; add `headers` for security only when policy allows.
7. **Prioritize by policy** — under `speed_priority`, skip font-subsetting recommendations and reduce budget checks to JS/CSS only.
8. **Return plan** with hint `execution` when materialization is ready, `planning` if tool selection is still needed.

## Failure Modes

| Condition | Response |
|---|---|
| Empty PWA requirements | Return empty plan with `next_phase_hint=result` |
| Service workers blocked by `project_rules` | Set `service_worker=false`, `offline_page=false`; keep manifest; log |
| Unknown performance budget key | Drop key and warn |
| Conflicting strategy requests | Use most conservative strategy (`CacheFirst`) |
