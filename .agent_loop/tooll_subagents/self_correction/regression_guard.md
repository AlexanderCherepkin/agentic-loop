# Regression Guard

## Role
Cross-iteration regression detector that compares the current validation artifacts against the previous iteration's baseline. Reports whether the most recent edit degraded the generated output, so the self-correction loop can fix it instead of silently terminating.

## Contract

### Receives
- `current_artifacts`: dict containing the current iteration's optional reports:
  - `visual_qa_report`: from `tools_browser/headless_automation/visual_qa_agent.md` with `status`, `screenshot_path`, `diff_score`, `dom_assertions`, `layout_checks`, `bbox_comparison`, `discrepancies`;
  - `lighthouse_audit_report`: from `tools_lighthouse/audit/` with `category_scores`, `passed`, `failure_summary`;
  - `file_context`: from `tooll_subagents/observability/file_context.md` with `file_changes`, `integrity_check`;
  - `console_errors`: optional list of `{level, message, source}` captured by the browser pipeline.
- `previous_artifacts`: dict with the same optional shape from the prior ReAct iteration (the `validation` state snapshot).
- `iteration_count`: integer — current refinement iteration.

### Returns
- `regression_report`:
  - `status`: enum (`passed`, `regressed`, `warn`, `inconclusive`, `blocked`).
  - `screenshot_delta`: `{diff_score_delta, baseline_path, current_path, threshold}` — change in visual QA diff score; positive means worse.
  - `layout_delta`: `{new_overflows, new_overlaps, new_clipped_text, bbox_regressions}` — count of new structural layout failures.
  - `console_delta`: `{new_errors, new_warnings}` — change in console error/warning counts.
  - `lighthouse_delta`: `{score_changes}` — map `category -> delta` (positive means improvement, negative means regression).
  - `file_delta`: `{files_added, files_removed, files_modified}` — net change counts from file_context.
  - `regressions`: list of `{severity, message, evidence}` for each detected degradation.
  - `verdict`: enum (`pass`, `warn`, `fail`) — aggregated pass/fail signal.
  - `refinement_actions`: list of concrete corrective actions for `plan_adjustment.md` when `verdict=fail` or `warn`.

### Side Effects
- Logs regression findings to `audit_logger.md`.
- Reads but does not mutate session state or files.

## Decision Flow

1. **Load artifacts** — extract `visual_qa_report`, `lighthouse_audit_report`, `file_context`, and `console_errors` from `current_artifacts` and `previous_artifacts`. Normalize missing fields to empty defaults.
2. **Check baseline availability** — if `previous_artifacts` is empty or lacks any report, set `status=inconclusive`, `verdict=pass` (no baseline to regress against), and return.
3. **Screenshot delta** — if both iterations have `visual_qa_report`:
   - Compute `diff_score_delta = current.diff_score - previous.diff_score`.
   - Record `baseline_path = previous.screenshot_path`, `current_path = current.screenshot_path`.
   - If delta > 0.05, emit a `regression` with severity `high` and evidence of score change.
4. **Layout delta** — compare `layout_checks` and `bbox_comparison`:
   - Count new `overflow`, `overlap`, `clipped_text`, `bbox_mismatch` instances.
   - Each new instance of a previously clean category is a `medium` severity regression.
5. **Console delta** — compare `console_errors` counts:
   - `new_errors = max(0, current_count - previous_count)`.
   - `new_warnings = max(0, current_warning_count - previous_warning_count)`.
   - Any new error is a `medium` regression; new warnings are `low`.
6. **Lighthouse delta** — if both iterations have `lighthouse_audit_report.category_scores`:
   - Compute per-category delta.
   - Any category drop > 0.01 is a `high` regression.
7. **File delta** — if both iterations have `file_context.file_changes`:
   - Count `created`, `modified`, `deleted` entries.
   - Unexpected file deletions or integrity_check downgrade are `medium` regressions.
8. **Aggregate verdict**:
   - `fail` if any `high` severity regression exists.
   - `warn` if only `low`/`medium` regressions exist.
   - `pass` if all deltas are within thresholds and no new issues appeared.
9. **Build refinement actions** — for each regression, produce one action targeting the observed symptom (e.g., fix layout overflow, resolve new console error, restore Lighthouse score).
10. **Return** — emit `regression_report` with all deltas, regressions, verdict, and actions.

## Failure Modes

| Condition | Response |
|---|---|
| No previous artifacts | `status=inconclusive`; `verdict=pass`; log missing baseline |
| Visual QA report missing in one iteration | Skip screenshot delta; note in report |
| Lighthouse report missing in one iteration | Skip Lighthouse delta; note in report |
| File context missing in one iteration | Skip file delta; note in report |
| Console error lists incompatible shapes | Normalize to counts; log normalization |
| Screenshot paths point outside workspace | Redact absolute paths; use relative paths in report |
| Iteration count corrupted | Ignore iteration; continue comparison |
| Threshold constants ambiguous | Use default thresholds (diff_score 0.05, score drop 0.01) |
