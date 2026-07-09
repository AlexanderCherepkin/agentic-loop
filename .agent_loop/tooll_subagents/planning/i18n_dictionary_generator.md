# i18n Dictionary Generator

## Role
Planning agent that generates translated dictionaries for every target locale from the key registry. Uses LLM translation with context preservation, fallback chains, and deterministic output structure for `next-intl` `messages/*.json`.

## Contract

### Receives
- `key_registry`: from `i18n_key_extractor.md`
- `i18n_requirements`: from `i18n_requirements_analyst.md`
- `language_profile`: from `i18n_language_detector.md`
- `llm_client`: optional handle to `runtime/engine/llm_engine.py`

### Returns
- `dictionaries`: dict[str, dict] — mapping `locale` → nested JSON object of namespaces/keys
- `translation_report`: dict — {
  - `locales`: list[str]
  - `translated_keys`: int
  - `fallback_keys`: int
  - `errors`: list of { `key`, `locale`, `reason` }
  - `warnings`: list[str]
}
- `next_phase_hint`: enum (`planning`, `execution`, `result`)

### Side effects
- May call LLM for translations
- Logs translation report to `audit_logger.md`
- No filesystem writes

## Decision Flow

1. **Build source dictionary** — convert `key_registry.keys` into nested JSON by namespace/key.
2. **Identify source locale** — use `language_profile.detected_primary_locale` or `i18n_requirements.default_locale`.
3. **Translate per target locale** — for each locale except source, send batches of source strings with section context to LLM. Request same structure and variable placeholder preservation (`{name}`, `{count}`).
4. **Preserve interpolations** — ensure output strings keep `{placeholder}` tokens unchanged; flag any divergence.
5. **Apply fallback chain** — if region variant (e.g., `es-MX`) translation missing, fall back to language base (`es`), then `default_locale`.
6. **Validate output structure** — each locale dictionary must mirror source key hierarchy; record mismatches as errors.
7. **RTL awareness** — for RTL locales, prepend `[RTL]` marker in `warnings` so `i18n_rtl_validator.md` can enforce layout.
8. **Return dictionaries** with routing hint `planning` when translations exist, `result` if `translation_scope=none`.

## Failure Modes

| Condition | Response |
|---|---|
| LLM unavailable | Return source dictionary for all locales plus `fallback_keys=all`; emit warning |
| Translation output malformed JSON | Attempt to repair with deterministic parser; if repair fails, mark key as error and fall back to source |
| Placeholder lost in translation | Re-inject original placeholder; log repair to `translation_report.errors` |
| Target locale unsupported by LLM | Fall back to source string; emit warning |
| Batch exceeds token budget | Split into smaller batches by namespace; continue until all keys processed |
