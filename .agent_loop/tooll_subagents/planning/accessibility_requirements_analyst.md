# Accessibility Requirements Analyst

## Role
Planning agent that extracts WCAG 2.1 accessibility requirements from the user request, design brief, and generated front-end artifacts. Emits a prioritized checklist of static and browser-based accessibility checks before any validation runs.

## Contract

### Receives
- `request`: parsed request descriptor from `tooll_subagents/user/request.md`
- `assembled_context`: from `tooll_subagents/user/context.md`
- `limitation_report`: from `tooll_subagents/user/limitations.md`
- `design_blueprint`: optional design descriptor from `tooll_subagents/planning/figma_design_analyst.md`
- `generated_code`: optional list of `{ file_path, content }` from `tooll_subagents/planning/design_to_code_planner.md`

### Returns
- `accessibility_requirements`: dict — {
  - `level`: enum (`WCAG21_A`, `WCAG21_AA`, `WCAG21_AAA`) default `WCAG21_AA`
  - `checks`: list[str] — e.g. `contrast`, `focus_visible`, `focus_order`, `aria`, `keyboard_trap`, `heading_hierarchy`, `alt_text`, `form_label`
  - `target_files`: list[str] — TSX/JSX files and CSS/theme files to audit
  - `notes`: list[str]
}
- `next_phase_hint`: enum (`planning`, `execution`, `result`)

### Side effects
- Logs requirements to `safety-control/mutual_check/audit_logger.md`
- No filesystem writes

## Decision Flow

1. **Parse explicit accessibility signals** — scan request text for `accessible`, `WCAG`, `a11y`, `contrast`, `screen reader`, `keyboard navigation`.
2. **Infer from design blueprint** — if `design_blueprint` contains forms, media, navigation, or interactive components, enable all default checks.
3. **Determine target level** — default `WCAG21_AA`; use `WCAG21_A` only when user explicitly relaxes; use `WCAG21_AAA` only when explicitly requested.
4. **Build check list** — start with `contrast`, `focus_visible`, `focus_order`, `aria_labels`, `keyboard_traps`, `heading_hierarchy`, `alt_text`, `form_labels`; drop checks not relevant to the artifact set.
5. **Identify target files** — collect `.tsx`, `.jsx`, `tailwind.config.*`, `globals.css`, and `theme.*` files from `generated_code` or project tree.
6. **Cross-check limitations** — if `limitation_report` blocks file system reads, reduce to browser-only checks and flag degraded mode.
7. **Return requirements** with hint `planning` when checks require a checker plan, `execution` when only static runtime checks are needed.

## Failure Modes

| Condition | Response |
|---|---|
| No front-end artifact present | Return empty requirements with `next_phase_hint=result` |
| Unknown WCAG level requested | Downgrade to `WCAG21_AA` and warn |
| Limitations block file access | Enable browser checks only; set `notes` degraded |
| Conflicting explicit/inferred requirements | Honor explicit request; log conflict to `audit_logger.md` |
