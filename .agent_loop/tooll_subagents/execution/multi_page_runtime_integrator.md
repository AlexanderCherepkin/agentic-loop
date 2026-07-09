# Multi-page Runtime Integrator

## Role
Execution agent that materializes the multi-page routing plan into concrete Next.js App Router files using `runtime/multi_page/MultiPageEngine`. Generates page routes, shared Navigation component, sitemap, and robots handlers.

## Contract

### Receives
- `multi_page_requirements`: from `tooll_subagents/planning/multi_page_planner.md`
- `target_dir`: str — Next.js project root
- `design_blueprint`: optional design descriptor from `tooll_subagents/planning/figma_design_analyst.md`
- `safe_component_manifest`: optional list of generated safe components from `design_to_code_planner.md`

### Returns
- `multi_page_integration_report`: dict — {
  - `files_written`: list[str]
  - `files_modified`: list[str]
  - `pages`: list[dict[str, Any]]
  - `errors`: list[dict[str, Any]]
  - `notes`: list[str]
  - `next_phase_hint`: enum (`observability`, `execution`, `result`)
}

### Side effects
- Writes `app/[slug]/page.tsx`, `app/page.tsx`, `app/components/Navigation.tsx`, `app/sitemap.ts`, `app/robots.ts`.
- Reads generated page code from `multi_page_requirements.pages`.
- Logs file mutations to `safety-control/mutual_check/audit_logger.md`.

## Decision Flow

1. **Validate target directory** — ensure `target_dir` contains `package.json` or `next.config.*`; abort if not.
2. **Check file-system guard** — confirm all writes stay inside `target_dir`; if blocked, escalate to `tooll_subagents/execution/human_approval.md`.
3. **Build config** — create `MultiPageConfig` from `multi_page_requirements`.
4. **Run MultiPageEngine** — invoke `runtime/multi_page/MultiPageEngine(target_dir, config).run()` to write routes and routing artifacts.
5. **Respect existing files** — if `app/sitemap.ts` or `app/robots.ts` already exist, record a note and skip overwrite.
6. **Return integration report** with hint `observability` when navigation/sitemap/robots were generated, `result` otherwise.

## Failure Modes

| Condition | Response |
|---|---|
| Target directory not a Next.js project | Return error, `next_phase_hint=result`; log to `audit_logger.md` |
| `file_system_guard.md` blocks write | Abort; route to `human_approval.md` |
| Missing page code in requirements | Skip that page; record error; continue with others |
| Sitemap/robots already exist | Skip overwrite; note in report; continue |
