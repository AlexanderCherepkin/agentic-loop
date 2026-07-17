# Spec Lock

## Role

Runtime enforcement gate that prevents any sub-agent or parallel execution phase from starting until a user-approved specification exists in session state. Acts as a hard circuit breaker between planning and execution.

## Contract

### Receives
- `session_id`: string
- `spec_status`: enum (`draft`, `pending_approval`, `approved`, `rejected`, `missing`) from session state
- `approved_spec`: dict | None — the approved specification object, including `approval_token`
- `task_scope`: from `tooll_subagents/planning/task_scoping_agent.md`
- `plan`: current plan object about to be executed
- `request_source`: enum (`chat`, `cli`, `api`, `voice`, `batch`)

### Returns
- `lock_status`: enum (`open`, `locked`)
- `reason`: string
- `missing_requirements`: list[str] | None — what is required to open the lock
- `next_action`: enum (`proceed`, `require_approval`, `escalate_human`)

### Side Effects
- Logs lock event to `audit_logger.md`
- If locked, aborts current execution phase and routes back to `spec_approval_gate.md`

## Decision Flow

1. **Check trivial exemption** — if `task_scope.scope_size == trivial` and `task_scope.needs_spec == false`, return `lock_status=open`, `next_action=proceed`.
2. **Check spec presence** — if `spec_status` is `missing`, `draft`, or `rejected`, return `lock_status=locked`, `next_action=require_approval`, `reason="Approved spec is required before sub-agents can run"`.
3. **Check approval validity** — if `spec_status == approved` but `approved_spec` is null, `approval_token` is null/empty, or `approved_spec.success_criteria` is empty, return `lock_status=locked`, `next_action=require_approval`, `reason="Approved spec is incomplete or lacks approval token"`.
4. **Check scope alignment** — compare `plan` against `approved_spec.scope`. If the plan contains sub-tasks outside the approved scope, return `lock_status=locked`, `next_action=require_approval`, `reason="Plan contains items outside the approved spec scope"`.
5. **Check non-interactive sources** — if `request_source` is `api` or `batch` and no prior approved spec exists, return `lock_status=locked`, `next_action=escalate_human`, `reason="Non-interactive requests must include a pre-approved spec"`.
6. **Open the lock** — if all checks pass, return `lock_status=open`, `next_action=proceed`.
7. **Log and enforce** — log the decision. If locked, the caller must abort execution and return to `spec_approval_gate.md`.

## Failure Modes

| Condition | Response |
|---|---|
| Session state corrupted and spec status unreadable | Return `locked`, `next_action=escalate_human`; do not guess |
| Approved spec present but plan is empty | Return `locked`, `next_action=require_approval`; no execution without a plan |
| User explicitly requests parallel agents before approval | Return `locked`, explain the rule, and route to `spec_approval_gate.md` |
| Plan matches approved spec but tools were added later | Re-check scope alignment; if new tools were not in the spec, lock and request re-approval |
| `task_scope` is missing | Assume `needs_spec=true` and lock; log anomaly |
