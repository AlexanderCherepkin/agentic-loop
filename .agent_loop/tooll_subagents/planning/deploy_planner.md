# Deploy Planner

## Role
Planning agent that selects the deployment target and parameters for a generated Next.js site. Emits a structured deploy plan with safe defaults (dry-run enabled).

## Contract

### Receives
- `request`: parsed request descriptor from `tooll_subagents/user/request.md`
- `assembled_context`: from `tooll_subagents/user/context.md`
- `limitation_report`: from `tooll_subagents/user/limitations.md`
- `design_blueprint`: optional design descriptor from `tooll_subagents/planning/figma_design_analyst.md`
- `generated_code`: optional list of `{ file_path, content }` from `tooll_subagents/planning/design_to_code_planner.md`

### Returns
- `deploy_requirements`: dict — {
  - `needs_deploy`: bool
  - `provider`: enum (`vercel`, `netlify`, `generic`)
  - `dry_run`: bool
  - `build_command`: str
  - `dist_dir`: str
  - `env`: dict[str, str]
  - `timeout`: float
  - `notes`: list[str]
}
- `next_phase_hint`: enum (`planning`, `execution`, `result`)

### Side effects
- Logs plan to `safety-control/mutual_check/audit_logger.md`
- No filesystem writes

## Decision Flow

1. **Parse explicit signals** — scan request text for `deploy`, `vercel`, `netlify`, `hosting`, `publish`, `go live`, `production`.
2. **Select provider** — `vercel` if explicitly mentioned or no provider specified and Next.js static export; `netlify` if mentioned; `generic` for custom host.
3. **Safety default** — set `dry_run=true` unless the request explicitly demands a live deploy AND a human approval gate is expected upstream.
4. **Build command** — default `pnpm build`; prefer existing `package.json` scripts if `generated_code` includes it.
5. **Dist directory** — `dist` for static export; `.next` for standalone.
6. **Env variables** — include only non-secret placeholders (e.g., `NODE_ENV=production`); never expose API keys.
7. **Return requirements** with hint `execution` when deploy is needed, `result` otherwise.

## Failure Modes

| Condition | Response |
|---|---|
| No deploy/hosting signal | `needs_deploy=false`; hint `result` |
| Unsupported provider requested | Switch to `generic`; note reason |
| Project rules forbid external deploy | `needs_deploy=false`; log reason |
| Live deploy requested without approval gate | Keep `dry_run=true`; add warning note |
