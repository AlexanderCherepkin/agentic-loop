# Plan: Автоматизация learn-from-source + graphify

## Контекст

Пользователь хочет автоматизировать два навыка внутри Agentic Loop:
1. **learn-from-source** — срабатывать при появлении новых markdown-источников в проекте.
2. **graphify** — обновлять граф после значимых изменений (≥N файлов или новые агенты).
3. **Подсказки** — анализировать чат и объяснять, стоит ли делать навык из источника/опыта.

## Ключевое ограничение

Полностью автоматическое создание SKILL.md без одобрения пользователя **невозможно** — это нарушает гарды существующего `learn-from-source` (Гард 2: никогда не перезаписывать без явного «да»). Поэтому автоматизация = **автообнаружение + автоанализ + предложение**, а запись навыка — только после явного одобрения.

## Подход

Гибрид: **git hook** для graphify (shell, 0 токенов) + **PipelineRunner агенты** для learn-from-source suggestions + **runtime engine** для сканирования.

## Фазы реализации

### Phase 1 — Runtime engine

Создать `runtime/skill_automation/`:
- `config.py` — `SkillAutomationConfig` с порогами:
  - `graphify_min_changed_files` (default: 10)
  - `graphify_new_agent_detected` (default: true)
  - `source_min_words` (default: 200)
  - `source_max_files_per_scan` (default: 5)
- `engine.py` — `SkillAutomationEngine`:
  - `detect_new_sources()` — находит `.md`-файлы, не отслеживаемые в `graphify-out/manifest.json` или `data/memory.db`.
  - `assess_source_value()` — оценивает, содержит ли файл повторяемый процесс.
  - `detect_graphify_need()` — сверяет изменения с порогами.
  - `propose_actions()` — возвращает JSON-список предложений.
- `__init__.py` — публичные экспорты.

### Phase 2 — Агенты

Создать в `.agent_loop/tooll_subagents/` по Algorithmic template:
- `observability/source_detector.md` — получает `file_changes` от `file_context.md`, ищет новые `.md`, эмитит `source_candidates`.
- `planning/skill_value_analyst.md` — получает `source_candidate`, объясняет ценность (`worth_making_skill`, `reason`, `estimated_reuse`).
- `observability/graphify_auto_updater.md` — получает `file_changes`, решает `needs_update`, формирует команду `graphify . --update`.
- `result/skill_proposal_presenter.md` — форматирует предложения для пользователя; не пишет файлы.

### Phase 3 — CLI-сканер

Создать `.agent_loop/scripts/skill_automation_scan.py`:
- Подкоманды: `scan`, `graphify-update`, `propose-skills`.
- Режим `--post-commit` — только graphify + запись предложений.
- Записывает результаты в `data/skill_automation.jsonl` и `memory` (через `MemoryManager`).
- Не использует Claude API, работает локально.

### Phase 4 — Git hook

- Добавить `.git/hooks/post-commit` (или расширить существующий `post-commit`/`post-merge`) вызовом `python .agent_loop/scripts/skill_automation_scan.py --post-commit`.
- Hook запускает `graphify . --update` при превышении порога, а предложения по навыкам сохраняет в `data/skill_automation.jsonl` и memory для показа в следующей сессии.

### Phase 5 — Интеграция в PipelineRunner

- Добавить `source_detector.md` в `observability` phase (conditional: если есть `file_changes` с новыми `.md`).
- Добавить `skill_value_analyst.md` в `result` phase для объяснения ценности найденных источников.
- Обновить `.agent_loop/scripts/generate_agent_invocation_map.py` для классификации новых агентов.
- Перегенерировать `runtime/engine/agent_invocation_map.py`.

### Phase 6 — Тесты

- `tests/runtime/test_skill_automation_engine.py` — unit-тесты детектора и value-оценки.
- `tests/test_agent_specs/test_skill_automation_agents.py` — проверка Algorithmic template у новых агентов.
- Обновить `.agent_loop/scripts/health_check.py` чтобы он видел новые модули.

### Phase 7 — Документация

- `runtime/skill_automation/README.md` — как работает автоматизация и как отключить.
- Обновить `MEMORY.md` — memory note о новой автоматизации.
- **Не обновлять** `CLAUDE.md` и `project_rules.md` без явного указания пользователя (human approval gate).

## Гарды, встроенные в план

1. **Навык не создаётся без одобрения** — автоматизатор только предлагает; `skill_packager.md`/`learn-from-source` сохраняют право вето.
2. **Graphify guard** — обновление запускается только при ≥10 изменённых файлов или новых агентах; при >500 файлов — предупреждение вместо автоапдейта.
3. **Токен-гард** — `skill_value_analyst.md` срабатывает только если источник >200 слов; чат анализируется только при ≥2 итерациях или наличии `corrections_applied`.
4. **Safety-first** — новые агенты проходят через `safety-control` и `mutual_check` как часть PipelineRunner.
5. **Memory audit** — все предложения логируются в `audit_logger.md` и `data/skill_automation.jsonl`.

## Риски

- Git hook работает вне Claude Code и не может напрямую вызвать Claude API; поэтому learn-from-source предложения накапливаются, а не мгновенно обрабатываются.
- Автоанализ чата тратит токены; гарды выше ограничивают частоту.
- Если пользователь не использует git hooks, автоматизация graphify не сработает — для этого есть ручной `scan`.
