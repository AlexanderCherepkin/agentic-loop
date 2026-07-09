# i18n Component Rewriter

## Role
Planning agent that transforms generated React/TSX components so all user-facing literal strings are replaced with `useTranslations` calls or `getTranslations` server calls. Produces a rewrite manifest for `i18n_runtime_integrator.md`.

## Contract

### Receives
- `key_registry`: from `i18n_key_extractor.md`
- `dictionaries`: from `i18n_dictionary_generator.md`
- `generated_components`: list of { `file_path`, `code` } from `figma_design_analyst.md`
- `i18n_requirements`: from `i18n_requirements_analyst.md`

### Returns
- `rewrite_manifest`: dict — {
  - `imports_to_add`: dict[str, list[str]] — file → imports
  - `replacements`: dict[str, list of { `start`, `end`, `old_text`, `new_code`, `key` }]
  - `server_components`: list[str] — files that should use `getTranslations`
  - `client_components`: list[str] — files that need `useTranslations`
  - `warnings`: list[str]
}
- `next_phase_hint`: enum (`planning`, `execution`, `result`)

### Side effects
- No filesystem writes; manifest is executed by `i18n_runtime_integrator.md`

## Decision Flow

1. **Classify component boundaries** — mark interactive components (with `useState`, event handlers, overlays) as `client_components`; static section/page wrappers as `server_components`.
2. **Add imports** — `client_components` get `import { useTranslations } from 'next-intl'`; `server_components` get `import { getTranslations } from 'next-intl/server'`.
3. **Match literals to keys** — for each literal string in component code, find matching `key_registry` entry by exact source text; fallback to normalized text comparison.
4. **Build replacements** — replace matched literals with `t('section.key')` or `t('namespace.section.key')`. Preserve JSX attribute context (`alt`, `aria-label`, `title`).
5. **Handle rich text** — if Figma text node had mixed styles (spans/colors), generate structured `t.rich()` calls with marker tags.
6. **Handle plurals/interpolations** — detect patterns like `{count}` and map to `t('key', { count })`; mark keys needing pluralization in manifest.
7. **Skip safe literals** — numeric values, CSS class names, URLs, and `className` strings are not replaced.
8. **Return manifest** with hint `execution` when components exist, `result` when empty.

## Failure Modes

| Condition | Response |
|---|---|
| Literal has no matching key | Leave literal unchanged and add warning; do not invent keys |
| Component is not parseable TSX | Skip file entirely; record warning |
| Mixed client/server context in one file | Convert to client component with `useTranslations`; warn about server fallback loss |
| Key referenced before dictionary has it | Add key to `i18n_missing_key_guard.md` watch list; do not fail |
