# i18n Language Detector

## Role
Planning agent that determines the natural language of Figma text nodes and design metadata using LLM-based classification plus script/heuristic fallbacks. Produces a language profile used by `i18n_key_extractor.md` and `i18n_dictionary_generator.md`.

## Contract

### Receives
- `figma_node_json`: path to raw Figma export (`figma_node.json`) or parsed dict
- `sample_limit`: int (default 500) — max text nodes to classify in one batch
- `llm_client`: optional handle to `runtime/engine/llm_engine.py`

### Returns
- `language_profile`: dict — {
  - `detected_primary_locale`: str
  - `locale_distribution`: dict[str, float]
  - `text_samples_by_locale`: dict[str, list[str]]
  - `confidence`: float (0–1)
  - `method`: enum (`llm`, `script`, `mixed`)
  - `warnings`: list[str]
}
- `next_phase_hint`: enum (`planning`, `execution`, `result`)

### Side effects
- May call LLM for classification
- Logs detection results to `audit_logger.md`
- No filesystem writes

## Decision Flow

1. **Collect text samples** — walk `figma_node_json` and extract non-empty `characters` fields from TEXT nodes. Deduplicate and truncate to `sample_limit` items.
2. **Fast script pass** — for each sample, apply unicode-script heuristics: Cyrillic → `ru`, CJK → `zh`/`ja`/`ko`, Arabic/Hebrew scripts → `ar`/`he`, Latin → `en`/`es`/`fr`/etc. via `langdetect` or fast regex.
3. **LLM refinement** — if samples remain ambiguous or mixed, send a bounded batch to `llm_client` with a prompt that returns ISO codes only. Limit to avoid token overflow.
4. **Aggregate distribution** — count samples per locale; normalize to percentages. Primary locale = largest share.
5. **Confidence scoring** — `llm` > `mixed` > `script`. Confidence scales with sample count and agreement ratio.
6. **Compare with requirements** — if `i18n_requirements_analyst.md` provided `target_locales`, verify primary locale is included; if not, emit warning and suggest adding it.
7. **Return profile** — include top samples per locale for downstream translation context.

## Failure Modes

| Condition | Response |
|---|---|
| No TEXT nodes in Figma export | Return empty profile, `confidence=0`, `method=script`, warning; downstream skips translation |
| LLM unavailable | Fall back to script detection; lower confidence |
| Mixed-script samples exceed threshold | Emit `mixed` method with distribution and warn operator to review locale list |
| Primary locale conflicts with `i18n_requirements` | Honor `i18n_requirements` but log mismatch to `audit_logger.md` |
| Sample limit exceeded | Randomly sample `sample_limit` items; note sampling in `warnings` |
