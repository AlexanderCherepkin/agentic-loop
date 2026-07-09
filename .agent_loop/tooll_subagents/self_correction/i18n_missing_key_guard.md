# i18n Missing Key Guard

## Role
Self-correction agent that scans translated dictionaries and generated code to ensure every translation key referenced by a component exists in every locale dictionary. Reports missing keys and drives the fallback resolver.

## Contract

### Receives
- `dictionaries`: dict[str, dict] from `tooll_subagents/planning/i18n_dictionary_generator.md`
- `rewrite_manifest`: from `tooll_subagents/planning/i18n_component_rewriter.md`
- `target_dir`: str

### Returns
- `missing_key_report`: dict — {
  - `status`: enum (`passed`, `failed`, `needs_refinement`)
  - `missing`: list of { `key`, `locale`, `referencing_files` }
  - `orphan_keys`: list[str] — keys in dictionaries not referenced in code
  - `refinement_actions`: list[str]
}
- `next_phase_hint`: enum (`self_correction`, `execution`, `result`)

### Side effects
- Logs missing keys to `audit_logger.md`

## Decision Flow

1. **Collect referenced keys** — from `rewrite_manifest.replacements`, extract every `key` used in `t(...)` calls.
2. **Flatten dictionaries** — turn each locale dictionary into a flat key set using dot-notation path.
3. **Compare sets** — for each referenced key, verify it exists in every target locale dictionary.
4. **Identify orphan keys** — keys present in dictionaries but not referenced in code (informational, not blocking).
5. **Categorize severity** — missing key in default locale = critical; missing in secondary locale = medium; orphan = low.
6. **Emit actions** — for each missing key, action = run `tooll_subagents/execution/i18n_fallback_resolver.md` or `i18n_dictionary_generator.md` with explicit key list.
7. **Return report** with hint `execution` if missing keys found, `result` if passed.

## Failure Modes

| Condition | Response |
|---|---|
| No dictionaries available | `failed`; action = re-run `i18n_dictionary_generator.md` |
| Component code cannot be parsed | Skip file; list as unresolved |
| Key exists but value is empty string | Treat as missing; trigger fallback |
| All locales missing same key | Critical; route to `plan_adjustment.md` to add source key |
