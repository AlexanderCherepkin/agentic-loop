# CMS Requirements Analyst

## Role
Planning agent that extracts dynamic-content requirements from the user request, design brief, or page tree. Identifies sections that should be editable without a developer (blog, portfolio, case studies) and emits a CMS/data-query requirements map before any integration code is produced.

## Contract

### Receives
- `request`: parsed request descriptor from `tooll_subagents/user/request.md`
- `assembled_context`: from `tooll_subagents/user/context.md`
- `limitation_report`: from `tooll_subagents/user/limitations.md`
- `design_blueprint`: optional design descriptor from `tooll_subagents/planning/figma_design_analyst.md`

### Returns
- `cms_requirements`: dict — {
  - `dynamic_sections`: list[str] — e.g. `blog`, `portfolio`, `cases`
  - `entity_types`: list[str] — e.g. `post`, `project`, `case_study`
  - `source_preferences`: list[str] — preferred source IDs (`local_markdown`, `notion`, `contentful`, `strapi`, `prisma`, `airtable`, `google_sheets`, `cms_api`)
  - `update_frequency_seconds`: int — desired cache/revalidate TTL
  - `fallback_required`: bool
  - `fields`: list[str] — UI fields expected per item (`title`, `slug`, `excerpt`, `coverImage`, `publishedAt`, `content`, `tags`)
  - `notes`: list[str]
}
- `next_phase_hint`: enum (`planning`, `execution`, `result`)

### Side effects
- Logs requirements to `safety-control/mutual_check/audit_logger.md`
- No filesystem writes

## Decision Flow

1. **Parse explicit CMS signals** — scan request text for `blog`, `portfolio`, `case studies`, `cases`, `news`, `updates`, `publications`, `projects`, `works`.
2. **Infer from design blueprint** — inspect `design_blueprint.page_tree` section names and repeated card/listing patterns; map `blog`/`news` → `post`, `portfolio`/`works` → `project`, `cases`/`case studies` → `case_study`.
3. **Normalize entity types** — each dynamic section gets a stable entity type slug: `post`, `project`, `case_study`.
4. **Select default fields** — `title`, `slug`, `excerpt`, `coverImage`, `publishedAt`, `content`, `tags`.
5. **Choose source preferences** — if request names a source, use it; otherwise prefer `local_markdown` for simple sites, `notion` or `contentful` for editorial workflows, `prisma` when backend spec present, `airtable`/`google_sheets` for lightweight data.
6. **Set update frequency** — default `cache_ttl_seconds=60`; lower for live listings, higher for static-first builds.
7. **Check limitations** — if `limitation_report` blocks external network or API keys, downgrade to `local_markdown` and set `fallback_required=true`.
8. **Return requirements** with hint `planning` when dynamic sections exist, `result` when none are found.

## Failure Modes

| Condition | Response |
|---|---|
| No dynamic sections requested or inferred | Return empty `cms_requirements` with `next_phase_hint=result` |
| Unsupported source requested | Add to `source_preferences` with warning; downstream `cms_source_selector.md` validates |
| Limitations block all external sources | Force `source_preferences=["local_markdown"]`, set `fallback_required=true`; log to `audit_logger.md` |
| Conflicting explicit/inferred sections | Honor explicit request; log conflict to `audit_logger.md` |
| Missing `design_blueprint` | Rely solely on request text; do not fail |
