# CMS Validator

## Role
Self-correction agent that audits generated CMS integration files for completeness, secret safety, and fallback correctness. Produces a validation report consumed by `tooll_subagents/self_correction/result_validation.md` and `tooll_subagents/observability/cms_audit_agent.md`.

## Contract

### Receives
- `cms_source_config`: from `tooll_subagents/planning/cms_source_selector.md`
- `integration_report`: from `tooll_subagents/execution/cms_runtime_integrator.md`
- `target_dir`: str — Next.js project root

### Returns
- `validation_report`: dict — {
  - `status`: enum (`passed`, `failed`, `needs_refinement`, `not_applicable`)
  - `violations`: list of { `severity`, `file`, `message` }
  - `refinement_actions`: list[str]
}
- `next_phase_hint`: enum (`self_correction`, `execution`, `result`)

### Side effects
- No writes; emits refinement actions for `tooll_subagents/self_correction/plan_adjustment.md`
- Logs to `safety-control/mutual_check/audit_logger.md`

## Decision Flow

1. **Short-circuit if no CMS** — if `cms_source_config.enabled=false`, return `not_applicable`.
2. **Check core files** — verify `src/lib/cms.ts`, `src/lib/cms/staticFallback.ts`, and at least one listing page (`src/app/blog/page.tsx`) exist when dynamic sections were requested.
3. **Check env example** — `.env.local.example` must contain source-specific placeholders for external sources; flag missing placeholders as `needs_refinement`.
4. **Check package dependency** — for sources that require an SDK, verify the dependency was added to `package.json`.
5. **Scan for hardcoded secrets** — run `safety-control/data_leak_preventer.md` over `cms_source_config.connection` and generated `.env.local.example`; fail if real tokens/keys detected.
6. **Check source switch coverage** — verify `src/lib/cms.ts` switch includes the selected `source_id` or falls back gracefully.
7. **Check fallback policy** — confirm `fallback_to_static=true` for external sources or note that the site will break if the CMS is unreachable.
8. **Check file-system boundaries** — ensure all generated paths are inside `target_dir`; if not, fail.
9. **Emit refinement actions** — for each violation, specify exact file/line change.
10. **Return report** with hint `execution` if violations found, `result` if passed.

## Failure Modes

| Condition | Response |
|---|---|
| Core CMS file missing | `needs_refinement`; action = re-run `cms_runtime_integrator.md` |
| Real secret in `.env.local.example` or config | `failed`; action = rotate secret and replace with placeholder |
| SDK dependency missing | `needs_refinement`; action = add dependency to `package.json` |
| Generated path outside workspace | `failed`; route to `control/file_system_guard.md` |
| Source switch does not cover selected source | `needs_refinement`; action = extend switch in `src/lib/cms.ts` |
