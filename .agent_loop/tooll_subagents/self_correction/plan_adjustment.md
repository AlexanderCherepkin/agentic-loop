# Plan Adjustment

## Role
Adaptive replanning agent that modifies the current task graph when execution results deviate from expectations. Generates a revised plan that addresses identified gaps, failures, or new information without discarding completed valid work.

## Contract

### Receives
- `validation_result`: from `self_correction/result_validation.md`
- `current_task_graph`: from `planning/task_decomposition.md`
- `tool_plan`: from `planning/tool_plan_selection.md`
- `gap_analysis`: from `self_correction/result_validation.md`
- `refinement_actions`: optional list from `self_correction/result_validation.md` when visual QA discrepancies drive layout/component corrections
- `visual_qa_report`: optional structured report from `tools_browser/headless_automation/visual_qa_agent.md`
- `max_replanning_attempts`: integer (default 3)

### Returns
- `adjusted_plan`: new task graph with modifications highlighted
- `change_summary`: list of added, removed, reordered, or modified sub-tasks with rationale
- `layout_patches`: optional list of deterministic layout AST or component patches to apply before the next visual QA iteration
- `risk_delta`: change in overall risk score compared to original plan
- `approval_needed`: boolean — whether human or elevated approval required for adjustment
- `remaining_attempts`: integer — how many replanning attempts left
- `human_escalation_reason`: optional string when `remaining_attempts` exhausted

### Side Effects
- Updates session plan state
- Logs adjustment to `audit_logger.md`
- May trigger `cost_risk_assessment.md` if budget impact significant

## Decision Flow

1. **Analyze gaps** — for each item in `gap_analysis`, determine root cause: missing step, wrong tool, incorrect parameter, environmental change, user constraint overlooked, or upstream error.
2. **Classify failures** — transient (retryable), persistent (requires different approach), or fundamental (goal itself flawed or impossible).
3. **Preserve completed work** — identify which sub-tasks in `current_task_graph` succeeded and should remain; mark them as frozen.
4. **Design adjustments** — for each gap:
   - Missing step: add new sub-task with appropriate dependencies.
   - Wrong tool: substitute tool category and update parameter schema.
   - Incorrect parameter: add validation sub-task or parameter correction step.
   - Environmental change: insert environment refresh or dependency installation step.
   - Overlooked constraint: add constraint-checking gate before affected steps.
   - Visual QA discrepancy: convert `refinement_actions` into deterministic `layout_patches` (spacing, sizing, alignment, font, color) and insert `compose` + `visual_qa` sub-tasks for the next iteration.
5. **Validate adjusted graph** — ensure no cycles, all dependencies satisfiable, no frozen tasks modified.
6. **Compute risk delta** — compare new plan risk to original using `cost_risk_assessment` heuristics; flag if significantly higher.
7. **Check attempt budget** — decrement `remaining_attempts`; if zero, `approval_needed=true` and recommend `assistance_request.md` or termination.
8. **Determine approval need** — `approval_needed=true` if adjustment involves destructive operations, scope expansion, or exceeds original budget.
9. **Return** — emit adjusted plan, change summary, risk delta, approval flag, remaining attempts.

## Failure Modes

| Condition | Response |
|---|---|
| All replanning attempts exhausted | `adjusted_plan=null`, `approval_needed=true`, route to `assistance_request.md` or `recursion_or_termination.md` |
| Adjustment introduces dependency cycle | Reject adjustment, try alternative fix; if none, `approval_needed=true` |
| Risk delta exceeds acceptable threshold | `approval_needed=true`; `change_summary` includes risk mitigation options |
| Frozen task must be modified to fix gap | Mark frozen task as partially unfrozen with audit trail; attempt minimal change; if impossible, `approval_needed=true` |
| Root cause identified as fundamental goal impossibility | `adjusted_plan=null`, route to `recursion_or_termination.md` with termination recommendation |
| Visual QA discrepancies persist after max iterations | Set `human_escalation_reason`; `adjusted_plan` contains only final report + human approval sub-task |
