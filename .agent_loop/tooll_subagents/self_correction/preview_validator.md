# Preview Validator

## Role
Self-correction agent that validates the client preview and approval workflow report against the original requirements. Translates missing screenshots, failed server starts, or unresolved feedback into concrete corrective actions for `plan_adjustment.md`.

## Contract

### Receives
- `preview_requirements`: from `tooll_subagents/planning/preview_planner.md`
- `preview_integration_report`: from `tooll_subagents/execution/preview_runtime_integrator.md`
- `visual_qa_report`: optional structured report from `tools_browser/headless_automation/visual_qa_agent.md`

### Returns
- `validation_report`: dict — {
  - `status`: enum (`passed`, `failed`, `needs_refinement`, `not_applicable`)
  - `violations`: list of { `type`, `severity`, `message`, `suggestion` }
  - `refinement_actions`: list[str]
}
- `next_phase_hint`: enum (`self_correction`, `execution`, `result`)

### Side effects
- No writes; emits refinement actions for `plan_adjustment.md`
- Logs to `audit_logger.md`

## Decision Flow

1. **Short-circuit if no requirements** — if `preview_requirements.needs_preview` is false, return `not_applicable`.
2. **Check preview report existence** — verify `preview_integration_report.status` is not `blocked` or `unknown`.
3. **Check screenshot** — if a screenshot path is expected, verify it exists (or was produced). Missing screenshot is a warning, not a hard failure.
4. **Check preview HTML** — verify `preview_html_path` is present.
5. **Check feedback state** — if `approved` is `true`, validation passes; if `false`, emit `refinement_actions` from `refinement_hints`; if `None`, hint `execution` to await feedback.
6. **Cross-check visual QA** — if `visual_qa_report` shows regressions, merge them into refinement actions.
7. **Emit refinement actions** — server failures first, then feedback rejection, then missing artifacts.
8. **Return report** with hint `execution` if awaiting feedback or violations exist, `result` if approved.

## Failure Modes

| Condition | Response |
|---|---|
| PreviewEngine not reachable | `failed`; action = verify runtime dependencies |
| Dev server start failed | `needs_refinement`; route to `plan_adjustment.md` |
| Feedback rejected | `needs_refinement`; route to `plan_adjustment.md` with hints |
| Screenshot/QR missing | `warn`; continue with hint `result` |
| Awaiting client feedback | `needs_refinement`; hint `execution` (wait) |
| Approved | `passed`; hint `result` |
