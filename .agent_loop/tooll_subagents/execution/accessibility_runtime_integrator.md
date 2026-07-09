# Accessibility Runtime Integrator

## Role
Execution agent that materializes the accessibility checker plan into deterministic static audits using `runtime/accessibility/AccessibilityEngine`. Runs file-system-only checks on generated Next.js files and produces a structured accessibility report.

## Contract

### Receives
- `checker_plan`: from `accessibility_checker_planner.md`
- `target_dir`: str — Next.js project root
- `safe_component_manifest`: optional list of generated safe components from `design_to_code_planner.md`
- `optimization_plan`: from `analytics_optimizer.md` or `i18n_optimizer.md` when relevant

### Returns
- `accessibility_report`: dict — {
  - `status`: enum (`passed`, `failed`, `needs_refinement`, `not_applicable`)
  - `violations`: list of { `severity`, `file`, `line`, `check`, `message`, `suggestion` }
  - `score`: float 0–1
  - `files_audited`: list[str]
  - `next_phase_hint`: enum (`observability`, `execution`, `result`)
}

### Side effects
- Reads generated Next.js files under `target_dir`
- Logs report summary to `audit_logger.md`
- No writes to the project source

## Decision Flow

1. **Validate target directory** — ensure `target_dir` contains `package.json`; abort if not.
2. **Build config** — create `AccessibilityConfig(level=checker_plan.level, checks=checker_plan.static_checks, contrast_threshold_normal=..., contrast_threshold_large=...)`.
3. **Run static engine** — instantiate `AccessibilityEngine(target_dir, config)` and call `.run()`.
4. **Classify status** — `passed` when score == 1.0 and no violations; `needs_refinement` when violations exist; `failed` when config errors or unreadable project; `not_applicable` when no files match.
5. **Route browser checks** — if `checker_plan.browser_checks` is non-empty and `tools_browser/headless_automation` is available, schedule a follow-up observation via `tools_browser/headless_automation/visual_qa_agent.md`; otherwise append note that browser checks are deferred.
6. **Log to audit** — append `accessibility_report` summary to `audit_logger.md`.
7. **Return report** with hint `observability` when violations need audit, `result` when passed.

## Failure Modes

| Condition | Response |
|---|---|
| Target directory not a Next.js project | `failed`; `next_phase_hint=result`; log to `audit_logger.md` |
| `file_system_guard.md` blocks reads | Abort; route to `tooll_subagents/execution/human_approval.md` |
| AccessibilityEngine raises exception | `failed`; include exception reason in report |
| No files audited | `not_applicable`; hint `result` |
| Violations found | `needs_refinement`; hint `observability` |
