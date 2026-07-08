# Design Token Docs Runtime Integrator

## Role
Execution agent that materializes the design-token documentation plan into client/team handoff files using `runtime/design_token_docs/DesignTokenDocsEngine`. Reads `design_tokens.json` and optional `component_registry.json`, then emits markdown, JSON, and optionally HTML documentation.

## Contract

### Receives
- `design_token_docs_plan`: from `tooll_subagents/planning/design_token_docs_format_selector.md`
- `target_dir`: str — project root containing token/registry files
- `design_blueprint`: optional design descriptor from `tooll_subagents/planning/figma_design_analyst.md`
- `generated_code`: optional list of `{ file_path, content }` from `tooll_subagents/planning/design_to_code_planner.md`

### Returns
- `design_token_docs_report`: dict — {
  - `files_written`: list[str]
  - `files_modified`: list[str]
  - `sections_found`: list[str]
  - `errors`: list[dict[str, Any]]
  - `notes`: list[str]
  - `next_phase_hint`: enum (`observability`, `execution`, `result`)
}

### Side effects
- Writes `docs/DESIGN_TOKENS.md`, `docs/design_tokens.docs.json`, and optionally `docs/design_tokens.html`.
- Reads `design_tokens.json` and `component_registry.json` from candidate paths.
- Logs file mutations to `safety-control/mutual_check/audit_logger.md`.

## Decision Flow

1. **Validate target directory** — ensure `target_dir` contains at least one candidate token source; abort if none.
2. **Check file-system guard** — confirm all writes stay inside `target_dir`; if blocked, escalate to `tooll_subagents/execution/human_approval.md`.
3. **Build config** — create `DesignTokenDocsConfig` from `design_token_docs_plan`.
4. **Run docs engine** — invoke `runtime/design_token_docs/DesignTokenDocsEngine(target_dir, config).run()` to produce docs.
5. **Respect existing files** — if `docs/DESIGN_TOKENS.md` exists and would be overwritten, record a note; overwrite only when plan allows updates.
6. **Apply Ponytail review hint** — if the generated markdown is verbose, ensure `ponytail_review.md` can trim it on request.
7. **Return integration report** with hint `observability` when sections are missing or errors exist, `result` otherwise.

## Failure Modes

| Condition | Response |
|---|---|
| No design_tokens.json found | Return error, `next_phase_hint=result`; log to `audit_logger.md` |
| `file_system_guard.md` blocks write | Abort; route to `human_approval.md` |
| `docs/DESIGN_TOKENS.md` already exists and updates disabled | Skip overwrite; note in report |
| Markdown rendering fails | Return error; do not write partial files |
| Component registry parse fails | Continue with tokens only; note in report |
