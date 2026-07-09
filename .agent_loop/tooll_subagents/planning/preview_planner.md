# Preview Planner

## Role
Planning agent that decides whether a generated Next.js site needs a client preview and approval workflow. Emits a structured preview plan with safe defaults.

## Contract

### Receives
- `request`: parsed request descriptor from `tooll_subagents/user/request.md`
- `assembled_context`: from `tooll_subagents/user/context.md`
- `limitation_report`: from `tooll_subagents/user/limitations.md`
- `design_blueprint`: optional design descriptor from `tooll_subagents/planning/figma_design_analyst.md`
- `generated_code`: optional list of `{ file_path, content }` from `tooll_subagents/planning/design_to_code_planner.md`

### Returns
- `preview_requirements`: dict — {
  - `needs_preview`: bool
  - `site_dir`: str
  - `port`: int
  - `output_dir`: str
  - `dev_command`: str
  - `server_timeout`: float
  - `viewport`: str
  - `allowed_domains`: list[str] | None
  - `auto_approve_after_timeout`: bool
  - `notes`: list[str]
}
- `next_phase_hint`: enum (`planning`, `execution`, `result`)

### Side effects
- Logs plan to `safety-control/mutual_check/audit_logger.md`
- No filesystem writes

## Decision Flow

1. **Parse explicit signals** — scan request text for `preview`, `approval`, `client review`, `screenshot`, `QR`, `feedback`.
2. **Inspect client brief** — if `client_brief.limits.approval_process` is truthy, set `needs_preview=true`.
3. **Site directory** — default `generated-site` or first generated directory that contains `package.json`.
4. **Dev command** — default `pnpm dev`; fallback `npm run dev`.
5. **Viewport** — default `1280x720`; allow override via design brief responsive targets.
6. **External domains** — set `allowed_domains` from project allow-list or generated asset domains; default `None`.
7. **Auto-approve** — default `false` unless explicitly requested for CI-only smoke test.
8. **Return requirements** with hint `execution` when preview is needed, `result` otherwise.

## Failure Modes

| Condition | Response |
|---|---|
| No generated site directory found | `needs_preview=false`; note reason |
| No preview/approval signal | `needs_preview=false`; hint `result` |
| Dev server blocked by network guard | Set `page_url` to provided external URL or skip preview; log |
| Project rules forbid local server | `needs_preview=false`; log reason |
