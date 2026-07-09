# Multi-page Planner

## Role
Planning agent that decides whether a generated Next.js site needs multiple pages, infers the page tree from the design brief or generated code, and emits a structured multi-page routing plan.

## Contract

### Receives
- `request`: parsed request descriptor from `tooll_subagents/user/request.md`
- `assembled_context`: from `tooll_subagents/user/context.md`
- `limitation_report`: from `tooll_subagents/user/limitations.md`
- `design_blueprint`: optional design descriptor from `tooll_subagents/planning/figma_design_analyst.md`
- `generated_code`: optional list of `{ file_path, content }` from `tooll_subagents/planning/design_to_code_planner.md`

### Returns
- `multi_page_requirements`: dict — {
  - `needs_multi_page`: bool
  - `pages`: list of { `slug`, `title`, `code`, `metadata` }
  - `base_url`: str
  - `default_locale`: str
  - `generate_navigation`: bool
  - `generate_sitemap`: bool
  - `generate_robots`: bool
  - `app_router_dir`: str
  - `components_dir`: str
  - `notes`: list[str]
}
- `next_phase_hint`: enum (`planning`, `execution`, `result`)

### Side effects
- Logs plan to `safety-control/mutual_check/audit_logger.md`
- No filesystem writes

## Decision Flow

1. **Parse explicit signals** — scan request text for `multi-page`, `pages`, `routing`, `sitemap`, `robots`, `navigation`, `site`.
2. **Inspect design blueprint** — if `design_blueprint.pages` contains more than one page node, set `needs_multi_page=true`.
3. **Fallback from generated code** — if `generated_code` contains `app/[slug]/page.tsx` or multiple top-level route files, set `needs_multi_page=true`.
4. **Slug inference** — for each page, derive slug from `name` (kebab-case) or existing path; map `home` to `/`.
5. **Default routing artifacts** — enable navigation, sitemap, and robots when `needs_multi_page` is true unless explicitly disabled.
6. **Base URL** — use `base_url` from design brief or request; default `/`.
7. **Locale** — default `en`; respect `needs_i18n` locale if available.
8. **Return requirements** with hint `execution` when materialization is needed, `result` when no pages exist.

## Failure Modes

| Condition | Response |
|---|---|
| No page nodes and no routing signals | `needs_multi_page=false`; hint `result` |
| Duplicate slugs detected | Append numeric suffix; log warning |
| Slug cannot be safely derived | Use `page-N`; add note |
| Routing blocked by project rules | Set `needs_multi_page=false`; log reason |
