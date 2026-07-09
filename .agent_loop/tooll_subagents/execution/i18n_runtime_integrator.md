# i18n Runtime Integrator

## Role
Execution agent that materializes the i18n plan into concrete Next.js project files. Generates `next-intl` configuration, locale dictionaries, middleware, layout providers, and applies the component rewrite manifest.

## Contract

### Receives
- `routing_plan`: from `tooll_subagents/planning/i18n_routing_planner.md`
- `dictionaries`: from `tooll_subagents/planning/i18n_dictionary_generator.md`
- `rewrite_manifest`: from `tooll_subagents/planning/i18n_component_rewriter.md`
- `optimization_plan`: from `tooll_subagents/planning/i18n_optimizer.md`
- `i18n_requirements`: from `tooll_subagents/planning/i18n_requirements_analyst.md`
- `target_dir`: str — Next.js project root

### Returns
- `integration_report`: dict — {
  - `files_written`: list[str]
  - `files_modified`: list[str]
  - `locales_installed`: list[str]
  - `errors`: list of { `file`, `reason` }
  - `next_phase_hint`: enum (`observability`, `execution`, `result`)
}

### Side effects
- Writes `middleware.ts`, `i18n/config.ts`, `i18n/routing.ts`, `i18n/request.ts`, `messages/*.json`, `app/[locale]/layout.tsx`, modified `app/page.tsx`, and rewrites component files.
- Logs file mutations to `audit_logger.md`

## Decision Flow

1. **Validate target directory** — ensure `target_dir` exists and contains `package.json`; if not, report error and abort.
2. **Install dependency** — ensure `next-intl` is in `package.json` dependencies; add with version pin if missing.
3. **Write config files** — create `i18n/config.ts` with locales/default; create `i18n/routing.ts` with `defineRouting`; create `i18n/request.ts` with `getRequestConfig`.
4. **Write middleware** — create `middleware.ts` exporting ` NextResponse` redirect/rewrite and matcher.
5. **Write dictionaries** — serialize each locale dictionary to `messages/{locale}.json` with stable key ordering.
6. **Create locale layout** — create `app/[locale]/layout.tsx` that wraps children with `NextIntlClientProvider` and sets `lang` attribute.
7. **Rewrite root page** — move or redirect root `app/page.tsx` to `app/[locale]/page.tsx`.
8. **Apply component rewrites** — use `tools_replace/replace_in_file/write_executor.md` to apply `rewrite_manifest` replacements and add imports.
9. **Handle RTL** — for RTL locales, inject `dir="rtl"` logic into layout and add logical CSS note.
10. **Validate file system guard** — confirm all writes stay inside `target_dir`; if `control/file_system_guard.md` blocks, abort and escalate to `tooll_subagents/execution/human_approval.md`.
11. **Return integration report**.

## Failure Modes

| Condition | Response |
|---|---|
| Target directory not a Next.js project | Return error and `next_phase_hint=result`; log to `audit_logger.md` |
| `file_system_guard.md` blocks write | Abort; route to `human_approval.md` for explicit scope grant |
| Component rewrite manifest invalid | Skip rewrites, emit error, continue with config/dictionaries |
| Dictionary serialization fails | Emit per-locale error; continue for remaining locales |
| Middleware conflicts with existing `middleware.ts` | Merge matchers conservatively; if conflict remains, route to `human_approval.md` |
| `safety_guardrails.md` blocks execution mid-run | Abort immediately; preserve trace; route to `safety-control/safety_assessor.md` |
