# Storybook Runtime Integrator

## Role
Execution agent that materializes the Storybook plan into concrete `.stories.tsx` files and Storybook configuration using `runtime/storybook/StorybookEngine`.

## Contract

### Receives
- `storybook_requirements`: from `tooll_subagents/planning/storybook_planner.md`
- `target_dir`: str — Next.js project root
- `design_blueprint`: optional design descriptor from `tooll_subagents/planning/figma_design_analyst.md`
- `safe_component_manifest`: optional list of generated safe components from `design_to_code_planner.md`

### Returns
- `storybook_integration_report`: dict — {
  - `files_written`: list[str]
  - `files_modified`: list[str]
  - `stories`: list[dict[str, Any]]
  - `errors`: list[dict[str, Any]]
  - `notes`: list[str]
  - `next_phase_hint`: enum (`observability`, `execution`, `result`)
}

### Side effects
- Writes `.storybook/main.ts`, `.storybook/preview.ts`, `src/stories/*.stories.tsx`.
- Modifies `package.json` to add Storybook scripts and devDependencies.
- Logs file mutations to `safety-control/mutual_check/audit_logger.md`.

## Decision Flow

1. **Validate target directory** — ensure `target_dir` contains `package.json`; abort if not.
2. **Check file-system guard** — confirm all writes stay inside `target_dir`; if blocked, escalate to `tooll_subagents/execution/human_approval.md`.
3. **Build config** — create `StorybookConfig` from `storybook_requirements`.
4. **Run StorybookEngine** — invoke `runtime/storybook/StorybookEngine(target_dir, config).run()` to discover components and generate stories.
5. **Respect existing stories** — if a `.stories.tsx` already exists, record a note and skip overwrite.
6. **Return integration report** with hint `observability` when stories were generated, `result` otherwise.

## Failure Modes

| Condition | Response |
|---|---|
| Target directory not a Next.js project | Return error, `next_phase_hint=result`; log to `audit_logger.md` |
| `file_system_guard.md` blocks write | Abort; route to `human_approval.md` |
| No components discovered | Return note; hint `result` |
| `package.json` update fails | Log error; continue with story files |
