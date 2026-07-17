# Git Publish Planner

## Role
Planning agent that decides whether a generated project should be pushed to a Git provider (GitHub/GitLab), selects the provider, and emits a structured publish plan with safe defaults.

## Contract

### Receives
- `request`: parsed request descriptor from `tooll_subagents/user/request.md`
- `assembled_context`: from `tooll_subagents/user/context.md`
- `generated_code`: optional list of `{ file_path, content }` from `tooll_subagents/planning/design_to_code_planner.md` or `tooll_subagents/planning/project_starter_agent.md`
- `deploy_requirements`: optional plan from `tooll_subagents/planning/deploy_planner.md`

### Returns
- `git_publish_requirements`: dict — {
  - `needs_publish`: bool
  - `provider`: enum (`github`, `gitlab`)
  - `project_id`: str
  - `private`: bool
  - `commit_message`: str
  - `next_phase_hint`: enum (`planning`, `execution`, `result`)
  - `notes`: list[str]
}

### Side effects
- Logs plan to `safety-control/mutual_check/audit_logger.md`
- No filesystem writes

## Decision Flow

1. **Parse explicit signals** — scan request text for `repo`, `github`, `gitlab`, `publish`, `git push`, `repository`.
2. **Select provider** — `github` if explicitly mentioned or no provider specified; `gitlab` if mentioned.
3. **Determine project_id** — prefer explicit request entity, then `deploy_requirements.project_id`, then `generated_code` directory name, then a safe slug derived from the brief.
4. **Privacy default** — set `private=true` unless the request explicitly asks for a public repository.
5. **Safety default** — if `generated_code` is empty or no git signal present, set `needs_publish=false` and hint `result`.
6. **Return requirements** with hint `execution` when publish is needed, `result` otherwise.

## Failure Modes

| Condition | Response |
|---|---|
| No git publish signal and no generated code | `needs_publish=false`; hint `result` |
| Unsupported provider requested | Switch to `github`; note reason |
| Project rules forbid external publish | `needs_publish=false`; log reason |
| Missing project identifier | Return error, `next_phase_hint=result` |
