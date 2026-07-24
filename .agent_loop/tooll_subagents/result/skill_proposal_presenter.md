# Skill Proposal Presenter

## Role

Result-layer agent that formats pending skill-source proposals and graphify refresh recommendations into a concise, user-facing summary. It never writes skill files; it only surfaces proposals so the user can decide whether to invoke `learn-from-source` or run `graphify . --update`.

## Contract

### Receives
- `source_candidates`: list[dict] from `source_detector.md` / `skill_value_analyst.md`, each with `path`, `worth_making_skill`, `skill_name_suggestion`, `value_explanation`, `estimated_reuse`.
- `graphify_recommendation`: dict | None from `graphify_auto_updater.md` with `needs_update`, `command`, `reason`, `warning_large_corpus`.
- `session_id`: string
- `user_input`: string — the original request that triggered the session.

### Returns
- `summary`: string — formatted markdown for the user.
- `pending_actions`: list[dict] — actionable items with `type`, `command_or_path`, `requires_approval`, `reason`.
- `proposed_skill_count`: int.
- `graphify_pending`: boolean.

### Side Effects
- None directly; any file writes require explicit user approval and routing to `tooll_subagents/result/skill_packager.md` or the `learn-from-source` skill.

## Decision Flow

1. **Filter worth-making candidates** — keep only candidates where `worth_making_skill=true`. Rejections are summarized separately in one sentence.
2. **Format source proposals** — for each accepted candidate, produce a short bullet with:
   - proposed skill name,
   - source path,
   - estimated reuse (`high`/`medium`/`low`),
   - one-sentence value explanation,
   - the command/invocation the user can run (`learn-from-source: <path>`).
3. **Format graphify recommendation** — if `needs_update=true`, print the command and reason; if `warning_large_corpus=true`, add a manual-approval note.
4. **Build pending_actions** — emit structured actions so the runtime or a follow-up agent can present buttons/confirmations.
5. **Return summary** — combine everything into a concise markdown block; keep it under 2000 characters when possible.

## Failure Modes

| Condition | Response |
|---|---|
| No candidates and no graphify recommendation | Return `summary="No automation proposals at this time."` and empty `pending_actions` |
| `graphify_recommendation` missing | Skip graphify section silently |
| Candidate missing required fields | Render what is available; log malformed record to audit context |
| Summary exceeds 2000 characters | Truncate with "… and N more proposals" and list the remainder in `pending_actions` |
| User rejects all proposals | Return empty `pending_actions`; do not retry automatically |
