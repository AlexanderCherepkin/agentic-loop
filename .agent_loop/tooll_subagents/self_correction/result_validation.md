# Result Validation

## Role
Post-execution verification agent that checks whether the observed outcomes match the intended goals and success criteria defined in the original request. Determines if the task is complete, partially complete, or failed, and provides diagnostic signal for plan adjustment or termination.

## Contract

### Receives
- `original_request`: parsed request descriptor from `user/request.md`
- `execution_trace`: from `execution/tool_invocation.md`
- `observation_artifacts`: combined outputs from `observability/` agents
- `success_criteria`: optional explicit criteria from user or inferred from request type

### Returns
- `validation_status`: enum (`complete`, `partial`, `failed`, `inconclusive`)
- `criteria_checklist`: list of success criteria with pass/fail status and evidence
- `gap_analysis`: list of unmet requirements or unexpected deviations with severity
- `confidence`: float — certainty in validation verdict
- `retry_recommended`: boolean — whether another iteration could succeed
- `next_phase_hint`: enum (`self_correction`, `execution`, `planning`, `result`) — suggested next ReAct phase based on validation verdict

### Side Effects
- Writes validation record to session memory for future reference
- Logs to `audit_logger.md`

## Decision Flow

1. **Load criteria** — if `success_criteria` provided, use it; otherwise infer from `request_type` and domain patterns (e.g., code_change: tests pass, no syntax errors, files modified as intended; question: answer addresses all parts, sources cited).
2. **Map to observations** — for each criterion, identify which `observation_artifacts` provide evidence.
3. **Check completeness** — verify all expected outputs were produced (files created, commands executed, answers generated).
4. **Check correctness** — verify outputs meet quality standards (syntax valid, tests pass, no errors in logs, no contradictions in answer).
5. **Check scope** — verify that only intended resources were modified; no unintended side effects.
6. **Check user constraints** — verify that hard constraints from `original_request` were respected (e.g., "do not use regex", "must keep backward compatibility").
7. **Score each criterion** — `pass` if fully satisfied; `fail` if violated or missing; `partial` if mostly satisfied but with minor gaps.
8. **Aggregate verdict** — `complete` if all criteria pass; `partial` if some pass and no critical failures; `failed` if critical criterion fails or majority fail; `inconclusive` if insufficient evidence to judge.
9. **Determine retry recommendation** — `retry_recommended=true` if `partial` and root cause appears addressable (missing dependency, typo, single test failure); `false` if `failed` due to fundamental mismatch or `inconclusive`.
10. **Return** — emit status, checklist, gap analysis, confidence, retry recommendation.

## Failure Modes

| Condition | Response |
|---|---|
| Success criteria ambiguous or missing | Infer from `request_type` with low confidence; `validation_status=inconclusive`; recommend clarification via `assistance_request.md` |
| Observation artifacts missing critical evidence | `validation_status=inconclusive`; `gap_analysis` includes missing evidence items |
| Validation contradicts user's explicit approval | Honor user approval; `validation_status=complete`; log override and rationale |
| Circular validation (result validates itself) | Break loop by requiring external evidence (test, file diff, third-party output); flag to `audit_logger.md` |
| Gap analysis identifies security regression | `validation_status=failed`; `retry_recommended=false`; escalate to `safety-control/content_checker.md` |
