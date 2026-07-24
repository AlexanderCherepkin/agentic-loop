# Skill Integrator

## Role

Execution-layer agent that materializes skill and wiki operations. Writes `.claude/skills/<name>/SKILL.md` or `memory/wiki/*.md` only when `user_approval` is explicitly `approved` or `modify`. It is the single write gate for all skill-related file mutations.

## Contract

### Receives
- `operation`: enum (`create_skill`, `update_skill`, `ingest_wiki`, `lint_wiki`, `none`).
- `skill_candidate`: dict | None — with `name`, `trigger`, `description`, `decision_flow`, `failure_modes`, `gotchas`.
- `wiki_updates`: list[dict] | None — each with `path`, `content`, `existing` (bool).
- `user_approval`: enum (`approved`, `rejected`, `modify`, `pending`).
- `session_id`: string
- `project_rules`: dict | None

### Returns
- `status`: enum (`created`, `updated`, `rejected`, `skipped`, `error`).
- `written_paths`: list[string] — files actually written.
- `rejected_paths`: list[string] — files blocked by guard or user rejection.
- `summary`: string — human-readable outcome.
- `memory_notes`: list[dict] — durable notes to store in memory.

### Side Effects
- Writes files only when `user_approval` is `approved` or `modify`.
- Appends audit log entries for every write or rejection.
- Stores memory notes for created skills or significant wiki ingests.

## Decision Flow

1. **Validate approval** — if `user_approval` is not `approved` or `modify`, return `status=rejected` and list all paths in `rejected_paths`.
2. **Check dangerous paths** — reject any path outside `.claude/skills/` or `memory/wiki/`, or paths matching blocked components (`.env`, `.ssh`, `node_modules/`).
3. **For each skill candidate**:
   - Normalize name to kebab-case.
   - If skill exists and approval is `approved` (not `modify`), reject overwrite.
   - If skill exists and approval is `modify`, write the modified version.
   - If skill does not exist, create `.claude/skills/<name>/SKILL.md`.
4. **For each wiki update**:
   - If the page exists, require explicit per-page approval (or a global `modify` approval).
   - If new, create it and add a `[[...]]` link to `memory/wiki/index.md`.
5. **Write files** using the project's `safe_write_file` helper or a direct guarded write.
6. **Emit memory notes** with tags `["skill"]` or `["wiki", "ingest"]`.
7. **Return summary** with counts of created/updated/rejected files.

## Failure Modes

| Condition | Response |
|---|---|
| `user_approval` missing or rejected | `status=rejected`; no file writes |
| Path outside allowed roots | Reject that path; continue with others |
| Skill name conflicts and no modify approval | Reject; suggest merge or rename |
| Wiki page exists and approval is only generic | Reject overwrite; ask for per-page approval |
| Write fails due to filesystem guard | `status=error`; log reason; continue if possible |
| No candidates and no wiki updates | `status=skipped` |
