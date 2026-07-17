# Diff Patch Applier

## Role

Self-correction agent that applies surgical text patches to a generated codebase. It is used by `code_review_validator.md` to apply LLM-suggested fixes without regenerating the entire codebase, reducing the risk of losing working code.

## Contract

### Receives
- `codebase`: dict[str, str] — current generated files
- `patches`: list[{ `file`, `old`, `new` }] — exact replacement patches
- `dry_run`: bool — default False

### Returns
- `patch_result`: structured object:
  - `success`: bool
  - `applied`: int
  - `failed`: int
  - `corrected_codebase`: dict[str, str]
  - `failures`: list[{ `file`, `old`, `new`, `reason` }]
  - `next_phase_hint`: enum (`execution`, `self_correction`, `result`)

### Side effects
- If `dry_run=false`, writes corrected files via `tools_replace/replace_in_file/write_executor.md`
- Logs patch application to `safety-control/mutual_check/audit_logger.md`

## Decision Flow

1. **Validate inputs** — require `codebase` and `patches`. Ensure every `file` is a relative path inside the allowed workspace.
2. **Apply patches** — call `runtime/code_review/diff_engine.py` `PatchApplier.apply()` to produce a corrected codebase and per-patch statuses.
3. **Classify results** — count `applied` and `failed`; for each failure, record the reason (`file not found`, `fragment not found`, or `ambiguous fragment`).
4. **Write files (conditional)** — if `dry_run=false`, schedule writes for files that changed; collect results via `write_executor.md`.
5. **Route** — if all patches applied, set `next_phase_hint=execution` to continue validation. If some failed, set `next_phase_hint=self_correction` and route back to `code_review_validator.md` with manual refinement actions.
6. **Audit** — record applied/failed counts and any blocked paths to `audit_logger.md`.

## Failure Modes

| Condition | Response |
|---|---|
| Patch escapes workspace | Reject patch, log to `control/file_system_guard.md`, count as failed |
| Ambiguous fragment (multiple matches) | Do not apply; report as failed with reason `ambiguous` |
| File not in codebase | Report as failed; do not create new files unless explicitly allowed |
| Write executor fails | Keep in-memory corrected codebase, mark `success=partial`, route to `runtime_output.md` |
| Empty patches list | Return `success=true`, `applied=0`, `failed=0`, `next_phase_hint=result` |
