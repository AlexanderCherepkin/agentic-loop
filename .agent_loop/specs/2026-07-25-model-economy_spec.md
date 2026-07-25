---
session_id: 2026-07-25-model-economy
approval_token: approve-2026-07-25-model-economy
approved_at: 2026-07-25T12:45:00Z
scope_size: large
uncertainty_level: medium
interview_depth: full
needs_spec: true
needs_sub_agents: true
human_in_the_loop_required: true
automation_mode: augment
---

# Спецификация — Model Economy (Modes + Drift Detection + Auxiliary Slots)

## Goal

Внедрить контролируемую экономику моделей в Agentic Loop: именованные Modes, drift-detection настроек от сохранённого эталона, и auxiliary slot map для вспомогательных операций. Сначала документируем паттерн в вики, затем реализуем в `runtime/engine/llm_engine.py` и конфигах.

## Scope — In

1. **Документация**:
   - `memory/wiki/model_economy.md` — auxiliary slot map, mode semantics, drift-detection rules, Hermes config example.
   - `memory/wiki/howto-switch-mode.md` — операционный howto.
   - Update `project-agentic-loop.md` with model-economy baseline.

2. **Конфигурация**:
   - `runtime/config/model_economy.yaml` — project default modes and slots under git.
   - Read `~/.hermes/config.yaml` overrides if present.
   - `runtime/engine/model_economy_config.py` — dataclasses `Mode`, `AuxiliarySlots`, `ModelEconomyConfig`.

3. **Runtime**:
   - `runtime/engine/mode_manager.py` — `ModeManager`:
     - `load_modes()` from project + user config.
     - `set_mode(name)` — runtime switch.
     - `active_mode` property.
   - `runtime/engine/drift_detector.py` — `DriftDetector`:
     - compare current overrides vs active mode template,
     - compare current overrides vs last persisted snapshot,
     - return `DriftReport` with severity + audit event.
   - Integrate into `runtime/engine/llm_engine.py`:
     - `LLMEngine` uses auxiliary slots for title/vision/compression/approval/web_extract/code_review/summary.
     - Main calls still default to `claude-sonnet-5`.
     - Optional OpenRouter fallback provider (`openrouter/auto`, `openrouter/pareto-code`).
     - Drift check on every `raw_chat_completion` or explicit `check_drift()` call; flagged results returned, not raised, unless critical operation flag is set.

4. **Тесты**:
   - `tests/runtime/engine/test_model_economy_config.py`
   - `tests/runtime/engine/test_mode_manager.py`
   - `tests/runtime/engine/test_drift_detector.py` (property-based fuzz)
   - `tests/runtime/engine/test_llm_engine_model_economy.py` (mock routing)

## Scope — Out

- No UI or CLI for mode switching in this increment (only programmatic API).
- No billing/cost estimation logic beyond existing cost tracking.
- No automatic mode switching by heuristics — only explicit `set_mode()` or config default.
- No push/deploy of `~/.hermes/config.yaml`.

## Key Decisions

1. Modes are runtime-switchable; guardrail template loaded from `~/.hermes/config.yaml` + `runtime/config/model_economy.yaml`.
2. Drift detection checks two deltas: (active mode template vs current overrides) and (persisted snapshot vs current overrides).
3. Drift triggers flagged result + audit log; hard block only when `critical=True`.
4. Auxiliary slots: `title`, `vision`, `compression`, `approval`, `web_extract`, `code_review`, `summary`.
5. Main model remains `claude-sonnet-5`; OpenRouter routers are optional fallback providers.
6. Project defaults live under git; user overrides stay in `~/.hermes/config.yaml`.

## Deliverables

1. `memory/wiki/model_economy.md`
2. `memory/wiki/howto-switch-mode.md`
3. Updated `memory/wiki/project-agentic-loop.md`
4. `runtime/config/model_economy.yaml`
5. `runtime/engine/model_economy_config.py`
6. `runtime/engine/mode_manager.py`
7. `runtime/engine/drift_detector.py`
8. Updated `runtime/engine/llm_engine.py`
9. Test modules listed above.
10. Memory note about model-economy integration.

## Success Criteria

- `pytest tests/runtime/engine/test_*model_economy* -q` passes.
- Drift detector returns correct verdicts for known-good, drifted-template, and drifted-snapshot cases.
- Property-based fuzz runs ≥100 random override mutations without false negatives.
- `LLMEngine` routes auxiliary slots to configured models while main path stays on Claude.
- Wiki lint clean; no broken links.

## Human Zones

- `git push` / deploy — separate explicit approval.
- Editing `~/.hermes/config.yaml` user-specific modes — user owns the file; agent reads, does not write without approval.
- Critical-operation hard block on drift — requires explicit user reset.

## Assumptions

- `~/.hermes/config.yaml` exists or is optional; project defaults suffice.
- OpenRouter integration uses existing API key infrastructure (`OPENROUTER_API_KEY` env).
- `claude-sonnet-5` remains the default main model and is not replaced.
- Property-based tests use `hypothesis` if available, otherwise handcrafted fuzz.

## Verification Plan

1. Unit tests for config parsing and mode resolution.
2. Adversarial drift-detection fuzz tests.
3. Mock routing tests for auxiliary slots and OpenRouter fallback.
4. Wiki lint check after documentation updates.
5. Full core suite run to confirm no regressions.
