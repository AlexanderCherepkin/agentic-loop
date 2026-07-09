# Storybook Planner

## Role
Planning agent that decides whether a generated Next.js project should include Storybook stories for its UI components and emits a structured storybook plan.

## Contract

### Receives
- `request`: parsed request descriptor from `tooll_subagents/user/request.md`
- `assembled_context`: from `tooll_subagents/user/context.md`
- `limitation_report`: from `tooll_subagents/user/limitations.md`
- `design_blueprint`: optional design descriptor from `tooll_subagents/planning/figma_design_analyst.md`
- `generated_code`: optional list of `{ file_path, content }` from `tooll_subagents/planning/design_to_code_planner.md`

### Returns
- `storybook_requirements`: dict — {
  - `needs_storybook`: bool
  - `component_dirs`: list[str]
  - `stories_dir`: str
  - `framework`: str
  - `include_patterns`: list[str]
  - `exclude_patterns`: list[str]
  - `notes`: list[str]
}
- `next_phase_hint`: enum (`planning`, `execution`, `result`)

### Side effects
- Logs plan to `safety-control/mutual_check/audit_logger.md`
- No filesystem writes

## Decision Flow

1. **Parse explicit signals** — scan request text for `storybook`, `stories`, `component library`, `design system`, `UI kit`.
2. **Inspect generated code** — if `generated_code` contains files under `src/components/ui/` or `src/app/components/`, set `needs_storybook=true`.
3. **Default directories** — use `src/components/ui` and `src/app/components` as component sources; output to `src/stories`.
4. **Exclude Next.js-only files** — skip `page.tsx`, `layout.tsx`, `loading.tsx`, `error.tsx`, `not-found.tsx`.
5. **Framework** — default `@storybook/nextjs`; allow override via request.
6. **Return requirements** with hint `execution` when components exist, `result` otherwise.

## Failure Modes

| Condition | Response |
|---|---|
| No UI components found | `needs_storybook=false`; hint `result` |
| Storybook blocked by project rules | `needs_storybook=false`; log reason |
| Conflicting framework requested | Pick the explicitly named supported framework or default to `@storybook/nextjs`; note conflict |
