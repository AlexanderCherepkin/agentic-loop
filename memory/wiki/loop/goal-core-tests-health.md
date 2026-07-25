# Loop Workflow: goal-core-tests-health

**Goal:** all core tests pass and health check stays green

## Preset

- ID: `goal-core-tests-health`
- Trust level: L1
- Max iterations: 1
- Schedule: on-demand

## Steps

- **health_check**: run `.agent_loop/scripts/health_check.py --json` and parse `healthy` field.
- **core_tests**: run `python -m pytest -m core -q --no-cov` and confirm 0 failures.
- **loop_engine_tests**: run `python -m pytest tests/runtime/test_loop_engine.py tests/runtime/test_loop_trust_levels.py tests/runtime/test_loop_presets.py -q --no-cov` and confirm all pass.
- **verify**: route evidence through `runtime/loop_engine/loop_verifier.py` with ≥2 adversarial critics.

## Exit conditions

- `healthy=true` in health check JSON.
- Core pytest reports 0 failures.
- Verifier consensus ≥2 critics approve.

## Verification

- Executor: `claude-haiku-4-5`
- Verifier: `claude-opus-4-8`
- Critics: 2

## Human zones

- None for this read-only verification goal.
