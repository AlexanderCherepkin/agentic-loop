---
session_id: 2026-07-25-multi-agent-profiles-moa
approval_token: approve-2026-07-25-multi-agent-profiles-moa
approved_at: 2026-07-25T14:00:00Z
scope_size: large
uncertainty_level: medium
interview_depth: full
needs_spec: true
needs_sub_agents: true
human_in_the_loop_required: true
automation_mode: augment
---

# Спецификация — Multi-Agent, Profiles и MOA

## Goal

Реализовать три локальные CLI/TUI‑механики для Agentic Loop:
1. **Fork‑субагенты** — фоновый рой помощников с панелью статусов.
2. **Profiles** — per‑profile модель + системный промпт (`SOUL.md`) через `ProfileResolver`.
3. **MOA (Mixture of Agents)** — консилиум из ≤5 советников + агрегатор уровня Opus.

Всё работает только внутри локального терминального процесса, не выставляется через MCP/веб.

## Scope — In

1. **Документация**
   - `memory/wiki/multi_agent_profiles_moa.md` — общая концепция.
   - `memory/wiki/fork_subagents.md` — `/fork`, `/agents`, панель статусов, policy.
   - `memory/wiki/profiles.md` — `ProfileResolver`, структура `~/.hermes/profiles/<id>/`.
   - `memory/wiki/moa.md` — формат, лимиты, dry‑run, обработка конфликтов.
   - Обновить `memory/wiki/project-agentic-loop-wiki.md` и `memory/wiki/index.md`.

2. **Fork‑субагенты**
   - `runtime/engine/fork_pool.py` — `ForkPool` с `asyncio.gather`.
   - `runtime/tui/fork_panel.py` — панель статусов воркеров для TUI.
   - Команды `/fork <задача>` и `/agents` внутри TUI.
   - Human approval gate перед стартом роя.
   - Жёсткий лимит параллельных воркеров `MAX_FORK_WORKERS=8`.

3. **Profiles**
   - `~/.hermes/profiles/<id>/config.yaml` — `model`, `provider`, `mode`, `guardrail_template`.
   - `~/.hermes/profiles/<id>/SOUL.md` — системный промпт в markdown.
   - `runtime/engine/profile_resolver.py` — `ProfileResolver` поверх `ModeManager`.
   - Интеграция в `LLMEngine.execute()` и `raw_chat_completion()` через параметр `profile_id`.

4. **MOA**
   - `runtime/engine/moa.py` — `MOAEngine`, `MOAConfig`, `AdvisorResult`, `MOAOutput`.
   - Агрегатор получает строго `list[AdvisorResult]` (JSON).
   - `max_advisors=5` по умолчанию.
   - `dry_run()` выводит план вызовов и оценку токенов без API‑запросов.
   - Обработка противоречивых и битых ответов советников.

5. **Тесты**
   - `tests/runtime/engine/test_fork_agents.py` — мок‑воркеры, лимиты, сборка результатов.
   - `tests/runtime/engine/test_profiles.py` — разбор профилей, fallback, интеграция с `LLMEngine`.
   - `tests/runtime/engine/test_moa.py` — конфликтные советники, битый JSON, fuzz.

## Scope — Out

- MCP/веб‑интерфейсы для этих механик.
- Постоянное хранение результатов fork вне сессии (snapshot в памяти + опциональный JSON‑дамп).
- Авто‑approve для `/fork`.
- Профили внутри git (`runtime/config/profiles/`).
- Автоматический выбор профиля по heuristics.

## Key Decisions

1. **Локальность**: CLI/TUI only, никаких внешних endpoint'ов.
2. **Fork**: `asyncio.gather` + human approval gate + `MAX_FORK_WORKERS=8`.
3. **Profiles**: `ProfileResolver` — декоратор над `ModeManager`, не ломает Model Economy.
4. **MOA**: structured JSON от советников, Opus‑агрегатор, `max_advisors=5`, обязательный `dry_run()`.
5. **Approval**: `/fork` требует явного `да/yes/ok` перед стартом.
6. **Storage**: `~/.hermes/profiles/` user‑specific, не git.

## Deliverables

1. Wiki‑документы из раздела «Документация».
2. `runtime/engine/fork_pool.py`.
3. `runtime/tui/fork_panel.py`.
4. `runtime/engine/profile_resolver.py`.
5. `runtime/engine/moa.py`.
6. Интеграция `profile_id` в `runtime/engine/llm_engine.py`.
7. Интеграция команд `/fork`, `/agents` в `runtime/tui.py`.
8. Тесты из раздела «Тесты».
9. Memory‑запись о завершении инкремента.

## Success Criteria

- `pytest tests/runtime/engine/test_fork_agents.py tests/runtime/engine/test_profiles.py tests/runtime/engine/test_moa.py -q --no-cov` passes.
- MOA fuzz ≥100 итераций с битым JSON/шумом не падает.
- `ProfileResolver` подменяет модель и системный промпт при `profile_id`, не ломая `ModeManager`.
- `/fork` без approval не запускает воркеров.
- Wiki lint clean.
- Core suite (`pytest -m core -q --no-cov`) без регрессий.

## Human Zones

- `git push` / deploy — отдельное explicit approval.
- Создание/изменение `~/.hermes/profiles/<id>/SOUL.md` — пользователь владеет файлом; агент читает, не пишет без approval.
- `/fork` — explicit approval gate перед каждым запуском.

## Assumptions

- `LLMEngine` уже интегрирован с Model Economy (`ModeManager`, `DriftDetector`).
- `pyyaml` доступен (добавлен в Model Economy).
- TUI уже существует (`runtime/tui.py`).
- Пользователь сам управляет содержимым `~/.hermes/profiles/`.

## Verification Plan

1. Юнит‑тесты на каждую подсистему.
2. Fuzz/property‑based тесты MOA.
3. Мок‑тесты fork с контролем concurrency и памяти.
4. Wiki lint после документации.
5. Full core suite run.
