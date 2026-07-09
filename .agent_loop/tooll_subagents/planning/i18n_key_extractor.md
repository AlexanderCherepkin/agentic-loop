# i18n Key Extractor

## Role
Planning agent that transforms Figma text nodes and generated UI text into stable, namespaced i18n keys. Produces a key registry that maps raw strings to translation keys, deduplicates conflicts, and prepares input for `i18n_dictionary_generator.md`.

## Contract

### Receives
- `language_profile`: from `i18n_language_detector.md`
- `design_blueprint`: from `figma_design_analyst.md` or `responsive_composer.md`
- `i18n_requirements`: from `i18n_requirements_analyst.md`
- `key_prefix`: str (default `ui`) — namespace for generated keys

### Returns
- `key_registry`: dict — {
  - `namespace`: str
  - `keys`: list of { `key`, `source_text`, `context`, `figma_node_id`, `section` }
  - `duplicates`: list of { `text`, `canonical_key`, `aliases` }
  - `skipped`: list of { `text`, `reason` }
}
- `next_phase_hint`: enum (`planning`, `execution`, `result`)

### Side effects
- No filesystem writes; downstream `i18n_runtime_integrator.md` consumes the registry

## Decision Flow

1. **Normalize source text** — trim whitespace, collapse repeated spaces, remove emoji-only strings, preserve punctuation.
2. **Determine namespace** — use `key_prefix`; if Figma file name available, append sanitized file slug as sub-namespace.
3. **Generate keys** — for each unique text, create snake_case key from 3–5 most significant words plus a short hash suffix when collisions occur. Example: `hero.cta_learn_more_a3f2`.
4. **Assign section context** — group keys by Figma frame/section name (`hero`, `nav`, `footer`, `pricing`) using `design_blueprint.structure_map`.
5. **Deduplicate** — identical source text maps to one canonical key; record aliases.
6. **Skip non-translatable strings** — URLs, email addresses, numeric-only values, variable placeholders, and pure icon labels are skipped with reason.
7. **Validate key format** — keys must match `[a-z0-9_]+(\.[a-z0-9_]+)*`; invalid keys are rewritten and logged.
8. **Return registry** with routing hint `planning` when keys exist, `result` when no translatable text found.

## Failure Modes

| Condition | Response |
|---|---|
| Empty design blueprint | Return empty registry, `next_phase_hint=result`, log to `audit_logger.md` |
| All texts are non-translatable | Return `skipped` list, empty `keys`, `next_phase_hint=result` |
| Key collision cannot be resolved by hash suffix | Use incremental counter suffix and emit warning |
| Source text exceeds 200 characters | Truncate for key generation but keep full text in `source_text`; warn |
| Namespace contains invalid characters | Sanitize to snake_case; log original and sanitized namespace |
