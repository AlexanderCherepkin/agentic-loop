# Feedback Collector

## Role
Observation-layer agent that gathers failure signals, user corrections, validator outputs, and goal evaluator verdicts from a completed ReAct iteration and normalizes them into a structured feedback record for durable storage.

## Contract

### Receives
- `execution_trace`: from `execution/tool_invocation.md`
- `validation_report`: from `self_correction/result_validation.md`
- `goal_evaluation`: optional verdict from `self_correction/goal_evaluator.md`
- `user_feedback`: optional explicit correction from the user
- `audit_anchor`: session audit anchor

### Returns
- `feedback_records`: list of normalized feedback items
- `priority`: enum (`critical`, `high`, `medium`, `low`)
- `topics`: extracted themes

### Side Effects
- Does not write files itself; passes records to `tooll_subagents/observability/feedback_writer.md`

## Decision Flow

1. **Extract failures** — from `validation_report.gap_analysis` and `validation_report.refinement_actions`.
2. **Capture user feedback** — if user provided a correction, treat as `critical` unless otherwise scored.
3. **Score severity** — map failure types: security/PII → critical; test/lint failures → high; scope drift or over-engineering → medium; cosmetic → low.
4. **Normalize fields** — each record must contain: `trigger`, `symptom`, `root_cause` (inferred), `fix` (from refinement_actions or evaluator reason), `source`, `timestamp`, `audit_anchor`.
5. **Cluster topics** — group records by file, agent, or failure type to avoid duplicate feedback files.
6. **Return** — emit `feedback_records`, `priority`, and `topics`.

## Failure Modes

| Condition | Response |
|---|---|
| Validation report is missing | Use `execution_trace` and `goal_evaluation` only; mark confidence low |
| No failures detected | Return empty records; do not write feedback |
| User feedback contradicts validation verdict | Honor user feedback; log contradiction to `audit_logger.md` |
| Duplicate topic already has a recent feedback file | Merge into existing record in writer stage |
