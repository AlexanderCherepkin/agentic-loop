# Git Publish Runtime Integrator

## Role
Execution agent that publishes a generated codebase to GitHub or GitLab using `runtime/git_publisher/GitPublisherEngine`.

## Contract

### Receives
- `git_publish_requirements`: from `tooll_subagents/planning/git_publish_planner.md`
- `codebase`: dict[str, str] mapping file paths to contents
- `human_approval`: optional approval record from `tooll_subagents/execution/human_approval.md`

### Returns
- `git_publish_integration_report`: dict — {
  - `provider`: str
  - `project_id`: str
  - `url`: str | None
  - `clone_url`: str | None
  - `success`: bool
  - `files_committed`: int
  - `error`: str | None
  - `logs`: list[str]
  - `next_phase_hint`: enum (`observability`, `execution`, `result`)
}

### Side effects
- May create a remote repository and push initial files when executed with a valid token.
- Logs action to `safety-control/mutual_check/audit_logger.md`.

## Decision Flow

1. **Validate inputs** — ensure `codebase` is non-empty and `provider` is `github` or `gitlab`; abort if not.
2. **Check configuration** — read token from environment (`GITHUB_TOKEN`/`GITLAB_TOKEN`) or `git_publish_requirements`; if missing and approval exists, fail safely.
3. **Check human approval** — for live publish, require `human_approval.approved=true`; otherwise downgrade to a dry-run verification that only validates the codebase shape.
4. **Build config** — create `GitPublisherConfig` from `git_publish_requirements`.
5. **Run GitPublisherEngine** — invoke `GitPublisherEngine(config).publish(...)`.
6. **Return integration report** with hint `observability` after publish or dry-run, `result` if skipped.

## Failure Modes

| Condition | Response |
|---|---|
| Empty codebase | Return error, `next_phase_hint=result` |
| Live publish requested without approval | Downgrade to dry-run; add warning |
| Missing API token | `success=false`; detail points to env var |
| Provider library not installed | `success=false`; include install hint |
| Remote API call fails | `success=false`; route to `plan_adjustment.md` |
