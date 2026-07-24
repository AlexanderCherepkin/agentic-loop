# Skill Request Router

## Role

Planning-layer agent that detects whether the user is asking for a skill operation (`/skill`, `/learn`, `/lint`, or a plain-language equivalent) and routes the request to the correct downstream agent. It does not write files; it only classifies intent and extracts parameters.

## Contract

### Receives
- `user_input`: string — the user's message.
- `session_id`: string
- `existing_skills`: list[string] — names under `.claude/skills/`.
- `available_wiki_pages`: list[string] — current `memory/wiki/*.md` names.

### Returns
- `skill_request`: dict | None — with keys `command` (`skill`, `learn`, `lint`), `source` (path/URL/note/chat), `proposed_name` (string | None), `target` (string | None), `requires_approval` (bool).
- `route_to`: enum (`skill_installer`, `skill_learner`, `wiki_linter`, `none`).
- `reason`: string — why this route was chosen.

### Side Effects
- None.

## Decision Flow

1. **Normalize input** — lowercase, trim punctuation, detect leading slash commands.
2. **Match command patterns**:
   - `/skill ...`, `установи навык ...`, `make skill ...`, `create skill ...` → `command=skill`, route to `skill_installer`.
   - `/learn ...`, `сохрани этот чат как навык`, `научи навыку ...`, `learn from ...` → `command=learn`, route to `skill_learner`.
   - `/lint`, `почисти вики`, `lint wiki`, `wiki lint` → `command=lint`, route to `wiki_linter`.
   - Otherwise return `route_to=none`.
3. **Extract source/target** — capture quoted strings, URLs, file paths, or the phrase `this chat`/`этот чат`.
4. **Propose a name** — if the input contains a kebab-case/single-token word that matches an existing skill, treat it as target; otherwise propose a name derived from the source topic.
5. **Return classification** — emit `skill_request`, `route_to`, and `reason`.

## Failure Modes

| Condition | Response |
|---|---|
| Empty or non-skill input | `route_to=none` |
| Ambiguous command (e.g. `/learn` without source) | `route_to=skill_learner` with `source=None` so downstream can ask |
| Source path looks dangerous or outside workspace | `route_to=skill_learner` but flag `unsafe_source=true` |
| Existing skill conflict detected | Include `conflict_with` in `skill_request` |
