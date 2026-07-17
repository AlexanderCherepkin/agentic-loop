# Project Developer

## Role

Execution agent that materialises a starter codebase from an `architecture_manifest`. It invokes `runtime/web_project_agents/developer.py` to produce a dictionary of file paths and contents, then schedules writes via `tools_replace/replace_in_file/write_executor.md` inside the allowed workspace boundaries.

## Contract

### Receives
- `architecture_manifest`: from `tooll_subagents/planning/project_architect.md`
- `classification`: from `tooll_subagents/planning/project_classifier.md`
- `language`: string | None
- `template_context`: optional dict from `runtime/project_starter/template_manager.py`
- `target_dir`: string — workspace-relative directory for the generated project

### Returns
- `development_package`: structured object:
  - `files`: list[{ `path`, `content` }]
  - `commands`: list[str] — install and run commands
  - `readme`: str
  - `env_example`: str
  - `language`: str
  - `stack`: dict[str, str]
  - `success`: bool
  - `errors`: list[str]
  - `next_phase_hint`: enum (`execution`, `observability`, `result`)

### Side effects
- Writes files to `target_dir` via `tools_replace/replace_in_file/write_executor.md`
- Logs actions to `tooll_subagents/execution/action_logging.md` and `audit_logger.md`

## Decision Flow

1. **Validate inputs** — require `architecture_manifest` and `target_dir`. If `target_dir` is outside the allowed workspace, reject via `control/file_system_guard.md`.
2. **Merge with template context** — if `template_context` contains a preset skeleton, load files from `runtime/project_starter/template_manager.py` and mark them as fallback for any paths the LLM does not generate.
3. **Invoke runtime developer** — call `runtime/web_project_agents/developer.py` `ProjectDeveloper.develop()` with the manifest and language.
4. **Apply template fallback** — for each file in the preset skeleton, keep it if the generated codebase does not include that path; generated files override skeleton files.
5. **Validate file paths** — ensure all paths are relative and do not escape `target_dir`; block attempts to write to `.env`, `.ssh`, or absolute system paths via `file_system_guard.md`.
6. **Write files** — schedule writes via `tools_replace/replace_in_file/write_executor.md`; collect success/failure statuses.
7. **Generate README and env example** — if missing, create a minimal README and `.env.example` from the manifest.
8. **Route** — set `next_phase_hint=observability` so `code_review_validator.md`, `security_scan_validator.md`, and `quality_evaluator_agent.md` can validate the result.
9. **Audit** — record number of files written, language, stack, and any errors to `audit_logger.md`.

## Failure Modes

| Condition | Response |
|---|---|
| Empty manifest | Return `success=false`, errors=["architecture_manifest is empty"], route to `self_correction/plan_adjustment.md` |
| Target dir outside workspace | Block write and return `success=false`; escalate to `control/file_system_guard.md` |
| LLM returns invalid JSON | Retry once; if still invalid, return `raw_output` as a single `notes.txt` file and flag for review |
| Generated file attempts path traversal | Remove or reject the path; log to `audit_logger.md` |
| Write executor fails | Collect error, mark `success=partial`, route to `observability/runtime_output.md` and `self_correction/result_validation.md` |
| Template merge conflict | Prefer generated content; log override count to `audit_logger.md` |
