# PWA Validator

## Role
Self-correction agent that validates the PWA integration report against the original requirements and the generated project state. Translates budget violations and missing PWA artifacts into concrete corrective actions for `plan_adjustment.md`.

## Contract

### Receives
- `pwa_requirements`: from `tooll_subagents/planning/pwa_requirements_analyst.md`
- `pwa_plan`: from `tooll_subagents/planning/pwa_optimizer.md`
- `pwa_integration_report`: from `tooll_subagents/execution/pwa_runtime_integrator.md`
- `lighthouse_audit_report`: optional structured report from `tools_lighthouse/audit/` pipeline containing `category_scores` and `failure_summary`

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

1. **Short-circuit if no requirements** — if `pwa_requirements` is empty, return `not_applicable`.
2. **Check required artifacts** — verify `public/manifest.json`, `public/sw.js` (if service worker enabled), and offline page (if required) were written or pre-existed.
3. **Evaluate budget violations** — for each violation, build a concrete refinement action (reduce JS/CSS payload, optimize images, subset fonts, limit third-party scripts).
4. **Cross-reference with Lighthouse** — if `lighthouse_audit_report` shows Performance score < 1.0, merge performance-related failures into violations.
5. **Check manifest validity** — ensure manifest contains `name`, `short_name`, `start_url`, `display`, `icons`, `theme_color`, `background_color`.
6. **Emit refinement actions** — prioritize `js`/`css` budget fixes first, then images, then fonts.
7. **Return report** with hint `execution` if violations exist, `result` if passed.

## Failure Modes

| Condition | Response |
|---|---|
| PwaEngine not reachable | `failed`; action = verify runtime dependencies |
| Required artifact missing | `needs_refinement`; route to `pwa_runtime_integrator.md` |
| Critical budget violation unresolved | `needs_refinement`; route to `plan_adjustment.md` |
| Lighthouse Performance score < 1.0 | `needs_refinement`; action = run performance optimization |
| All checks pass | `passed`; hint `result` |
