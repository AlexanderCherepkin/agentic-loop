# Design Token Docs Validator

## Role
Self-correction agent that validates the design-token documentation report against the original requirements and the generated project state. Translates missing sections, parse errors, and incomplete handoff artifacts into concrete corrective actions for `plan_adjustment.md`.

## Contract

### Receives
- `design_token_docs_requirements`: from `tooll_subagents/planning/design_token_docs_requirements_analyst.md`
- `design_token_docs_plan`: from `tooll_subagents/planning/design_token_docs_format_selector.md`
- `design_token_docs_report`: from `tooll_subagents/execution/design_token_docs_runtime_integrator.md`

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

1. **Short-circuit if no requirements** — if `generate_docs` is false, return `not_applicable`.
2. **Check required artifacts** — verify every format in `design_token_docs_plan.formats` has a corresponding file in `files_written` or pre-existed.
3. **Check sections** — ensure at least `colors` or `typography` is present when token data exists; if `components` was requested, verify registry was loaded.
4. **Evaluate errors** — for each engine error, build a concrete refinement action (fix source path, regenerate tokens, repair registry JSON).
5. **Check audience fit** — if `target_audience=client` and `html` is missing but requested, flag `needs_refinement`.
6. **Emit refinement actions** — prioritize source/fix actions first, then format additions.
7. **Return report** with hint `execution` if violations exist, `result` if passed.

## Failure Modes

| Condition | Response |
|---|---|
| Engine not reachable | `failed`; action = verify runtime dependencies |
| Required artifact missing | `needs_refinement`; route to `design_token_docs_runtime_integrator.md` |
| Token source empty | `needs_refinement`; action = re-run `figma_extract_tokens` |
| All checks pass | `passed`; hint `result` |
