# Deploy Runtime Integrator

## Role
Execution agent that runs the deployment for a generated Next.js site using `runtime/deploy/DeployEngine`. Defaults to dry-run mode for safety and only performs a live deploy when explicitly approved.

## Contract

### Receives
- `deploy_requirements`: from `tooll_subagents/planning/deploy_planner.md`
- `target_dir`: str — Next.js project root
- `human_approval`: optional approval record from `tooll_subagents/execution/human_approval.md`
- `safe_component_manifest`: optional list of generated safe components from `design_to_code_planner.md`

### Returns
- `deploy_integration_report`: dict — {
  - `provider`: str
  - `command`: str
  - `dry_run`: bool
  - `success`: bool
  - `deploy_url`: str | None
  - `stdout`: str
  - `stderr`: str
  - `returncode`: int | None
  - `errors`: list[dict[str, Any]]
  - `notes`: list[str]
  - `next_phase_hint`: enum (`observability`, `execution`, `result`)
}

### Side effects
- May execute external deploy CLI (Vercel/Netlify/generic) when `dry_run=false`.
- Logs command and result to `safety-control/mutual_check/audit_logger.md`.
- No file writes inside the project by default.

## Decision Flow

1. **Validate target directory** — ensure `target_dir` contains deploy artifacts (`package.json`, `vercel.json` or `netlify.toml`, or `dist/` for generic); abort if not.
2. **Check human approval** — if `dry_run=false` but no explicit `human_approval.approved=true`, downgrade to dry-run and log warning.
3. **Build config** — create `DeployConfig` from `deploy_requirements`.
4. **Run DeployEngine** — invoke `runtime/deploy/DeployEngine(target_dir, config).run()`.
5. **Capture result** — record command, exit code, stdout, stderr, and any captured deploy URL.
6. **Return integration report** with hint `observability` after live deploy or dry-run, `result` if skipped.

## Failure Modes

| Condition | Response |
|---|---|
| Target directory missing deploy artifacts | Return error, `next_phase_hint=result`; log to `audit_logger.md` |
| Live deploy requested without approval | Downgrade to dry-run; add warning |
| Deploy command fails | `success=false`; route to `plan_adjustment.md` |
| Deploy URL cannot be extracted | `success=true` if exit code 0; note missing URL |
| Network guard blocks external CLI | Abort; route to `human_approval.md` |
