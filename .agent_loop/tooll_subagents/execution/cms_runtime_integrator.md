# CMS Runtime Integrator

## Role
Execution agent that materializes CMS/data-query plans into concrete Next.js App Router files using `runtime/cms_queries/CmsQueriesEngine`. Generates provider-agnostic typed wrappers, a working local-markdown loader, static fallback, listing/detail pages, and card components.

## Contract

### Receives
- `cms_source_config`: from `tooll_subagents/planning/cms_source_selector.md`
- `target_dir`: str — Next.js project root
- `design_blueprint`: optional design descriptor from `tooll_subagents/planning/figma_design_analyst.md`
- `cms_requirements`: optional from `tooll_subagents/planning/cms_requirements_analyst.md`

### Returns
- `integration_report`: dict — {
  - `files_written`: list[str]
  - `files_modified`: list[str]
  - `sources_installed`: list[str]
  - `errors`: list of { `file`, `reason` }
  - `notes`: list[str]
  - `next_phase_hint`: enum (`observability`, `execution`, `result`)
}

### Side effects
- Writes `src/lib/cms.ts`, `src/lib/cms/localMarkdown.ts`, `src/lib/cms/staticFallback.ts`, `src/components/cms/PostCard.tsx`, `src/components/cms/ProjectCard.tsx`, `src/components/cms/CaseStudyCard.tsx`, listing pages under `src/app/{blog,portfolio,cases}/page.tsx`, detail pages under `src/app/{blog,portfolio,cases}/[slug]/page.tsx`, and `.env.local.example` with source-specific placeholders.
- Injects the correct npm dependency into `package.json` when the source needs an SDK.
- Logs file mutations to `safety-control/mutual_check/audit_logger.md`

## Decision Flow

1. **Validate target directory** — ensure `target_dir` is a Next.js project; abort if `package.json` is missing.
2. **Check file-system guard** — confirm all writes stay inside `target_dir`; if `control/file_system_guard.md` blocks, escalate to `tooll_subagents/execution/human_approval.md`.
3. **Load source configuration** — instantiate `runtime/cms_queries/config.CmsSource` from `cms_source_config` and call `validate()`.
4. **Run CMS engine** — invoke `runtime/cms_queries/engine.CmsQueriesEngine.run()` to write the data layer, card components, listing/detail pages, env example, and package dependency.
5. **Guard secrets** — before writing, route any connection placeholders through `safety-control/data_leak_preventer.md`; abort on real secret leak.
6. **Respect existing files** — if `src/lib/cms.ts` already exists, record a note and do not overwrite it.
7. **Apply Ponytail review hint** — if code generation is involved, ensure `tooll_subagents/planning/ponytail_injector.md` was applied upstream; after writing, surface the output for `tooll_subagents/self_correction/ponytail_review.md` if requested.
8. **Return integration report** with hint `observability` for audit/validation.

## Failure Modes

| Condition | Response |
|---|---|
| Target directory not a Next.js project | Return error, `next_phase_hint=result`; log to `audit_logger.md` |
| `file_system_guard.md` blocks write | Abort; route to `human_approval.md` for explicit scope grant |
| `data_leak_preventer.md` flags real secrets | Abort; route to `safety-control/safety_assessor.md` |
| Invalid source configuration | Return validation errors; do not write |
| `src/lib/cms.ts` already exists | Skip overwrite; note in report; continue with other files |
| SDK dependency injection fails | Log error but continue with provider-agnostic stubs |
