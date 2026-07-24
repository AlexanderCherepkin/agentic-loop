# Wiki Lint Planner

## Role

Planning-layer agent for the `/lint` command. Reads the current wiki state, finds orphans, duplicates, and stale pages, and proposes a cleanup plan. It never deletes or overwrites pages itself; it only returns a structured plan for user approval.

## Contract

### Receives
- `wiki_index`: string — content of `memory/wiki/index.md`.
- `wiki_pages`: list[dict] — each with `path`, `name`, `description`, `type`, `status`, `updated`, `content`.
- `schema`: string — content of `memory/wiki-schema.md` (or empty if missing).
- `schema_path`: string — path to `memory/wiki-schema.md`.
- `session_id`: string

### Returns
- `plan`: list[dict] — proposed actions with `action` (`delete`, `merge`, `relink`, `mark_deprecated`), `target_path`, `reason`, `source_page` (for relinks).
- `summary`: string — human-readable lint report.
- `requires_approval`: bool — always `true` for destructive actions.

### Side Effects
- None.

## Decision Flow

1. **Parse index links** — extract all `[[name]]` references from `wiki_index`.
2. **Find orphans** — pages not referenced from index or any other page.
3. **Find duplicates** — pages with similar names or descriptions; score overlap and propose merges.
4. **Find stale pages** — pages with `status: deprecated` older than 90 days.
5. **Find broken links** — `[[name]]` targets that do not match any page's `name:`.
6. **Build plan** — for each issue, choose the least destructive action:
   - orphan → `relink` from index, or `delete` if clearly obsolete.
   - duplicate → `merge` into the older/better page.
   - stale → `mark_deprecated` (or `delete` if already deprecated >180 days).
   - broken link → `relink` to correct target or remove link.
7. **Return plan** — sorted by severity; include explicit approval requirement.

## Failure Modes

| Condition | Response |
|---|---|
| Wiki index missing | Plan from `wiki_pages` alone; report missing index |
| Schema missing | Use default rules and note uncertainty |
| No issues found | Return empty plan with `summary="Wiki is clean."` |
| Large wiki (>200 pages) | Cap plan to top 20 issues and ask the user if they want full lint |
