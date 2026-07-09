# CMS Source Selector

## Role
Planning agent that normalizes the chosen CMS source, validates it against supported providers, and emits a concrete source configuration used by `cms_runtime_integrator.md`.

## Contract

### Receives
- `cms_requirements`: from `tooll_subagents/planning/cms_requirements_analyst.md`
- `project_rules`: from `tooll_subagents/user/context.md`
- `mcp_categories`: list of available MCP category names

### Returns
- `cms_source_config`: dict — {
  - `source_id`: enum (`local_markdown`, `notion`, `contentful`, `strapi`, `prisma`, `airtable`, `google_sheets`, `cms_api`)
  - `enabled`: bool
  - `connection`: dict[str, Any] — endpoint placeholder, API key placeholder, table/collection/sheet name, query params
  - `entity_types`: list[str]
  - `mapping`: dict[str, str] — external field → UI field (`title`, `slug`, `excerpt`, `coverImage`, `publishedAt`, `content`, `tags`)
  - `cache_ttl_seconds`: int
  - `fallback_to_static`: bool
}
- `next_phase_hint`: enum (`planning`, `execution`, `result`)

### Side effects
- None; planning only

## Decision Flow

1. **Normalize source ID** — map common names to canonical ids: `notion` → `notion`, `contentful` → `contentful`, `strapi` → `strapi`, `prisma` → `prisma`, `airtable` → `airtable`, `google_sheets`/`gsheets` → `google_sheets`, `markdown`/`md` → `local_markdown`, generic API → `cms_api`.
2. **Filter unsupported sources** — if a requested source is unknown, fall back to `local_markdown` and add a warning.
3. **Apply project tooling preferences** — if `project_rules.tooling_preferences` favors or blocks a source, respect it; if a blocked source is required, escalate to `control/policy_enforcer.md`.
4. **Map entity types** — use `cms_requirements.entity_types`; default to `["post", "project", "case_study"]` when empty.
5. **Build field mapping** — default mapping preserves common field names and remaps unusual ones to UI fields (`title`, `slug`, `excerpt`, `coverImage`, `publishedAt`, `content`, `tags`).
6. **Set connection placeholders** — include `endpoint`, `api_key`, `collection` / `database_id` / `table_name` / `sheet_name` depending on source; leave values empty for `.env.local.example` population.
7. **Set cache TTL and fallback** — default `cache_ttl_seconds=60`; enable `fallback_to_static` for all external sources and when `cms_requirements.fallback_required=true`.
8. **Return config** with hint `execution` when source is enabled, `result` when disabled or no dynamic sections remain.

## Failure Modes

| Condition | Response |
|---|---|
| All requested sources invalid | Fall back to `local_markdown`, `enabled=true`, `fallback_to_static=true`; warn |
| No entity types provided | Default to `["post", "project", "case_study"]` |
| Project rules block external source | Switch to `local_markdown`; log to `safety-control/mutual_check/audit_logger.md` |
| Connection placeholder missing | Add empty placeholder; downstream `cms_runtime_integrator.md` writes `.env.local.example` |
