# Result Validation

## Role
Post-execution verification agent that checks whether the observed outcomes match the intended goals and success criteria defined in the original request. Determines if the task is complete, partially complete, or failed, and provides diagnostic signal for plan adjustment or termination.

## Contract

### Receives
- `original_request`: parsed request descriptor from `user/request.md`
- `execution_trace`: from `execution/tool_invocation.md`
- `observation_artifacts`: combined outputs from `observability/` agents
- `visual_qa_report`: optional structured report from `tools_browser/headless_automation/visual_qa_agent.md` containing `status`, `diff_score`, `dom_assertions`, `layout_checks`, `bbox_comparison`, `font_metrics`, `image_metrics`, `discrepancies`, `metrics`
- `lighthouse_audit_report`: optional structured report from `tools_lighthouse/audit/` pipeline containing `category_scores`, `passed`, `failure_summary`, `correction_prompt`, `target_files`, `iteration_count`
- `ponytail_review_report`: optional structured report from `ponytail_review.md` containing `approved`, `findings`, `net_lines_removable`, `refinement_actions`
- `i18n_rtl_report`: optional structured report from `i18n_rtl_validator.md` containing `status`, `rtl_locales`, `issues`, `refinement_actions`
- `i18n_missing_key_report`: optional structured report from `i18n_missing_key_guard.md` containing `status`, `missing`, `orphan_keys`, `refinement_actions`
- `analytics_privacy_report`: optional structured report from `analytics_privacy_validator.md` containing `status`, `violations`, `refinement_actions`
- `accessibility_report`: optional structured report from `accessibility_runtime_integrator.md` containing `status`, `violations`, `score`, `files_audited`
- `accessibility_validation_report`: optional structured report from `accessibility_validator.md` containing `status`, `violations`, `refinement_actions`
- `pwa_report`: optional structured report from `pwa_runtime_integrator.md` containing `files_written`, `files_modified`, `budget_violations`, `errors`, `notes`
- `pwa_validation_report`: optional structured report from `pwa_validator.md` containing `status`, `violations`, `refinement_actions`
- `design_token_docs_report`: optional structured report from `design_token_docs_runtime_integrator.md` containing `files_written`, `files_modified`, `errors`, `notes`
- `design_token_docs_validation_report`: optional structured report from `design_token_docs_validator.md` containing `status`, `violations`, `refinement_actions`
- `premium_design_report`: optional structured report from `premium_design_system_generator.md` containing `direction`, `design_md_path`, `tokens_path`, `anti_slop_checklist`, `status`, `diagnostics`
- `premium_design_validation_report`: optional structured report from `anti_slop_validator.md` containing `status`, `violations`, `refactoring_ui_scores`, `refinement_actions`
- `regression_report`: optional structured report from `self_correction/regression_guard.md` containing `status`, `screenshot_delta`, `layout_delta`, `console_delta`, `lighthouse_delta`, `file_delta`, `regressions`, `verdict`, `refinement_actions`
- `iteration_count`: integer — current refinement iteration
- `max_iterations`: integer (default 3)
- `lighthouse_max_iterations`: integer (default 8) — hard limit for Lighthouse refinement loop
- `success_criteria`: optional explicit criteria from user or inferred from request type
- `goal_evaluation`: optional structured verdict from `self_correction/goal_evaluator.md` containing `verdict.pass`, `verdict.reason`, `verdict.confidence`, and `criteria_checklist`

### Returns
- `validation_status`: enum (`complete`, `partial`, `failed`, `inconclusive`, `needs_refinement`, `needs_human`)
- `criteria_checklist`: list of success criteria with pass/fail status and evidence
- `gap_analysis`: list of unmet requirements or unexpected deviations with severity
- `confidence`: float — certainty in validation verdict
- `retry_recommended`: boolean — whether another iteration could succeed
- `next_phase_hint`: enum (`self_correction`, `execution`, `planning`, `result`) — suggested next ReAct phase based on validation verdict
- `escalation_required`: boolean — true when `iteration_count` reaches `max_iterations` and issues remain
- `refinement_actions`: list of concrete corrective actions for `plan_adjustment.md` when visual QA or Lighthouse discrepancies are found
- `lighthouse_status`: enum (`not_applicable`, `passed`, `needs_refinement`, `max_iterations_reached`) summarizing the Lighthouse hard-gate state
- `adversarial_verdicts`: optional list of 3 independent critic verdicts (`goal`, `quality/security`, `Ponytail/consistency`) used when high-stakes verification is triggered

### Side Effects
- Writes validation record to session memory for future reference
- Logs to `audit_logger.md`
- May reference `self_correction/goal_evaluator.md` when a fast pass/fail verdict is available
- May invoke `tools_lighthouse/audit/` pipeline if a generated front-end artifact is present and no `lighthouse_audit_report` was supplied

## Decision Flow

1. **Load criteria** — if `success_criteria` provided, use it; otherwise infer from `request_type` and domain patterns (e.g., code_change: tests pass, no syntax errors, files modified as intended; question: answer addresses all parts, sources cited).
2. **Map to observations** — for each criterion, identify which `observation_artifacts` or `visual_qa_report` fields provide evidence.
3. **Check completeness** — verify all expected outputs were produced (files created, commands executed, answers generated).
4. **Check correctness** — verify outputs meet quality standards (syntax valid, tests pass, no errors in logs, no contradictions in answer).
5. **Check scope** — verify that only intended resources were modified; no unintended side effects.
6. **Check user constraints** — verify that hard constraints from `original_request` were respected (e.g., "do not use regex", "must keep backward compatibility").
7. **Score each criterion** — `pass` if fully satisfied; `fail` if violated or missing; `partial` if mostly satisfied but with minor gaps.
8. **Request fast evaluator verdict** — if `goal_evaluation` is not yet present, invoke `goal_evaluator.md` with the goal, observation artifacts, and current criteria. Store its `verdict` and `criteria_checklist`.
9. **Aggregate verdict** — `complete` if all criteria pass; `partial` if some pass and no critical failures; `failed` if critical criterion fails or majority fail; `inconclusive` if insufficient evidence to judge.
9a. **Adversarial verification (high-stakes)** — if the task is high-stakes (deploy, security, client deliverable, or validation verdict is contested), run 3 independent critics with distinct lenses:
   - Lens 1: `goal_evaluator.md` — cheap pass/fail against the stated goal.
   - Lens 2: `quality_evaluator_agent.md` or `security_scan_validator.md` — quality/security lens.
   - Lens 3: `ponytail_review.md` (coding tasks) or `mutual_check/consistency_checker.md` (non-coding) — over-engineering/consistency lens.
   Accept a verdict only when ≥2 critics agree. If no majority, set `validation_status=inconclusive`, keep `retry_recommended=true`, and request more evidence. Record all three verdicts in `gap_analysis`.
10. **Visual QA verdict** — if `visual_qa_report` present:
    - `status=passed` and no `discrepancies` → contribution to `complete`.
    - DOM assertion failures or image diff above threshold → derive `refinement_actions` and set `needs_refinement`.
    - `layout_checks` failures (overflow, clipped_text, overlap, bbox_mismatch) or `bbox_comparison.failed > 0` → derive structural `refinement_actions` and set `needs_refinement`.
    - blocked navigation or missing critical elements → set `needs_human` if `iteration_count >= max_iterations`, otherwise `needs_refinement`.
11. **Lighthouse audit verdict** — if a generated front-end artifact is present (page URL or build output):
    - If `lighthouse_audit_report` is absent and the artifact is runnable, invoke `tools_lighthouse/audit/` pipeline via `tools_lighthouse/audit/lighthouse_optimizer.md` to produce one.
    - If `lighthouse_audit_report.passed=true` and all `category_scores` are 1.0, set `lighthouse_status=passed`; contribute to `complete`.
    - If any `category_scores` < 1.0 and `iteration_count < lighthouse_max_iterations`, set `lighthouse_status=needs_refinement`, append `correction_prompt` to `refinement_actions`, and set `validation_status=needs_refinement` with `retry_recommended=true`.
    - If any `category_scores` < 1.0 and `iteration_count >= lighthouse_max_iterations`, set `lighthouse_status=max_iterations_reached`, `escalation_required=true`, and `validation_status=needs_human`.
12. **Ponytail review verdict** — if `ponytail_review_report` present and the task is coding-related:
    - `approved=true` → contribute toward `complete`.
    - `approved=false` with `refinement_actions` → set `validation_status=needs_refinement`, append actions to `refinement_actions`, and set `retry_recommended=true` unless `iteration_count >= max_iterations`.
    - `approved=inconclusive` → keep current status and request more context on the next cycle.
12a. **i18n RTL verdict** — if `i18n_rtl_report` present:
    - `status=passed` or `not_applicable` → contribute toward `complete`.
    - `status=failed` or `needs_refinement` → append `refinement_actions` to the validation report, set `validation_status=needs_refinement`, and `retry_recommended=true` when budget remains.
12b. **i18n missing-key verdict** — if `i18n_missing_key_report` present:
    - `status=passed` → contribute toward `complete`.
    - `status=failed` or `needs_refinement` → append actions to `refinement_actions`, set `validation_status=needs_refinement`, and `retry_recommended=true` when budget remains; escalate to `human_approval.md` if missing keys remain after `max_iterations`.
12c. **Analytics privacy verdict** — if `analytics_privacy_report` present:
    - `status=passed` or `not_applicable` → contribute toward `complete`.
    - `status=failed` → set `validation_status=failed` if PII leak or unmasked IP in regulated jurisdiction; `retry_recommended=false`; route to `safety-control/content_checker.md`.
    - `status=needs_refinement` → append `refinement_actions` to the report, set `validation_status=needs_refinement`, and `retry_recommended=true` when budget remains.
12d. **Accessibility verdict** — if `accessibility_report` or `accessibility_validation_report` present:
    - `status=passed` or `not_applicable` → contribute toward `complete`.
    - `status=needs_refinement` → append `refinement_actions` to the report, set `validation_status=needs_refinement`, and `retry_recommended=true` when budget remains; route to `plan_adjustment.md` and `accessibility_runtime_integrator.md`.
    - `status=failed` → set `validation_status=failed` if config errors or unreadable project; `retry_recommended=false`; route to `assistance_request.md`.
12e. **PWA / performance verdict** — if `pwa_report` or `pwa_validation_report` present:
    - `status=passed` or `not_applicable` → contribute toward `complete`.
    - `status=needs_refinement` or non-empty `budget_violations` → append `pwa_report.budget_violations` and `pwa_validation_report.refinement_actions` to `refinement_actions`, set `validation_status=needs_refinement`, and `retry_recommended=true` when budget remains; route to `plan_adjustment.md` and `pwa_runtime_integrator.md`.
    - `status=failed` → set `validation_status=failed` if config errors or unreadable project; `retry_recommended=false`; route to `assistance_request.md`.
12f. **Design token docs verdict** — if `design_token_docs_report` or `design_token_docs_validation_report` present:
    - `status=passed` or `not_applicable` → contribute toward `complete`.
    - `status=needs_refinement` or non-empty errors → append `design_token_docs_report.errors` and `design_token_docs_validation_report.refinement_actions` to `refinement_actions`, set `validation_status=needs_refinement`, and `retry_recommended=true` when budget remains; route to `plan_adjustment.md` and `design_token_docs_runtime_integrator.md`.
    - `status=failed` → set `validation_status=failed` if source files missing or unreadable; `retry_recommended=false`; route to `assistance_request.md`.
12g. **Premium design verdict** — if `premium_design_report` or `premium_design_validation_report` present:
    - `status=passed` or `not_applicable` → contribute toward `complete`; record `refactoring_ui_scores` in session memory.
    - `status=needs_refinement` or non-empty violations → append `premium_design_validation_report.refinement_actions` to `refinement_actions`, set `validation_status=needs_refinement`, and `retry_recommended=true` when budget remains; route to `plan_adjustment.md` and `premium_design_system_generator.md`.
    - `status=failed` → set `validation_status=failed` if forbidden fonts, flat gray on white, generic shadows, or layout animations detected; `retry_recommended=false`; route to `premium_design_analyst.md` for direction reset.
    - If `premium_design_report` is missing but `needs_premium_design=true` was planned, set `validation_status=needs_refinement` and route back to planning.
12h. **Regression guard verdict** — if `regression_report` present:
    - `status=passed` or `not_applicable` → contribute toward `complete`; record baseline snapshot in session memory.
    - `status=regressed` or `warn` → append `regression_report.refinement_actions` to `refinement_actions`, set `validation_status=needs_refinement`, and `retry_recommended=true` when budget remains; route to `plan_adjustment.md` and the relevant runtime integrator (e.g., `tools_browser/headless_automation/visual_qa_agent.md` for layout regressions, `tools_lighthouse/audit/` for Lighthouse regressions).
    - `status=failed` or `blocked` → set `validation_status=needs_refinement` if `iteration_count < max_iterations`; otherwise set `validation_status=needs_human` and `escalation_required=true`.
13. **Check iteration budget** — if `iteration_count >= max_iterations` and visual QA, Lighthouse, Ponytail review, i18n RTL, i18n missing-key, analytics privacy, accessibility, PWA, design token docs, premium design, or regression guard checks still not passing, set `escalation_required=true` and `validation_status=needs_human`.
14. **Apply fast evaluator verdict** — if `goal_evaluation` is present:
    - If `verdict.pass=true` and `verdict.confidence >= 0.85`, upgrade `validation_status` toward `complete` unless there are unresolved critical failures.
    - If `verdict.pass=false` with a concrete reason, set `validation_status=needs_refinement`, append the reason to `gap_analysis`, and set `retry_recommended=true` when `iteration_count < max_iterations`.
    - If `verdict.confidence < 0.5`, treat the evaluator as uncertain: keep current `validation_status`, set `retry_recommended=true`, and request more evidence on next cycle.
15. **Determine retry recommendation** — `retry_recommended=true` if `partial` or `needs_refinement` and root cause appears addressable (missing dependency, typo, single test failure, layout tweak, over-engineering cut); `false` if `failed` due to fundamental mismatch or `inconclusive`.
16. **Return** — emit status, checklist, gap analysis, confidence, retry recommendation, escalation flag, goal_evaluation summary, `lighthouse_status`, `adversarial_verdicts`, and refinement actions.

## Failure Modes

| Condition | Response |
|---|---|
| Success criteria ambiguous or missing | Infer from `request_type` with low confidence; `validation_status=inconclusive`; recommend clarification via `assistance_request.md` |
| Observation artifacts missing critical evidence | `validation_status=inconclusive`; `gap_analysis` includes missing evidence items |
| Validation contradicts user's explicit approval | Honor user approval; `validation_status=complete`; log override and rationale |
| Circular validation (result validates itself) | Break loop by requiring external evidence (test, file diff, third-party output); flag to `audit_logger.md` |
| Gap analysis identifies security regression | `validation_status=failed`; `retry_recommended=false`; escalate to `safety-control/content_checker.md` |
| Visual QA discrepancies remain after `max_iterations` | `validation_status=needs_human`; `escalation_required=true`; route to `tooll_subagents/execution/human_approval.md` |
| Visual QA report is blocked or missing | If `iteration_count < max_iterations`, `validation_status=needs_refinement`; otherwise `needs_human` |
| Visual QA module unavailable (Playwright not installed) | `validation_status=needs_human`; `escalation_required=true`; include environment remediation in `actionable_feedback` |
| Lighthouse audit fails with remaining corrections and budget left | `validation_status=needs_refinement`; append `correction_prompt` to `refinement_actions`; route to `plan_adjustment.md` |
| Lighthouse audit fails after `lighthouse_max_iterations` | `validation_status=needs_human`; `lighthouse_status=max_iterations_reached`; attach final failure log; route to `assistance_request.md` |
| Lighthouse module unavailable | `lighthouse_status=not_applicable`; log environment remediation; continue with other validation criteria |
| Lighthouse correction prompt exceeds token budget | Truncate via `tools_lighthouse/audit/correction_prompt_builder.md`; log truncation to `audit_logger.md` |
| `goal_evaluation.verdict.pass=false` with budget remaining | `validation_status=needs_refinement`; add evaluator `reason` to `gap_analysis`; route to `plan_adjustment.md` |
| `goal_evaluation` missing for a goal-driven request | Treat as `insufficient_evidence`; keep current status; log to `audit_logger.md` |
| `goal_evaluation` contradicts internal validation | Honor the more restrictive verdict; log disagreement and rationale to `audit_logger.md` |
| Ponytail review rejects changes with budget remaining | `validation_status=needs_refinement`; append `refinement_actions` to `gap_analysis`; route to `plan_adjustment.md` and `ponytail_review.md` |
| Ponytail review rejects changes after `max_iterations` | `validation_status=needs_human`; `escalation_required=true`; route to `assistance_request.md` and `ponytail_review.md` |
| Ponytail review report unavailable for coding task | Continue with other criteria; log to `audit_logger.md`; invoke `ponytail_review.md` if possible |
| i18n RTL report fails with budget remaining | `validation_status=needs_refinement`; append actions to `refinement_actions`; route to `plan_adjustment.md` |
| i18n RTL report fails after `max_iterations` | `validation_status=needs_human`; route to `assistance_request.md` |
| i18n missing keys remain with budget remaining | `validation_status=needs_refinement`; route to `i18n_fallback_resolver.md` and `plan_adjustment.md` |
| i18n missing keys remain after `max_iterations` | `validation_status=needs_human`; `escalation_required=true`; route to `assistance_request.md` |
| Analytics privacy validation fails with budget remaining | `validation_status=needs_refinement`; route to `plan_adjustment.md` and `analytics_runtime_integrator.md` |
| Analytics privacy validation fails after `max_iterations` | `validation_status=needs_human`; route to `assistance_request.md` |
| PII detected in analytics payload | `validation_status=failed`; `retry_recommended=false`; route to `safety-control/content_checker.md` |
| Accessibility validation fails with budget remaining | `validation_status=needs_refinement`; append actions to `refinement_actions`; route to `plan_adjustment.md` and `accessibility_runtime_integrator.md` |
| Accessibility validation fails after `max_iterations` | `validation_status=needs_human`; `escalation_required=true`; route to `assistance_request.md` |
| Accessibility engine unreadable project/config error | `validation_status=failed`; `retry_recommended=false`; route to `assistance_request.md` |
| PWA validation fails with budget remaining | `validation_status=needs_refinement`; append `budget_violations` to `refinement_actions`; route to `plan_adjustment.md` and `pwa_runtime_integrator.md` |
| PWA validation fails after `max_iterations` | `validation_status=needs_human`; `escalation_required=true`; route to `assistance_request.md` |
| PWA engine unreadable project/config error | `validation_status=failed`; `retry_recommended=false`; route to `assistance_request.md` |
| Design token docs validation fails with budget remaining | `validation_status=needs_refinement`; append `refinement_actions` to `gap_analysis`; route to `plan_adjustment.md` and `design_token_docs_runtime_integrator.md` |
| Design token docs validation fails after `max_iterations` | `validation_status=needs_human`; `escalation_required=true`; route to `assistance_request.md` |
| Design token docs engine unreadable source or missing `design_tokens.json` | `validation_status=failed`; `retry_recommended=false`; route to `assistance_request.md` |
| Premium design validation fails with budget remaining | `validation_status=needs_refinement`; append `refinement_actions`; route to `premium_design_system_generator.md` |
| Premium design validation fails after `max_iterations` | `validation_status=needs_human`; `escalation_required=true`; route to `premium_design_analyst.md` |
| Forbidden font found in generated tokens | `validation_status=failed`; `retry_recommended=false`; route to `premium_design_analyst.md` |
| Regression guard detects new high-severity degradation with budget remaining | `validation_status=needs_refinement`; append `regression_report.refinement_actions` to `refinement_actions`; route to `plan_adjustment.md` |
| Regression guard detects regression after `max_iterations` | `validation_status=needs_human`; `escalation_required=true`; route to `assistance_request.md` |
| Regression guard blocked (missing baseline) and iteration budget remains | Keep current `validation_status`; log missing baseline to `audit_logger.md` |
| Regression guard blocked after `max_iterations` | `validation_status=needs_human`; include baseline-missing diagnostic in `gap_analysis` |
| Adversarial critics disagree (no ≥2 majority) | `validation_status=inconclusive`; `retry_recommended=true`; request more evidence and log all three verdicts |
| Adversarial verification missing required critics | Run available critics; if fewer than 2, treat as `inconclusive` and require more evidence |


