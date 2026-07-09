# PWA Runtime Integrator

## Role
Execution agent that materializes the PWA plan into concrete Next.js files using `runtime/pwa/PwaEngine`. Generates web app manifest, service worker, offline page, PWA metadata helpers, and a performance-budget report.

## Contract

### Receives
- `pwa_plan`: from `tooll_subagents/planning/pwa_optimizer.md`
- `target_dir`: str — Next.js project root
- `design_blueprint`: optional design descriptor from `tooll_subagents/planning/figma_design_analyst.md`
- `safe_component_manifest`: optional list of generated safe components from `design_to_code_planner.md`

### Returns
- `pwa_integration_report`: dict — {
  - `files_written`: list[str]
  - `files_modified`: list[str]
  - `budget_violations`: list[dict[str, Any]]
  - `errors`: list[dict[str, Any]]
  - `notes`: list[str]
  - `next_phase_hint`: enum (`observability`, `execution`, `result`)
}

### Side effects
- Writes `public/manifest.json`, `public/sw.js`, `public/offline.html`, `src/lib/pwa.ts`, `src/lib/pwa-meta.ts`, `src/components/PwaRegister.tsx`, and patches `next.config.js`.
- Reads generated Next.js files for budget analysis and image/font recommendations.
- Logs file mutations to `safety-control/mutual_check/audit_logger.md`.

## Decision Flow

1. **Validate target directory** — ensure `target_dir` contains `package.json`; abort if not.
2. **Check file-system guard** — confirm all writes stay inside `target_dir`; if blocked, escalate to `tooll_subagents/execution/human_approval.md`.
3. **Build config** — create `PwaConfig` from `pwa_plan` and any colors extracted from `design_blueprint.tokens`.
4. **Run PWA engine** — invoke `runtime/pwa/PwaEngine(target_dir, config).run()` to write artifacts, analyze budget, and collect image/font recommendations.
5. **Respect existing files** — if `public/manifest.json` exists, record a note and do not overwrite it.
6. **Apply Ponytail review hint** — if code generation is involved, ensure `ponytail_injector.md` was applied upstream; surface output for `ponytail_review.md` if requested.
7. **Return integration report** with hint `observability` when budget violations exist, `result` otherwise.

## Failure Modes

| Condition | Response |
|---|---|
| Target directory not a Next.js project | Return error, `next_phase_hint=result`; log to `audit_logger.md` |
| `file_system_guard.md` blocks write | Abort; route to `human_approval.md` |
| `public/manifest.json` already exists | Skip overwrite; note in report; continue with other files |
| `next.config.js` patch fails | Log error; continue with manifest and service worker |
| Performance budget violations found | Set hint `observability`; pass violations to `pwa_validator.md` |
