# i18n RTL Validator

## Role
Self-correction agent that verifies right-to-left locale support in generated components and layouts. Checks `dir` attribute, logical CSS properties, and safe-component wrappers so RTL users get correct layout.

## Contract

### Receives
- `i18n_requirements`: from `tooll_subagents/planning/i18n_requirements_analyst.md`
- `integration_report`: from `tooll_subagents/execution/i18n_runtime_integrator.md`
- `generated_files`: list[str] — paths to inspect

### Returns
- `rtl_report`: dict — {
  - `status`: enum (`passed`, `failed`, `needs_refinement`, `not_applicable`)
  - `rtl_locales`: list[str]
  - `issues`: list of { `file`, `line`, `severity`, `message` }
  - `refinement_actions`: list[str]
}
- `next_phase_hint`: enum (`self_correction`, `execution`, `result`)

### Side effects
- No writes; emits refinement actions for `plan_adjustment.md`

## Decision Flow

1. **Short-circuit if no RTL** — if `rtl_locales` is empty, return `not_applicable`.
2. **Check layout provider** — verify `app/[locale]/layout.tsx` sets `dir={isRtl ? 'rtl' : 'ltr'}` and `lang={locale}`.
3. **Check safe components** — verify `SafeLink`, `ResponsivePicture`, `TouchSafeElement` do not hardcode `left`/`right` margins/paddings in physical units.
4. **Scan for physical direction CSS** — search `*.tsx`, `*.css` for `margin-left`, `padding-right`, `text-align: left`, `float: left`, etc. Flag as issues.
5. **Check locale switcher** — ensure switcher flips order or uses logical layout for RTL.
6. **Recommend logical CSS** — for each flagged issue, emit `refinement_actions` to replace physical property with logical equivalent (`margin-inline-start`, `padding-inline-end`, etc.).
7. **Return report** with hint `execution` if issues found and budget remains, `result` if passed or not applicable.

## Failure Modes

| Condition | Response |
|---|---|
| Layout file missing | `failed`; action = re-run `i18n_runtime_integrator.md` |
| RTL locales present but `dir` not dynamic | `failed`; action = inject locale-based `dir` |
| Physical CSS found in safe components | `needs_refinement`; action = rewrite using logical properties |
| Validator cannot parse TSX | Skip file; note in issues |
