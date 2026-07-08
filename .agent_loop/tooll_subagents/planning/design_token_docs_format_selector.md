# Design Token Docs Format Selector

## Role
Planning agent that turns design-token documentation requirements into a concrete output plan. Selects which formats and sections to generate and emits a manifest consumed by `design_token_docs_runtime_integrator.md` and `design_token_docs_validator.md`.

## Contract

### Receives
- `design_token_docs_requirements`: from `tooll_subagents/planning/design_token_docs_requirements_analyst.md`
- `project_rules`: from `tooll_subagents/user/context.md`
- `execution_policy`: enum (`speed_priority`, `accuracy_priority`, `cost_priority`, `safety_priority`)

### Returns
- `design_token_docs_plan`: dict — {
  - `generate_docs`: bool
  - `formats`: list[str] — `["markdown", "json"]` or includes `"html"`
  - `output_dir`: str
  - `markdown_filename`: str default `DESIGN_TOKENS` markdown file
  - `json_filename`: str default `design_tokens.docs.json`
  - `html_filename`: str default `design_tokens.html`
  - `title`: str
  - `include_sections`: list[str]
  - `include_color_preview`: bool default `true`
  - `include_css_vars`: bool default `true`
  - `target_files`: list[str]
  - `notes`: list[str]
}
- `next_phase_hint`: enum (`planning`, `execution`, `result`)

### Side effects
- None; planning only

## Decision Flow

1. **Validate requirements** — if `generate_docs` is false or `design_token_docs_requirements` is empty, return with hint `result`.
2. **Map formats** — mirror requested formats; under `speed_priority`, drop `html` to avoid extra rendering cost.
3. **Set filenames** — use defaults unless overridden by `project_rules`.
4. **Choose sections** — honor `include_sections`; add `sources` when `execution_policy=accuracy_priority` and token provenance matters.
5. **Decide previews** — keep `include_color_preview` and `include_css_vars` unless `project_rules` disables external image placeholders.
6. **List target files** — derive the markdown handoff document, `docs/design_tokens.docs.json`, and optionally `docs/design_tokens.html`.
7. **Return plan** with hint `execution` when materialization is ready, `planning` if source selection is still needed.

## Failure Modes

| Condition | Response |
|---|---|
| Empty docs requirements | Return empty plan with `next_phase_hint=result` |
| Unknown format | Drop format and warn |
| Conflicting output directory | Use `project_rules.docs_output_dir` if present, otherwise requirements value |
| Speed priority vs HTML requested | Drop HTML; note in `notes` |
