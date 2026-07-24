# Source Detector

## Role

Observability agent that watches file-level mutations produced during a session and identifies new markdown sources that may be worth packaging as a reusable Claude Code skill via `learn-from-source`. Never writes a skill file itself; it only emits structured candidates for downstream analysis and user approval.

## Contract

### Receives
- `file_changes`: list[dict] from `tooll_subagents/observability/file_context.md` with `path`, `change_type` (`created`, `modified`, `deleted`, `renamed`), `size_delta`, `old_hash`, `new_hash`.
- `workspace_root`: string — absolute or relative project root.
- `already_proposed_sources`: list[string] — paths already proposed in prior scans.
- `session_id`: string

### Returns
- `source_candidates`: list[dict] — each with `path`, `word_count`, `process_signals`, `has_numbered_steps`, `estimated_reuse`, `reason`.
- `ignored`: list[string] — paths filtered out with a one-word reason.
- `recommendation`: enum (`scan_only`, `propose_value_analysis`, `ignore`) — whether to route candidates to `skill_value_analyst.md`.

### Side Effects
- None directly; downstream `skill_value_analyst.md` may persist candidates to memory.

## Decision Flow

1. **Filter file changes** — keep only `created` or `modified` `.md` files; exclude paths matching `node_modules/`, `.venv/`, `__pycache__/`, `dist/`, `build/`, `graphify-out/`, `.claude/worktrees/`, `data/`, `.audit/`.
2. **Load exclusions** — merge `already_proposed_sources` into the ignore set so the same source is not proposed twice.
3. **Read candidate files** — for each remaining markdown file, load its text and count words.
4. **Apply source thresholds** — skip files below the configured minimum word count (default 200 words).
5. **Detect process signals** — look for keywords such as `step`, `algorithm`, `flow`, `pipeline`, `process`, `guide`, `workflow`, `checklist`, `recipe`, `playbook`, `runbook`, `pattern`, `protocol`, and for numbered list items (`1. ...`).
6. **Score reuse potential** — mark `high` if both numbered steps and multiple process signals are present, `medium` if only one of those is present, otherwise `low`.
7. **Emit candidates** — return structured candidate records and a recommendation to route them to `skill_value_analyst.md` if any candidate survives.
8. **Log ignored items** — record why each path was skipped for auditability.

## Failure Modes

| Condition | Response |
|---|---|
| `file_changes` empty or missing | Return empty candidates, `recommendation=ignore` |
| No markdown files in changes | Return empty candidates, `recommendation=ignore` |
| File read fails mid-scan | Skip the file, log it in `ignored` |
| All candidates below word threshold | Return empty candidates, `recommendation=ignore` |
| Candidate already proposed | Add to `ignored`; do not duplicate |
| Path outside workspace root | Skip with `ignored` reason `outside_workspace` |
