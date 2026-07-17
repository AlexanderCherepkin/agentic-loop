# Project Architect

## Role

Planning agent that turns a `classification` from `project_classifier.md` into a structured architecture manifest (System Design). It selects the stack, defines modules, API surface, data model, auth flows, and deployment strategy so that `project_developer.md` can generate a runnable starter codebase.

## Contract

### Receives
- `classification`: from `tooll_subagents/planning/project_classifier.md`
- `language`: string | None — preferred programming language
- `project_rules`: dict | None
- `template_context`: optional dict from `runtime/project_starter/template_manager.py`

### Returns
- `architecture_manifest`: string — Markdown System Design document
- `adr`: string | None — Architecture Decision Record (if requested)
- `stack`: dict[str, str] — resolved framework, language, database, hosting
- `files_plan`: list[str] — anticipated top-level files/directories
- `confidence`: float 0.0–1.0
- `missing_inputs`: list[str]
- `next_phase_hint`: enum (`planning`, `execution`, `result`)

### Side effects
- Logs manifest generation to `safety-control/mutual_check/audit_logger.md`
- No filesystem writes; downstream agents consume `architecture_manifest`

## Decision Flow

1. **Validate inputs** — require `classification.project_type.base_category`. If missing, set `missing_inputs` and `confidence=0`, route back to `project_classifier.md`.
2. **Resolve language and stack** — use `language` or infer from `classification.confidence_scores`. Match against `project_rules.tooling_preferences` if available.
3. **Invoke runtime architect** — call `runtime/web_project_agents/architect.py` `ProjectArchitect.design()` with the classification and language.
4. **Parse manifest** — extract `stack` (framework, language, database, hosting) and `files_plan` by scanning headings and bullet lists in the returned Markdown.
5. **Generate ADR (conditional)** — if `project_rules.require_adr` is true or `classification.project_type.modules` includes enterprise-level terms (`SaaS`, `LMS`, `Booking`), generate an ADR via the same runtime engine.
6. **Check quality** — if manifest is shorter than 500 chars or lacks key sections (stack, data model, deployment), lower confidence and set `missing_inputs`.
7. **Route** — set `next_phase_hint=execution` and forward to `project_developer.md`. If confidence < 0.6, set `next_phase_hint=planning` and loop through `internal_monologue.md` for refinement.
8. **Audit** — record manifest length, stack, and routing decision to `audit_logger.md`.

## Failure Modes

| Condition | Response |
|---|---|
| Missing classification | Return empty manifest and route back to `project_classifier.md` |
| LLM returns non-JSON Markdown parse error | Treat the whole response as manifest; extract stack heuristically |
| Manifest lacks deployment section | Add a default deployment note and lower confidence |
| Stack conflicts with `project_rules` | Override with `project_rules.tooling_preferences` and log conflict to `audit_logger.md` |
| Safety concern in generated manifest | Route to `safety-control/output_reviewer.md` and `data_leak_preventer.md` |
