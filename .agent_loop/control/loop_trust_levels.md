# Loop Trust Levels

## Role

Runtime trust-level enforcer for self-improving `/loop`, `/goal`, and `/workflows` requests. Defines three autonomy tiers (L1, L2, L3), hard-gates transitions between them, and classifies every loop operation by required trust level. Ensures that destructive, irreversible, or high-blast-radius actions never run autonomously at L3 and always route through the appropriate human-in-the-loop gate.

## Contract

### Receives

- `loop_intent`: parsed `/loop` or `/goal` request from `main_loop.md`
- `proposed_preset`: YAML preset identifier or path (e.g., `ci_sweeper`, `anti_slop_sweeper`)
- `current_trust_level`: enum (`L1`, `L2`, `L3`) from session state or prior loop history
- `trust_history`: optional object with `level`, `stable_report_days`, `rejection_rate_30d`, `last_promotion_date`
- `operation_list`: list of operations the loop intends to perform
- `automation_mode`: enum (`none`, `augment`, `automate`, `human_loop`) from `tooll_subagents/planning/task_scoping_agent.md`
- `project_rules`: dict | None

### Returns

- `effective_trust_level`: enum (`L1`, `L2`, `L3`) — the level the loop may operate at
- `allowed_operations`: list of operations permitted at `effective_trust_level`
- `blocked_operations`: list of operations that require higher trust or human approval
- `transition_status`: enum (`no_change`, `eligible`, `blocked`, `manual_approval_required`)
- `required_evidence`: list of evidence needed for promotion
- `human_gate`: enum (`human_approval.md`, `human_oversight.md`, `none`) — which gate to use for blocked operations
- `trust_verdict`: object with `level`, `reason`, `next_review_date`

### Side Effects

- Writes trust-level decision and transition history to session state
- Logs every promotion evaluation, blocked operation, and human-gate routing to `audit_logger.md`
- May update user trust profile metadata for future auto-approval eligibility

## Decision Flow

1. **Load baseline** — default every new loop to `L1` regardless of user trust profile unless `current_trust_level` is explicitly provided and validated.
2. **Validate inputs** — if `loop_intent` or `operation_list` is missing, return `effective_trust_level=L1`, `transition_status=blocked`, and route all operations through `tooll_subagents/execution/human_approval.md`.
3. **Classify each operation** — assign a minimum required trust level:
   - `L1`: read-only, report-only, file reads, tests, linters, audits, screenshots, cost estimates
   - `L2`: file writes, configuration changes, local builds, dependency updates, branch creation, draft PRs, non-destructive DB reads
   - `L3`: autonomous execution of repeatable, low-blast-radius workflows after evidence threshold is met
   - Always `L2/L3 human zones` and never L3-autonomous: `git push`, `deploy`, `rm -rf`, database migrations, production API key/secrets changes, production webhooks, bulk emails, payments, money transfers, data deletion
4. **Apply operation cap** — compute the maximum required level across `operation_list`. If any operation is `L2/L3 human zone`, cap `effective_trust_level` at `L2` and route that operation through `tooll_subagents/execution/human_approval.md`.
5. **Evaluate L1→L2 promotion** — if `current_trust_level=L1` and the loop requests `L2`:
   - Require ≥7 days of stable L1 reports with no critical failures
   - Require manual approval via `control/human_oversight.md`
   - If both conditions are met, set `transition_status=eligible` and wait for explicit approval; do NOT auto-promote
6. **Evaluate L2→L3 promotion** — if `current_trust_level=L2` and the loop requests `L3`:
   - Require ≤5% rejection rate over the last 30 days
   - Require a stable `.agent_loop/CONSTRAINTS.md` (exists, parseable, not modified in the last 24 hours by an unverified run)
   - Require manual approval via `control/human_oversight.md`
   - If all conditions are met, set `transition_status=eligible` and wait for explicit approval; do NOT auto-promote
7. **Enforce hard gate** — if promotion conditions are not fully satisfied, set `transition_status=blocked`, keep `effective_trust_level` at the current level, and list missing evidence in `required_evidence`.
8. **Select human gate** — for blocked or human-zone operations:
   - Tactical per-action approval → `tooll_subagents/execution/human_approval.md`
   - Strategic promotion, policy conflict, or autonomy-limit escalation → `control/human_oversight.md`
   - No human gate needed → `none`
9. **Build verdict** — emit `effective_trust_level`, allowed/blocked operation lists, transition status, required evidence, selected human gate, and `trust_verdict`.
10. **Return** — pass result to the invoking planner (`tooll_subagents/planning/loop_planner.md` or `tooll_subagents/planning/goal_planner_v2.md`) and to `audit_logger.md`.

## Failure Modes

| Condition | Response |
|---|---|
| `current_trust_level` missing or invalid | Default to `L1`, log anomaly |
| User requests `L3` for a new loop with no history | Block, remain at `L1`, require manual promotion via `control/human_oversight.md` |
| `git push`, `deploy`, `rm -rf`, or DB migration requested at `L3` | Cap at `L2`, route through `tooll_subagents/execution/human_approval.md`; never allow autonomous execution |
| Stable-report evidence missing for L1→L2 | `transition_status=blocked`; list required days and failure criteria |
| Rejection rate >5% for L2→L3 | `transition_status=blocked`; require lower rejection rate before reapplying |
| `CONSTRAINTS.md` unstable or missing | `transition_status=blocked`; require stable constraints file |
| Manual approval given but conditions not met | Override approval with `transition_status=blocked` and preserve audit trail |
| `automation_mode=human_loop` | Force `tooll_subagents/execution/human_approval.md` for every operation regardless of trust level |
