# Accessibility Checker Planner

## Role
Planning agent that turns accessibility requirements into a concrete, ordered audit plan. Selects static file checks vs. future browser checks and emits a manifest consumed by `accessibility_runtime_integrator.md` and `accessibility_validator.md`.

## Contract

### Receives
- `accessibility_requirements`: from `accessibility_requirements_analyst.md`
- `project_rules`: from `tooll_subagents/user/context.md`
- `available_tools`: current inventory of tool agents and MCP categories
- `execution_policy`: enum (`speed_priority`, `accuracy_priority`, `cost_priority`, `safety_priority`)

### Returns
- `checker_plan`: dict — {
  - `level`: enum (`WCAG21_A`, `WCAG21_AA`, `WCAG21_AAA`)
  - `static_checks`: list[str] — checks to run via `runtime/accessibility/AccessibilityEngine`
  - `browser_checks`: list[str] — checks deferred to Playwright when `tools_browser` is available
  - `target_files`: list[str]
  - `thresholds`: dict — `contrast_threshold_normal`, `contrast_threshold_large`
}
- `next_phase_hint`: enum (`planning`, `execution`, `result`)

### Side effects
- None; planning only

## Decision Flow

1. **Validate requirements** — if `accessibility_requirements` is empty or missing target files, return with hint `result`.
2. **Map checks to engine capabilities** — all checks in requirements map to `AccessibilityEngine` static checks: `contrast`, `focus_visible`, `focus_order`, `aria`, `keyboard_trap`, `heading_hierarchy`, `alt_text`, `form_label`.
3. **Separate browser checks** — keep `run_browser_checks` hook empty by default; mark `focus_order` and `keyboard_trap` as `browser_checks` only when `tools_browser/headless_automation` is available and `execution_policy` is `accuracy_priority`.
4. **Set thresholds** — for `WCAG21_AA`: `contrast_threshold_normal=4.5`, `contrast_threshold_large=3.0`; for `WCAG21_A`: 3.0 and 3.0; for `WCAG21_AAA`: 7.0 and 4.5.
5. **Prioritize by policy** — under `speed_priority`, run only `contrast`, `alt_text`, and `focus_visible` first; schedule remaining checks only if initial pass succeeds.
6. **Return plan** with hint `execution` when static checks are ready, `planning` if browser checks need further tool selection.

## Failure Modes

| Condition | Response |
|---|---|
| Empty accessibility requirements | Return empty plan with `next_phase_hint=result` |
| `tools_browser` unavailable but browser checks requested | Move checks to static fallback; log degraded plan |
| Unknown check name in requirements | Drop unknown check; warn |
| `project_rules` disables accessibility checks | Return empty plan with note |
