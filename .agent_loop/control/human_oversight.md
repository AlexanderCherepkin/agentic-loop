# Human Oversight

## Role
Strategic human-in-the-loop gate that escalates high-stakes, ambiguous, or novel decisions to human operators for judgment. Maintains the ultimate accountability boundary for actions that exceed autonomous authority.

## Contract

### Receives
- `escalation_request`: structured case containing context, proposed action, risk summary, and urgency
- `escalation_reason`: enum (`high_risk`, `policy_conflict`, `novel_scenario`, `autonomy_limit`, `compliance_flag`, `user_request`)
- `timeout_config`: max seconds to wait for human response
- `fallback_policy`: enum (`block`, `defer`, `escalate_chain`, `auto_resolve_with_caution`) if human unavailable

### Returns
- `oversight_status`: enum (`approved`, `rejected`, `modified`, `timeout`, `delegated`)
- `human_decision`: free-text rationale from operator, or null if timeout
- `applied_constraints`: list of modified limits or conditions if `modified`
- `audit_reference`: traceable ID linking this oversight event

### Side Effects
- Records full escalation thread to `audit_logger.md`
- Updates human response time statistics
- May update policy rules if human establishes precedent

## Decision Flow

1. **Assess urgency** — classify `escalation_reason` into response-time buckets (critical = immediate, standard = 5 min, low = 30 min).
2. **Select channel** — route to on-call operator, domain expert queue, or product owner based on reason and domain.
3. **Render case** — present concise, decision-ready summary: what, why, risks, alternatives, recommended action.
4. **Wait for response** — hold proposed action; countdown `timeout_config`.
5. **Handle timeout** — if no response, apply `fallback_policy`: `block` for safety, `defer` for non-urgent, `escalate_chain` to next operator, `auto_resolve_with_caution` for low-risk with audit trail.
6. **Apply decision** — if `approved`, execute; if `rejected`, halt and notify requester; if `modified`, apply constraints and execute; if `delegated`, forward to designated authority.
7. **Log and close** — emit result, record decision, update statistics.

## Failure Modes

| Condition | Response |
|---|---|
| All human operators unreachable | Apply `fallback_policy`; if `fallback_policy` undefined, default to `block` |
| Escalation request malformed or missing context | Reject escalation back to sender with required-fields list |
| Human approves but decision violates hard policy | Override human approval with `rejected`, `human_decision` preserved in audit, alert senior operator |
| Timeout during operator handoff | Extend timeout by 50% once; if still no response, apply fallback |
| Duplicate escalation for same case | Deduplicate; append new reasoning to existing thread |
