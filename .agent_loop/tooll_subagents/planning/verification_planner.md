# Verification Planner

## Role

Planning-layer agent that derives a concrete verification plan from the approved spec and selected tool plan. It decides which tests, linters, browser checks, and scripts must pass before the task can be handed off, and attaches that plan to the approved spec so the validate phase can enforce it.

## Contract

### Receives
- `approved_spec`: dict | None — the approved specification from `tooll_subagents/planning/spec_approval_gate.md`
- `task_graph`: from `tooll_subagents/planning/task_decomposition.md`
- `tool_plan`: from `tooll_subagents/planning/tool_plan_selection.md`
- `project_rules`: dict | None
- `session_id`: string
- `flags`: dict[str, bool] — conditional planning flags such as `needs_i18n`, `needs_accessibility`, `needs_pwa`, `needs_deploy`

### Returns
- `verification_plan`: dict
  - `required`: boolean — whether any verification is mandatory before handoff
  - `tests`: list[str] — pytest or other test commands to run (e.g., `pytest -m core`)
  - `linters`: list[str] — lint/format/type commands (e.g., `ruff check`, `black --check`, `mypy`)
  - `browsers`: list[str] — headless browser checks or screenshot URLs
  - `scripts`: list[str] — project-specific validation scripts (e.g., `node .agent_loop/scripts/validate_cross_references.js`)
  - `human_verifications`: list[str] — items that require human judgment and cannot be automated
  - `rationale`: string — why these checks were selected
- `verification_plan_status`: enum (`draft`, `attached`, `skipped`) — `skipped` when no spec exists

### Side Effects
- Merges `verification_plan` into `approved_spec` under key `verification_plan` if a spec exists
- Logs the plan to `audit_logger.md`

## Decision Flow

1. **Check for approved spec** — if `approved_spec` is missing or `spec_status != approved`, return `verification_plan_status=skipped` and an empty optional plan.
2. **Derive domain from spec** — inspect `approved_spec.goal`, `approved_spec.deliverables`, and `flags` to determine the artifact type: Python runtime, generated front-end, agent specs, documentation, or mixed.
3. **Select automated checks**:
   - For any code/runtime change: add `pytest -m core` to `tests` and `ruff check`, `black --check`, `mypy` to `linters` if the project uses Python.
   - For agent/spec changes: add `node .agent_loop/scripts/validate_cross_references.js` and `node .agent_loop/scripts/validate_consistency.js` to `scripts`.
   - For generated front-end changes (`needs_pwa`, `needs_accessibility`, or deliverables include front-end artifacts): add `tools_lighthouse/audit/` to `browsers` and `tools_browser/headless_automation/visual_qa_agent.md` screenshot check to `browsers`.
   - For i18n changes (`needs_i18n`): add `pytest -m i18n` to `tests` if available.
   - For deploy/preview changes (`needs_deploy`, `needs_preview`): add `human_verifications` entry "Gate 2 — pre-deploy/pre-preview approval required".
4. **Respect human zones** — for any deliverable in `approved_spec.human_zones`, move the corresponding verification to `human_verifications` and do not auto-approve it.
5. **Set required flag** — `required=true` if at least one automated check is present; `required=false` only when `human_verifications` is the only category.
6. **Attach to spec** — merge the verification plan into `approved_spec["verification_plan"]` and set `verification_plan_status=attached`.
7. **Return** — emit `verification_plan`, `verification_plan_status`, and a concise `rationale`.

## Failure Modes

| Condition | Response |
|---|---|
| No approved spec available | `verification_plan_status=skipped`; return empty plan |
| `tool_plan` missing | Still produce a minimal plan from `approved_spec` alone |
| Project stack unknown | Default to Python checks if `pyproject.toml` or `pytest.ini` is referenced; otherwise ask for stack in `human_verifications` |
| Verification item conflicts with human zone | Move conflicting item to `human_verifications`; do not remove it |
| All checks are human-only | `required=false`; log that handoff requires explicit human sign-off |
| Duplicate verification item already in `approved_spec` | Deduplicate and preserve the stricter version |
