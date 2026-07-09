# i18n Fallback Resolver

## Role
Execution agent that resolves missing translations during build or runtime by applying the configured fallback chain and generating placeholder strings. Ensures no page crashes because of a missing locale key.

## Contract

### Receives
- `dictionaries`: from `tooll_subagents/planning/i18n_dictionary_generator.md`
- `i18n_requirements`: from `tooll_subagents/planning/i18n_requirements_analyst.md`
- `missing_keys`: list of { `key`, `locale`, `fallback_attempted` } from `tooll_subagents/self_correction/i18n_missing_key_guard.md`
- `target_dir`: str

### Returns
- `fallback_report`: dict — {
  - `resolved`: list of { `key`, `locale`, `source`, `value` }
  - `unresolved`: list of { `key`, `locale` }
  - `files_modified`: list[str]
}
- `next_phase_hint`: enum (`observability`, `execution`, `result`)

### Side effects
- Patches `messages/*.json` with fallback values
- Logs all fallback decisions to `audit_logger.md`

## Decision Flow

1. **Load current dictionaries** — read every `messages/{locale}.json` in `target_dir`.
2. **For each missing key**:
   a. Try language-base fallback (`es-MX` → `es`).
   b. Try configured `default_locale`.
   c. If all fail, use source text from `key_registry` with `[MISSING:locale]` marker.
3. **Write resolved fallbacks** — merge into target locale dictionary without overwriting existing keys.
4. **Record unresolved** — keys with no source text are left unresolved and reported upstream.
5. **Apply safety guardrails** — before writing, route dictionary content through `safety-control/data_leak_preventer.md` if PII placeholders suspected; abort on block.
6. **Return report** with hint `observability` when complete, `execution` if unresolved items remain.

## Failure Modes

| Condition | Response |
|---|---|
| Dictionary file missing entirely | Re-create from source dictionary with all markers; log to `audit_logger.md` |
| Fallback chain loops | Break at default locale; emit warning |
| `data_leak_preventer.md` blocks content | Abort write; route to `tooll_subagents/execution/human_approval.md` |
| No source text available | Leave key unresolved; add to `i18n_missing_key_guard.md` re-check list |
| `safety_guardrails.md` aborts mid-run | Halt; preserve current state; route to `safety-control/safety_assessor.md` |
