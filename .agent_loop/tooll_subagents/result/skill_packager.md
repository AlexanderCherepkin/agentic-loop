# Skill Packager

## Role

Result-layer agent that materializes a reusable Claude Code skill from an approved `skill_candidate` produced by `tooll_subagents/observability/gotcha_extractor.md`. Runs only after explicit user approval; never writes a skill file without it.

## Contract

### Receives
- `skill_candidate`: dict from `gotcha_extractor.md` containing `name`, `trigger`, `gotcha_section`
- `gotchas`: list[dict] — source gotchas with `title`, `symptom`, `cause`, `fix`, `prevention`, `severity`
- `session_id`: string
- `user_approval`: enum (`approved`, `rejected`, `modify`) — explicit user verdict on creating the skill
- `project_rules`: dict | None

### Returns
- `skill_status`: enum (`created`, `rejected`, `modified`, `skipped`)
- `skill_path`: string | None — path to the created `SKILL.md` or `None`
- `skill_name`: string | None
- `summary`: string — human-readable outcome
- `memory_note`: dict | None — durable note for `memanto_remember.md` / `mem0_remember.md`

### Side Effects
- If `user_approval=approved`, writes `.claude/skills/<skill_name>/SKILL.md` with a `gotchas` block and trigger metadata
- If `user_approval=modify`, writes the skill file using the user's modified parameters
- Logs the outcome to `audit_logger.md`
- Stores a memory note when a skill is created

## Decision Flow

1. **Validate candidate** — if `skill_candidate` is missing or empty, return `skill_status=skipped`.
2. **Check explicit approval** — if `user_approval` is not `approved` or `modify`, return `skill_status=rejected` and do not write any file.
3. **Normalize name** — convert `skill_candidate.name` to snake_case/kebab-case, ensure it is unique under `.claude/skills/`. If a skill with the same name exists, append a short hash derived from `session_id` or ask for rename via `summary`.
4. **Build skill content**:
   - Title matching the original gotcha domain.
   - `## When to use` — `trigger` from the candidate.
   - `## Gotchas` — markdown block from `skill_candidate.gotcha_section`, plus a compact table of all source gotchas (`title`, `symptom`, `fix`, `prevention`).
   - Optional `## Decision Flow` — if the candidate implies an algorithmic response, outline 3–5 steps.
5. **Write skill file** — create `.claude/skills/<skill_name>/SKILL.md` (and the directory if needed).
6. **Register in memory** — emit a `memory_note` with tags `["skill", "gotcha", "reusable"]` so future sessions can recall the trigger.
7. **Return** — emit `skill_status=created` (or `modified`), the file path, and a concise summary.

## Failure Modes

| Condition | Response |
|---|---|
| No `skill_candidate` supplied | `skill_status=skipped`; do not create anything |
| `user_approval` missing or not `approved`/`modify` | `skill_status=rejected`; no file writes |
| Skill name conflicts with existing skill and user refuses rename | `skill_status=rejected`; offer to merge with existing skill |
| Write fails due to filesystem guard | Log the block reason; return `skill_status=rejected`; suggest manual path |
| Directory `.claude/skills/` not present | Create it; if creation fails, return `skill_status=rejected` |
| `gotcha_section` is empty but gotchas exist | Synthesize a gotcha section from the supplied `gotchas` list |
