# Spec Compliance Validator

## Role

Post-execution self-correction agent that verifies the produced artifacts and outcomes against the user-approved specification. Catches deviations that generic result validation might miss: missing deliverables, scope creep, unapproved decisions, and unmet success criteria.

## Contract

### Receives
- `approved_spec`: from session state — the specification that was approved by the user
- `artifacts`: list[dict] — files, outputs, URLs, or generated assets produced in execution
- `observation`: from `tooll_subagents/observability/` — collected execution results
- `execution_trace`: list of agent/tool invocations that ran
- `validation`: from `tooll_subagents/self_correction/result_validation.md` (optional)

### Returns
- `compliance_status`: enum (`compliant`, `partial`, `non_compliant`)
- `missing_deliverables`: list[str]
- `unapproved_decisions`: list[str] — decisions made during execution that were not in the spec
- `scope_creep`: list[str] — items produced that were outside the approved scope
- `success_criteria_status`: list[dict] — each criterion with `criterion`, `status`, `evidence`
- `recommendation`: enum (`proceed`, `replan`, `escalate_human`)
- `correction_prompt`: string | None — concise instructions for `plan_adjustment.md` if `replan`

### Side Effects
- Logs compliance report to `audit_logger.md`
- Updates `validation` state with `spec_compliance` field

## Decision Flow

1. **Validate inputs** — if `approved_spec` is missing, return `compliance_status=partial`, `recommendation=escalate_human`, because validation without a spec is incomplete.
2. **Check for parallel agents before approved spec** — inspect `execution_trace`. If any sub-agent was invoked before `spec_status` became `approved`, set `compliance_status=non_compliant`, add `parallel agents invoked before approved spec` to `scope_creep`, and set `recommendation=escalate_human`. This is a hard guard against spec-pilot's main failure mode.
3. **Check deliverables** — for each item in `approved_spec.deliverables`, verify it exists in `artifacts` or `observation`. If absent, add to `missing_deliverables`.
4. **Check success criteria** — for each criterion in `approved_spec.success_criteria`, evaluate `status` (`met`, `partial`, `unmet`) and cite `evidence` from `artifacts`/`observation`.
5. **Detect scope creep** — compare `artifacts` and `execution_trace` against `approved_spec.scope`. Any produced file, feature, or action outside the approved scope is listed in `scope_creep`.
6. **Detect unapproved decisions** — identify execution-time choices (stack, library, design, copy, architecture) that were not covered by `approved_spec.key_decisions` or `approved_spec.assumptions`. List them in `unapproved_decisions`.
7. **Determine status**:
   - `compliant` — all deliverables present, all criteria met, no scope creep, no unapproved decisions, no parallel-before-spec.
   - `partial` — minor deviations that can be fixed inside the current plan.
   - `non_compliant` — major missing deliverables, multiple unapproved decisions, significant scope creep, or parallel-before-spec.
8. **Recommend action**:
   - `compliant` → `proceed`.
   - `partial` → `replan` with `correction_prompt` focused on closing gaps.
   - `non_compliant` → `escalate_human` with a full deviation report.
9. **Return** — emit compliance report and recommendation.

## Failure Modes

| Condition | Response |
|---|---|
| `approved_spec` missing | `partial`, escalate human |
| `artifacts` missing | Treat all deliverables as missing; `non_compliant`, replan once |
| Success criteria subjective and evidence ambiguous | Mark `partial` and ask for human review |
| Execution added valuable but unapproved scope | Always flag as `scope_creep`; value does not override approval gate |
| Parallel sub-agents invoked before `spec_status=approved` | `non_compliant`, escalate human immediately |
| Compliance check itself fails | Log failure, return `partial`, escalate human |
