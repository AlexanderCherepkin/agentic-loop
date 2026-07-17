# Code Review Validator

## Role

Self-correction agent that reviews a generated codebase against the original brief and architecture manifest. It identifies bugs, security issues, style violations, and mismatches, then returns either a list of refinement actions or a corrected codebase.

## Contract

### Receives
- `brief`: string — original technical assignment
- `manifest`: string — architecture manifest from `project_architect.md`
- `codebase`: dict[str, str] — generated files
- `mode`: enum (`review`, `review_and_fix`) — default `review`
- `project_rules`: dict | None

### Returns
- `review_result`: structured object:
  - `overall_score`: float 0.0–10.0
  - `summary`: str
  - `issues`: list[{ `file`, `severity`, `line`, `title`, `description`, `suggestion` }]
  - `suggestions`: list[str]
  - `corrected_codebase`: dict[str, str] | None
  - `patches`: list[{ `file`, `old`, `new` }] | None
  - `needs_fix`: bool
  - `next_phase_hint`: enum (`self_correction`, `execution`, `result`)

### Side effects
- Invokes `runtime/code_review/engine.py` `CodeReviewer`
- Logs review score and issue count to `safety-control/mutual_check/audit_logger.md`

## Decision Flow

1. **Validate inputs** — require non-empty `brief` and `codebase`. If `manifest` is missing, build a minimal manifest from the file list and brief.
2. **Filter reviewable files** — exclude binary files and paths matching `runtime/code_review/config.py` `excluded_paths`.
3. **Run review** — call `runtime/code_review/engine.py` `CodeReviewer.review()` with `brief`, `manifest`, and filtered `codebase`.
4. **Check threshold** — if `overall_score` >= 8.0 and no `critical`/`major` issues, set `needs_fix=false` and `next_phase_hint=result`.
5. **Attempt fix (conditional)** — if `mode=review_and_fix` or `overall_score` < 6.0, call `CodeReviewer.review_and_fix()` and populate `corrected_codebase` or `patches`. If only `patches` are returned, route to `diff_patch_applier.md` to apply them surgically.
6. **Apply patches** — delegate patch application to `diff_patch_applier.md` when `patches` are present; verify each patch with `runtime/code_review/diff_engine.py` before writing.
7. **Build refinement actions** — for each `major`/`critical` issue not covered by a patch, emit a `refinement_action` pointing to the relevant file.
8. **Route** — if fixes were applied, set `next_phase_hint=execution` to re-write files. Otherwise route to `recursion_or_termination.md` or `result/summary_recommendations.md`.
8. **Audit** — record score, issue count, and applied patches to `audit_logger.md`.

## Failure Modes

| Condition | Response |
|---|---|
| Empty codebase | Return `overall_score=0`, `needs_fix=false`, and route to `self_correction/assistance_request.md` |
| LLM returns invalid review JSON | Retry once; on failure, return heuristic review noting parse error |
| Patch application fails | Report `failed` count and keep original files; emit manual refinement actions |
| Review score < 3.0 | Trigger `assistance_request.md` for human review before rewriting |
| Safety concern in suggested fix | Route suggestion through `safety-control/output_reviewer.md` and `data_leak_preventer.md` |
