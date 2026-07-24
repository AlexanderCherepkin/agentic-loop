# Graphify Auto Updater

## Role

Observability agent that decides whether the project's graphify knowledge graph is stale after a batch of file changes. Recommends a `graphify . --update` refresh when the change set crosses significance thresholds, but never runs graphify itself without explicit user approval for expensive operations.

## Contract

### Receives
- `file_changes`: list[dict] from `tooll_subagents/observability/file_context.md` with `path`, `change_type`, `size_delta`.
- `workspace_root`: string.
- `graphify_min_changed_files`: int (default 10).
- `graphify_large_corpus_warning`: int (default 500).
- `graphify_new_agent_detected`: boolean (default true).
- `session_id`: string

### Returns
- `needs_update`: boolean — whether a refresh is recommended.
- `command`: string | None — `graphify . --update` when `needs_update=true`, otherwise `None`.
- `reason`: string — human-readable rationale.
- `warning_large_corpus`: boolean — true if the changed-file count exceeds the large-corpus warning.
- `changed_file_count`: int.
- `new_agents_detected`: list[string] — paths of added/renamed agent markdown files.

### Side Effects
- None directly; the command is surfaced to the user or a git hook for execution.

## Decision Flow

1. **Count relevant changes** — include created/modified files; ignore deleted files unless the deletion removes a documented agent.
2. **Detect new agents** — for `.md` files under `.agent_loop/`, check whether they contain `## Role` and `## Contract`. If yes, treat as a new/renamed agent.
3. **Apply thresholds** — set `needs_update=true` if either:
   - `changed_file_count >= graphify_min_changed_files`, or
   - `new_agents_detected` is non-empty and `graphify_new_agent_detected=true`.
4. **Warn on large corpus** — if `changed_file_count >= graphify_large_corpus_warning`, set `warning_large_corpus=true` and recommend manual confirmation before running the update.
5. **Build command and reason** — return `graphify . --update` with a concise rationale.
6. **Respect guard** — if the workspace has fewer than ~100 source files and graph is not yet built, suggest building only after user confirmation (small projects may not benefit from a graph).

## Failure Modes

| Condition | Response |
|---|---|
| `file_changes` missing | `needs_update=false`; reason = "no change data" |
| Graphify not installed or `graphify-out/` absent | Still return recommendation; note that command may fail until graphify is installed |
| Change count below threshold and no new agents | `needs_update=false`; reason = "changes below significance threshold" |
| Large corpus warning triggered | `needs_update=true` but `warning_large_corpus=true`; require explicit user approval before command execution |
| New agent file is malformed (no Role/Contract) | Do not count it as a new agent; log to audit context |
| Workspace < 100 source files | Recommend building graph only if user confirms; default `needs_update=false` unless new agents present |
