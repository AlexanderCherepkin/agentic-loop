# Preview Audit Agent

## Role
Observability agent that audits the final preview and approval workflow for report completeness, screenshot capture, feedback state, and refinement hints. Produces a structured report consumed by `tooll_subagents/result/action_report.md` and `safety-control/mutual_check/quality_assessor.md`.

## Contract

### Receives
- `preview_requirements`: from `tooll_subagents/planning/preview_planner.md`
- `preview_integration_report`: from `tooll_subagents/execution/preview_runtime_integrator.md`
- `validation_report`: from `tooll_subagents/self_correction/preview_validator.md`
- `visual_qa_report`: optional structured report from `tools_browser/headless_automation/visual_qa_agent.md`

### Returns
- `audit_report`: dict — {
  - `overall_status`: enum (`pass`, `warn`, `fail`)
  - `preview_status`: str
  - `screenshot_present`: bool
  - `preview_html_present`: bool
  - `feedback_present`: bool
  - `approved`: bool | None
  - `refinement_hints_count`: int
  - `recommendations`: list[str]
}
- `next_phase_hint`: enum (`observability`, `result`)

### Side effects
- Writes audit record to `audit_logger.md`
- No code changes

## Decision Flow

1. **Check requirements coverage** — if `needs_preview` is false, return `pass` with no further checks.
2. **Check preview status** — `blocked`/`unknown` → `fail`; `awaiting_feedback` → `warn`; `approved` → `pass`; `rejected` → `fail`.
3. **Check artifacts** — verify screenshot and preview HTML paths are present.
4. **Check feedback file** — verify feedback template or client response file exists.
5. **Check refinement hints** — if rejected, ensure `refinement_hints` are non-empty and actionable.
6. **Cross-check visual QA** — if `visual_qa_report` shows regressions, merge into recommendations.
7. **Generate recommendations** — suggest shorter feedback timeout, additional viewports, or auto-approve policy.
8. **Log to audit** — append findings to `audit_logger.md`.
9. **Return report** with hint `result`.

## Failure Modes

| Condition | Response |
|---|---|
| Preview status blocked/unknown | `fail`; recommend re-run `preview_runtime_integrator.md` |
| Feedback rejected without hints | `fail`; route to `plan_adjustment.md` |
| Missing screenshot/HTML | `warn`; continue with hint `result` |
| Awaiting feedback | `warn`; hint `result` (human action required) |
| `audit_logger.md` unavailable | Keep report in memory; continue |
