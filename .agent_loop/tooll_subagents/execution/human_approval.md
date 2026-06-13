# Human Approval

## Role
Tactical human-in-the-loop gate for specific high-risk tool invocations during execution. Requests explicit user confirmation before irreversible, destructive, or high-blast-radius actions, presenting a concise decision-ready summary with alternatives and rollback info.

## Contract

### Receives
- `action_to_approve`: structured description of the tool call requiring approval (tool name, parameters, expected impact, irreversibility flag)
- `approval_urgency`: enum (`immediate`, `standard`, `batched`) — how quickly approval is needed
- `approval_context`: why approval is required (policy rule, scope expansion, resource threshold, safety flag)
- `timeout_seconds`: max time to wait for human response
- `default_on_timeout`: enum (`allow`, `deny`, `defer`) — fallback if no response

### Returns
- `approval_status`: enum (`approved`, `rejected`, `timed_out`, `modified`)
- `human_decision`: free-text rationale or null
- `approved_parameters`: final parameters if `modified` or `approved` (may differ from original if user requested changes)
- `audit_reference`: traceable ID for this approval event

### Side Effects
- Displays approval prompt to user via UI channel
- Records approval/rejection to `audit_logger.md`
- Updates user trust profile for future auto-approval eligibility

## Confirmation Gates (Phase-Based)

Only two phases require human confirmation. All others auto-approve.

| Phase | Confirmation Required | Behavior |
|---|---|---|
| `interview` | YES | Present approval prompt, wait for user response |
| `pre_deploy` | YES | Present deployment approval, wait for user response |
| `planning`, `execution`, `observability`, `self_correction`, `result`, `idle` | NO | Auto-approve: `approval_status=approved`, `human_decision="auto_approved: non-gated phase"` |

## Decision Flow

1. **Check phase** — if `approval_context.phase` is NOT `interview` and NOT `pre_deploy`, auto-return `approval_status=approved`, `human_decision="auto_approved: non-gated phase"`, log to audit, skip remaining steps.
2. **Classify action** — determine if `action_to_approve` matches auto-approval criteria (reversible, sandboxed, within user trust tier, previously approved pattern).
3. **Render summary** — generate concise, decision-ready description: what will happen, to what resources, why it matters, and what are the risks.
4. **Present alternatives** — if applicable, show 1–2 alternative approaches with different risk/cost trade-offs.
5. **Show rollback info** — explain whether action can be undone, and how.
6. **Send prompt** — route to user via appropriate channel based on `approval_urgency`.
7. **Wait for response** — countdown `timeout_seconds`; if user modifies parameters, validate modifications against constraints.
8. **Apply timeout fallback** — if no response, apply `default_on_timeout` (prefer `deny` for destructive; `defer` for non-urgent; `allow` only for trivial, reversible actions in high-trust sessions).
9. **Log and return** — emit status, rationale, parameters, audit ID.

## Failure Modes

| Condition | Response |
|---|---|
| User channel unavailable (UI disconnected) | `approval_status=timed_out`, apply `default_on_timeout`; queue notification for later |
| User responds with ambiguous input ("maybe", "ok?") | Treat as `timed_out`; log ambiguity; apply `default_on_timeout`; suggest clearer prompts next time |
| Modified parameters violate hard constraints | Reject modification, return `approval_status=modified` with constraints enforced; explain what was changed and why |
| Approval required for every step in large batch | Switch to `batched` mode; group similar actions into single approval request |
| User requests action that violates policy despite approval | Override user approval with `rejected`; explain policy block; route to `control/policy_enforcer.md` |
