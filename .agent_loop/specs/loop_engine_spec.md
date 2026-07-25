# SPEC — Loop Engine: Self-Improving Loops в Agentic Loop

## Status

Draft — pending approval.

## Goal

Добавить в Agentic Loop runtime-инфраструктуру для `/goal`, `/loop` и `/workflows` так, чтобы повторяющиеся задачи можно было запускать по единому шаблону, верифицировать двухмодельной схемой (cheap executor + expensive verifier), накапливать CONSTRAINTS.md и материализовать успешные workflow как `.claude/skills/`. Первый use case — усиление anti-slop: регулярный аудит кода на banned-паттерны с автоматическим пополнением правил.

## Scope

### Входит

1. **Loop presets** — `runtime/loop_presets/` с тремя YAML-шаблонами:
   - `ci_sweeper.yaml` — чинит flaky CI-падения, перезапускает прогоны, эскалирует настоящие баги.
   - `pr_babysitter.yaml` — следит за PR, пишет summary, отмечает что требует внимания.
   - `dependency_sweeper.yaml` — проверяет зависимости на CVE/устаревание, предлагает обновления.
   - `anti_slop_sweeper.yaml` — первый доменный use case: аудит кода на banned-паттерны.
2. **Уровни доверия** — `control/loop_trust_levels.md` с runtime-политикой L1/L2/L3 и hard gate на переходах.
3. **Планнеры**:
   - `tooll_subagents/planning/loop_planner.md` — координация `/loop` запросов.
   - `tooll_subagents/planning/goal_planner_v2.md` — `/goal` с разделением на cheap worker и expensive verifier.
4. **Cost guard** — интеграция `loop-cost` с `runtime/cost_tracking/` и hard stop при превышении бюджета.
5. **Loop engine runtime** — `runtime/loop_engine/`:
   - `loop_cost_estimator.py` — оценка стоимости loop до запуска.
   - `loop_verifier.py` — expensive verifier с adversarial verification (≥2 критиков).
   - `loop_skill_exporter.py` — экспорт workflow в `memory/wiki/` автоматически и в `.claude/skills/` после ручного approval.
   - `constraints_manager.py` — чтение/запись `.agent_loop/CONSTRAINTS.md`.
6. **CONSTRAINTS.md** — `.agent_loop/CONSTRAINTS.md` с авто-пополнением из верификатора.
7. **CLI tools**:
   - `python -m agentic_loop.loop_audit` — оценка готовности проекта к loops.
   - `python -m agentic_loop.loop_init` — scaffold нового loop из preset.
   - `python -m agentic_loop.loop_cost` — оценка стоимости конкретного loop.
8. **Anti-slop интеграция** — `anti_slop_sweeper.yaml` запускает дешёвые детекторы (`runtime/premium_design/`) + верификатор Opus, фиксирует ошибки в CONSTRAINTS.md и wiki.
9. **Тесты**:
   - `tests/runtime/test_loop_presets.py` — валидность YAML и параметры presets.
   - `tests/runtime/test_loop_engine.py` — cost estimator, verifier, constraints manager.
   - `tests/runtime/test_loop_trust_levels.py` — L1/L2/L3 gate logic.

### Не входит

- Остальные 4 паттерна из Loop Engineering (Daily Triage, Changelog Drafter, Post-Merge Cleanup, Issue Triage) — deferred до стабилизации первых трёх.
- Web-UI dashboard для loops.
- Автоматический `git push` / deploy / миграции БД — остаются в human zones.
- Интеграция со сторонними loop-библиотеками (loop-engineering, Loop Library, Orange Book) как dependencies; используем их только как vocabulary.
- MCP-server wrapper под loop engine в первой итерации.

## Key Decisions

1. **Только 3 presets в v1.** CI Sweeper, PR Babysitter, Dependency Sweeper — критично для повседневной разработки. Anti-slop Sweeper — четвёртый, как доменный proof-of-concept.
2. **L1/L2/L3 hard gate.** Любой preset стартует на L1. Переход L1→L2 требует ≥7 дней стабильных отчётов и ручной верификации. Переход L2→L3 требует ≤5% отказов и стабильного CONSTRAINTS.md. Deploy/push/DB migrations всегда L2/L3-gated.
3. **Cheap + expensive verifier.** `claude-haiku-4-5` для массовых parallel sub-agents, `claude-opus-4-8` для adversarial verification (≥2 независимых критика).
4. **CONSTRAINTS.md в `.agent_loop/`.** Подгружается в начало каждого loop-запуска через `constraints_manager.py`.
5. **Auto-write skills — исключение.** Loop-derived skills пишутся в `memory/wiki/` автоматически и в `.claude/skills/` после явного ручного approval (контролируется `loop_skill_exporter.py`).
6. **Hard cost stop.** `loop-cost` читает бюджет из `runtime/cost_tracking/`, loop runtime проверяет remaining budget перед каждым LLM-вызовом и останавливается при достижении лимита.
7. **CLI-first.** `loop-audit`, `loop-init`, `loop-cost` — Python CLI. MCP-обёртка возможна позже, но не в v1.
8. **Anti-slop как первый Self-Improving use case.** Используем уже реализованные `runtime/premium_design/` детекторы как cheap swarm, Opus как verifier.

## Architecture

```
User Request (/goal /loop /workflows)
  → main_loop.md
    → loop_planner.md / goal_planner_v2.md
      → loop_trust_levels.md (L1/L2/L3 gate)
        → cost guard (runtime/cost_tracking/)
          → cheap executor (claude-haiku-4-5 swarm)
            → loop_verifier.py (claude-opus-4-8 ≥2 critics)
              → if approved:
                  → constraints_manager.py updates CONSTRAINTS.md
                  → loop_skill_exporter.py writes to memory/wiki/
                  → if human approved: writes to .claude/skills/
              → if rejected: retry with constraints or escalate to human
```

## Deliverables

1. `runtime/loop_presets/ci_sweeper.yaml`
2. `runtime/loop_presets/pr_babysitter.yaml`
3. `runtime/loop_presets/dependency_sweeper.yaml`
4. `runtime/loop_presets/anti_slop_sweeper.yaml`
5. `control/loop_trust_levels.md`
6. `tooll_subagents/planning/loop_planner.md`
7. `tooll_subagents/planning/goal_planner_v2.md`
8. `runtime/loop_engine/loop_cost_estimator.py`
9. `runtime/loop_engine/loop_verifier.py`
10. `runtime/loop_engine/loop_skill_exporter.py`
11. `runtime/loop_engine/constraints_manager.py`
12. `runtime/loop_engine/__init__.py`
13. `.agent_loop/CONSTRAINTS.md` (seed-файл)
14. `agentic_loop/loop_audit.py` (CLI)
15. `agentic_loop/loop_init.py` (CLI)
16. `agentic_loop/loop_cost.py` (CLI)
17. `tests/runtime/test_loop_presets.py`
18. `tests/runtime/test_loop_engine.py`
19. `tests/runtime/test_loop_trust_levels.py`
20. `memory/wiki/tool/loop-engine.md` (wiki-страница)

## Success Criteria

1. Все 4 YAML presets валидны и содержат `goal`, `max_iterations`, `trust_level`, `schedule`, `verification_plan`, `human_zones`, `exit_conditions`.
2. `loop_trust_levels.md` корректно классифицирует операции по L1/L2/L3 и блокирует L3-автономность для `git push`, `deploy`, `rm -rf`, миграций БД.
3. `loop_cost_estimator.py` возвращает оценку в токенах и $ для любого preset.
4. `loop_verifier.py` запускает ≥2 независимых критика и требует согласия ≥2 для `approved`.
5. `constraints_manager.py` читает `.agent_loop/CONSTRAINTS.md`, добавляет правила и сохраняет без конфликтов.
6. `loop_skill_exporter.py` пишет в `memory/wiki/` автоматически, а в `.claude/skills/` только после explicit approval.
7. `loop-audit`, `loop-init`, `loop-cost` работают из командной строки.
8. Anti-slop sweeper запускает `runtime/premium_design/` детекторы + Opus verifier и обновляет CONSTRAINTS.md при обнаружении новых banned-паттернов.
9. Все тесты проходят: `pytest tests/runtime/test_loop_*.py`.
10. Кросс-ссылочная целостность не нарушена (`validate_cross_references.js` без ошибок).
11. `health_check.py --json` — healthy.

## Verification Plan

### Unit tests

```python
def test_ci_sweeper_preset_valid_yaml(): ...
def test_pr_babysitter_has_l1_exit_conditions(): ...
def test_loop_trust_levels_blocks_push_on_l3(): ...
def test_cost_estimator_returns_token_and_dollar_budget(): ...
def test_verifier_requires_two_critics(): ...
def test_constraints_manager_appends_rule(): ...
def test_skill_exporter_auto_writes_wiki_only(): ...
def test_anti_slop_sweeper_fails_on_banned_pattern(): ...
```

### Integration checks

- `python -m agentic_loop.loop_cost --preset runtime/loop_presets/ci_sweeper.yaml` → возвращает JSON с `estimated_tokens`, `estimated_usd`, `budget_ok`.
- `python -m agentic_loop.loop_audit` → JSON с `readiness_score`, `blockers`, `recommendations`.
- `python -m agentic_loop.loop_init --preset ci_sweeper --name my-ci` → создаёт `my-ci.loop.yaml` и обновляет `CONSTRAINTS.md` seed.
- Запуск anti-slop sweeper на тестовом fixture с banned pattern → verifier возвращает `fail`, в CONSTRAINTS.md появляется новое правило.

### Regression checks

- `pytest tests/runtime/test_loop_*.py`
- `node .agent_loop/scripts/validate_cross_references.js`
- `python .agent_loop/scripts/health_check.py --json`

## Human Zones

- Утверждение этой SPEC.md.
- Ручной approve для продвижения workflow из `memory/wiki/` в `.claude/skills/`.
- Перевод loop с L1 на L2 и с L2 на L3 — требует явного подтверждения.
- `git push`, deploy, `rm -rf`, миграции БД — никогда не выполняются автономно.
- Изменение `.agent_loop/CONSTRAINTS.md` вручную разрешено, но должно логироваться.

## Assumptions

- `runtime/cost_tracking/` уже работает и предоставляет API для бюджетов.
- `Workflow` tool, `CronCreate`, `ScheduleWakeup` доступны в текущей сессии.
- `runtime/premium_design/` уже содержит deterministic anti-slop детекторы.
- Пользователь понимает 4 издержки loops (verification debt, comprehension rot, token expenses, cognitive surrender) и согласен с L1→L2→L3 rollout.
- Presets не выполняют действия без проверки на L1; L3 допустим только для read-only/отчётных операций.

## Approval Request

Спека готова. Если всё ок — ответь **«да»**, **«ok»**, **«согласен»**, **«продолжай»** или **«+»**.  
Если нужно изменить — скажи, что именно.
