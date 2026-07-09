# План: Feedback loop & regression guard (audit row #30)

## Контекст
- Реализуем строку аудита #30: **Feedback loop & regression guard** — после правок бот сравнивает новый скриншот/состояние с предыдущим и сообщает, что сломалось.
- Выбор пользователя: **комбинированный** guard (screenshot + DOM/layout + Lighthouse + console) + **на этапе самокоррекции**.
- Опираемся на уже существующие агенты: `visual_qa_agent.md`, `screenshot_agent.md`, `file_context.md`, `result_validation.md`, `recursion_or_termination.md`.

## Архитектурные решения
1. Новый агент самокоррекции `regression_guard.md` — единственное добавление агента.
2. Агент работает как валидатор в `self_correction`-слое; он сравнивает текущие артефакты с артефактами предыдущей итерации.
3. `PipelineRunner` будет передавать `previous_validation` в обзор валидаторов, чтобы `regression_guard.md` мог брать baseline.
4. `result_validation.md` получит новый вердикт «Regression guard» и на его основе формирует `needs_refinement` / refinement actions.
5. Никаких новых флагов планирования не требуется — guard срабатывает автоматически, когда в observation/validation есть скриншот/Lighthouse/файловые отчёты.

## Изменения

### 1. Новый агент
**Файл:** `.agent_loop/tooll_subagents/self_correction/regression_guard.md`
- Algorithmic template: Role, Contract (Receives/Returns/Side effects), Decision Flow, Failure Modes.
- Receives:
  - `current_artifacts` (или observation) — `visual_qa_report`, `lighthouse_audit_report`, `file_context`, `console_errors`;
  - `previous_artifacts` — те же отчёты с предыдущей итерации;
  - `iteration_count`.
- Returns `regression_report`:
  - `status`: `passed` / `regressed` / `warn` / `inconclusive` / `blocked`;
  - `screenshot_delta`: `diff_score_delta`, `baseline_path`, `current_path`;
  - `layout_delta`: `new_overflows`, `new_overlaps`, `new_clipped_text`, `bbox_regressions`;
  - `console_delta`: `new_errors`, `new_warnings`;
  - `lighthouse_delta`: `score_changes` по категориям;
  - `file_delta`: `files_added`, `files_removed`, `files_modified`;
  - `regressions`: список `{severity, message, evidence}`;
  - `verdict`: `pass` / `warn` / `fail`;
  - `refinement_actions`: список действий, если есть регрессии.

### 2. Обновление `result_validation.md`
**Файл:** `.agent_loop/tooll_subagents/self_correction/result_validation.md`
- В Contract → Receives добавить `regression_report`.
- В Decision Flow добавить шаг **12g. Regression guard verdict**:
  - `passed`/`not_applicable` → взнос к `complete`;
  - `regressed`/`warn` → `validation_status=needs_refinement`, добавить `refinement_actions`;
  - `blocked`/`inconclusive` → `needs_refinement` при оставшемся бюджете, иначе `needs_human`.
- Добавить Failure Modes для regression guard.

### 3. Обновление `PipelineRunner`
**Файл:** `runtime/engine/pipeline_runner.py`
- В `_run_self_correction_review` дополнить `review` перед вызовом валидаторов:
  - `review["previous_validation"] = state.get("validation", {})`
  - `review["iteration_count"] = state.get("iteration", 0)`
- Это позволит `regression_guard.md` сравнивать текущее состояние с baseline без изменения общего state-структуры.

### 4. Mock-ответ LLM
**Файл:** `runtime/engine/llm_engine.py`
- Добавить `_RESPONSES["self_correction/regression_guard.md"]` с базовым `regression_report` (status=passed, пустые deltas, verdict=pass).
- Для тестов с регрессией отдельный тест может переопределить `llm.execute`, чтобы вернуть статус `regressed`.

### 5. Runtime invocation map + счётчики
- Запустить `python .agent_loop/scripts/generate_agent_invocation_map.py` — новый агент автоматически попадёт в `self_correction`-фазу.
- **`.agent_loop/scripts/validate_runtime_coverage.py`**: `EXPECTED_AGENT_COUNT` 255 → 256.
- **`.agent_loop/scripts/health_check.py`**: `EXPECTED_AGENTS` 255 → 256.

### 6. Документация архитектуры
**Файлы:** `.agent_loop/ARCHITECTURE.md`, `.agent_loop/TECHNICAL_ASSIGNMENT.md`
- `self_correction`: 14 → 15 агентов.
- `tooll_subagents`: 99 → 100 агентов.
- Total: 255 → 256.
- В разделе data flow / self_correction упомянуть `regression_guard.md` рядом с валидаторами.
- `TECHNICAL_ASSIGNMENT.md`: масштаб 256, статус 256/256.

### 7. Тесты
**Файл:** `tests/runtime/test_pipeline_figma.py`
- `test_regression_guard_agent_in_validation_core()` — проверить, что путь агента есть в `runner.VALIDATION_CORE`.
- `test_regression_guard_produces_report_when_previous_validation_exists()` — вызвать `_run_self_correction_review` с state, содержащим observation (visual_qa_report) и previous_validation, и убедиться, что в review появился `regression_report`.
- `test_regression_guard_passes_previous_validation_to_review()` — проверить, что `review["previous_validation"]` передан.

## Верификация
1. `python .agent_loop/scripts/generate_agent_invocation_map.py` — 0 unreachable.
2. `python .agent_loop/scripts/validate_runtime_coverage.py` — OK.
3. `node .agent_loop/scripts/validate_cross_references.js` — clean.
4. `node .agent_loop/scripts/validate_consistency.js` — 0 warnings.
5. `python .agent_loop/scripts/health_check.py` — HEALTHY.
6. `pytest -m core` — проходит.
7. `graphify update .` — AST-only.
8. Git: commit + push в ветку `finish-increment-check` (Gate 2 уже одобрен ранее).
