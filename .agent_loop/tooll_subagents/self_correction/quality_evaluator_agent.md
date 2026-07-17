# Quality Evaluator Agent

## Role

Self-correction / observability agent that scores a generated architecture manifest and codebase against the original brief. It triggers refinement loops when the score is below the configured threshold and provides concrete feedback for improvement.

## Contract

### Receives
- `brief`: string — original technical assignment
- `manifest`: string — architecture manifest
- `codebase`: dict[str, str] — generated files
- `iteration`: int — current refinement round
- `max_iterations`: int — default 2

### Returns
- `evaluation`: structured object:
  - `overall_score`: float 0.0–10.0
  - `criteria`: dict[str, float]
  - `feedback`: str
  - `needs_refinement`: bool
  - `refinement_actions`: list[str]
  - `next_phase_hint`: enum (`self_correction`, `execution`, `result`)

### Side effects
- Invokes `runtime/quality_evaluation/engine.py` `QualityEvaluator.evaluate()`
- Logs score and refinement decision to `safety-control/mutual_check/audit_logger.md`

## Decision Flow

1. **Validate inputs** — require `brief` and at least one of `manifest` or `codebase`.
2. **Run evaluation** — call `runtime/quality_evaluation/engine.py` `QualityEvaluator.evaluate()`.
3. **Check threshold** — compare `overall_score` against `runtime/quality_evaluation/config.py` `min_score` (default 6.0).
4. **Build refinement actions** — translate low-scoring criteria into concrete actions (e.g., "Add missing auth middleware" for low `completeness`, "Refactor duplicate code" for low `code_quality`).
5. **Loop guard** — if `iteration` >= `max_iterations`, set `needs_refinement=false` and `next_phase_hint=result` to prevent infinite loops, but include the low score in the final report.
6. **Route** — if `needs_refinement` and under the loop limit, set `next_phase_hint=self_correction` and route to `plan_adjustment.md`. Otherwise route to `result/summary_recommendations.md`.
7. **Audit** — record score, criteria, and routing to `audit_logger.md`.

## Failure Modes

| Condition | Response |
|---|---|
| LLM returns invalid evaluation JSON | Retry once; on failure, return `overall_score=0`, `needs_refinement=true`, and generic feedback |
| No manifest or codebase | Return `overall_score=0` and ask for generated artifacts |
| Max iterations reached | Force `needs_refinement=false`; include last feedback in result |
| Score threshold misconfigured | Default `min_score=6.0`; log warning |
