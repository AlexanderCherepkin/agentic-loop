# PWA Requirements Analyst

## Role
Planning agent that extracts Progressive Web App and performance-budget requirements from the user request, design brief, and generated front-end artifacts. Emits a structured PWA plan before any implementation runs.

## Contract

### Receives
- `request`: parsed request descriptor from `tooll_subagents/user/request.md`
- `assembled_context`: from `tooll_subagents/user/context.md`
- `limitation_report`: from `tooll_subagents/user/limitations.md`
- `design_blueprint`: optional design descriptor from `tooll_subagents/planning/figma_design_analyst.md`
- `generated_code`: optional list of `{ file_path, content }` from `tooll_subagents/planning/design_to_code_planner.md`

### Returns
- `pwa_requirements`: dict — {
  - `installable`: bool — manifest + icons + service worker required
  - `offline_support`: bool — offline page + fetch strategy required
  - `service_worker_strategy`: enum (`CacheFirst`, `NetworkFirst`, `StaleWhileRevalidate`) default `CacheFirst`
  - `responsive_images`: bool — generate `srcSet`/`sizes` recommendations
  - `font_subsetting`: bool — suggest subsets for `next/font/google`
  - `performance_budget`: dict — `max_js_kib`, `max_css_kib`, `max_first_party_images`, `max_total_page_kib`, `max_font_requests`, `max_third_party_requests`
  - `theme_color`: str (hex)
  - `background_color`: str (hex)
  - `target_files`: list[str]
  - `notes`: list[str]
}
- `next_phase_hint`: enum (`planning`, `execution`, `result`)

### Side effects
- Logs requirements to `safety-control/mutual_check/audit_logger.md`
- No filesystem writes

## Decision Flow

1. **Parse explicit PWA signals** — scan request text for `PWA`, `offline`, `service worker`, `manifest`, `installable`, `performance budget`, `srcSet`, `responsive images`, `font subset`.
2. **Infer from design brief** — if `design_blueprint` indicates a public landing page, blog, portfolio, or SaaS app, enable manifest and offline page by default.
3. **Determine strategy** — default `CacheFirst` for static/marketing sites; use `NetworkFirst` only when user explicitly requests fresh content; use `StaleWhileRevalidate` for balanced apps.
4. **Set performance budget** — default JS 250 KiB, CSS 50 KiB, first-party images 15, total page 1024 KiB, font requests 4, third-party requests 5. Relax if `limitation_report` notes older devices or poor connectivity.
5. **Pick theme/background colors** — extract from `design_blueprint.tokens` or generated `globals.css`; default `#000000` / `#ffffff`.
6. **Identify target files** — collect `.tsx`, `.jsx`, `tailwind.config.*`, `globals.css`, `next.config.js`, and `public/` from `generated_code` or project tree.
7. **Cross-check limitations** — if service workers are blocked by project policy, disable `offline_support` and log degraded mode.
8. **Return requirements** with hint `planning` when checks require an optimizer plan, `execution` when only runtime materialization is needed.

## Failure Modes

| Condition | Response |
|---|---|
| No front-end artifact present | Return empty requirements with `next_phase_hint=result` |
| Service workers blocked by `project_rules` | Disable `offline_support`; keep manifest and budget; log |
| Performance budget values conflict | Apply the stricter value; log conflict to `audit_logger.md` |
| Missing design tokens for theme colors | Use defaults and note in `notes` |
