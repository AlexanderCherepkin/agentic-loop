# План интеграции Ponytail Protocol в Agentic Loop

## Контекст

Пользователь приложил файл `1.docx` и репозиторий [DietrichGebert/ponytail](https://github.com/DietrichGebert/ponytail). Необходимо внедрить философию «ленивого старшего разработчика» (Ponytail) в наш автономный агент-бот для повышения стабильности, порядка и контролируемости использования контекста/ресурсов.

## Решения пользователя

1. Режим по умолчанию: **full**.
2. Обновлять `project_rules.md`, `CLAUDE.md`, `ARCHITECTURE.md` — **да** (требует отдельного human approval).
3. Команды: **режимы + review + audit** (`/ponytail`, `/ponytail-review`, `/ponytail-audit`); `debt/gain/help` — в следующем приоритете, не обязательны сейчас.

## Цель интеграции

Ponytail должен стать **cross-cutting policy/optimizer слоем**, аналогичным Lighthouse hard-gate или `project_rules.md`:
- инжекция правил в system prompt перед генерацией кода;
- дополнительная валидация результатов на over-engineering;
- целевой аудит репозитория по запросу;
- режимы `lite|full|ultra|off` через env-переменную и runtime-команды.

## Архитектурный подход

Ponytail не выносится в отдельную `tools_*` категорию (чтобы не нарушать 12 существующих pipeline и не плодить лишнюю инфраструктуру). Вместо этого:
- runtime-модуль `runtime/engine/ponytail_optimizer.py` реализует `PonytailOptimizer` (инжекция правил, метрики, конфиг);
- новые markdown-агенты размещаются в `tooll_subagents/planning/` и `tooll_subagents/self_correction/`;
- существующие агенты обновляются ссылками на новых.

## Изменения

### 1. Новый runtime-модуль

**Файл:** `runtime/engine/ponytail_optimizer.py`

Содержит:
- `PONYTAIL_CORE_PROMPT` — системное ядро с 7-ступенчатой лестницей лени и critical guardrail;
- `PONYTAIL_MODES` — `lite`, `full`, `ultra`, `off`;
- `PonytailOptimizer`:
  - `__init__(default_mode=None)` — читает `PONYTAIL_DEFAULT_MODE` (default `full`);
  - `set_mode(mode)`;
  - `inject_rules(base_system_prompt)` — вставляет core prompt + mode instruction;
  - `extract_metrics(original_code, generated_code)` — LoC-экономия;
  - `is_coding_task(request_type)` — heuristic для применения Ponytail;
  - `mode_enabled` property.

### 2. Новые markdown-агенты

Все следуют Algorithmic template (Role, Contract, Decision Flow, Failure Modes).

#### a) `tooll_subagents/planning/ponytail_injector.md`

**Role:** инжектор Ponytail rules в system prompt перед генерацией кода.

**Contract:**
- Receives: `base_system_prompt`, `task_type` (design_project / code_change / refactor / fix / review), `ponytail_mode` (env или user override).
- Returns: `optimized_system_prompt`, `mode_applied`, `guardrails`.
- Side effects: logs to `audit_logger.md`.

**Decision Flow:**
1. Determine effective mode (`off` для non-coding, иначе env/user override).
2. If `off` or non-coding → return base prompt unchanged.
3. Build Ponytail prompt: core + mode instruction.
4. Prepend to base system prompt.
5. Return optimized prompt and metadata.

**Failure Modes:**
| Condition | Response |
|---|---|
| Unknown mode | Fall back to `full`; log warning |
| Base prompt missing | Return Ponytail prompt alone |
| Non-coding task with coding mode | Force `off`; log |

#### b) `tooll_subagents/self_correction/ponytail_review.md`

**Role:** суб-агент валидации over-engineering в цикле self-correction.

**Contract:**
- Receives: `proposed_changes` (diff/code), `context`, `ponytail_mode`, `task_type`.
- Returns: `approved` boolean, `findings` list, `net_lines_removable` int, `refinement_actions`.

**Decision Flow:**
1. If mode is `off` or task is non-coding → `approved=true` with empty findings.
2. Scan for: redundant abstractions, avoidable dependencies, stdlib alternatives, native platform alternatives, duplicated existing code, speculative features.
3. Emit one-line findings: `L<line>: <tag> <what to cut>. <replacement>.`
4. Tags: `delete`, `stdlib`, `native`, `yagni`, `shrink`, `reuse`.
5. Aggregate `net_lines_removable`.
6. If any critical over-engineering found → `approved=false` and `refinement_actions`.
7. If nothing to cut → `'Lean already. Ship.'`

**Failure Modes:**
| Condition | Response |
|---|---|
| Empty proposed changes | `approved=true`; note 'no changes' |
| Review contradicts explicit user approval | Honor user approval; log override |
| Cannot parse diff | `approved=inconclusive`; escalate to human |

#### c) `tooll_subagents/planning/ponytail_audit.md`

**Role:** целевой аудит всего репозитория на over-engineering по команде `/ponytail-audit`.

**Contract:**
- Receives: `workspace_root`, `scope` (all / src / generated), `ponytail_mode`.
- Returns: `findings` list, `net_lines_removable`, `dependencies_removable`, `summary`.

**Decision Flow:**
1. If mode is `off` → return 'Ponytail disabled'.
2. Scan repository tree (excluding node_modules, .git, build, dist).
3. Identify dead code, stdlib reinventions, native-platform substitutions, YAGNI abstractions, shrink opportunities.
4. Rank by biggest cut first.
5. Return report; do not mutate files.

**Failure Modes:**
| Condition | Response |
|---|---|
| Workspace root unreadable | Return error finding |
| Scan exceeds timeout | Return partial findings with truncation notice |
| No findings | Return 'Lean already. Ship.' |

### 3. Обновление существующих агентов

#### `main_loop.md`

- Добавить в `Receives`: `ponytail_mode` (optional override).
- На шаге инициализации (Decision Flow step 1) загружать `PONYTAIL_DEFAULT_MODE` из env и передавать в `context.md`.
- Перед Plan phase для coding-task вызывать `ponytail_injector.md` для модификации system prompt генератора.
- Добавить ссылку на `ponytail_injector.md` в Failure Modes.

#### `tooll_subagents/planning/tool_plan_selection.md`

- В Decision Flow добавить шаг: если `task_type` ∈ {code_change, refactor, fix, design_project full_code}, включить `ponytail_injector.md` в план перед tool-агентами генерации кода.
- Добавить ссылку на `ponytail_injector.md` и `ponytail_audit.md` (для /ponytail-audit command).

#### `tooll_subagents/execution/tool_invocation.md`

- Добавить обработку специальных команд:
  - `/ponytail [lite|full|ultra|off]` — переключить режим сессии;
  - `/ponytail-review` — вызвать `ponytail_review.md` для последних изменений;
  - `/ponytail-audit` — вызвать `ponytail_audit.md`.
- Decision Flow step 4 добавить подшаг для распознавания slash-команд.
- Failure Modes: unknown command → log and abort.

#### `tooll_subagents/self_correction/result_validation.md`

- Добавить в `Receives`: `ponytail_review_report` (optional).
- Добавить Decision Flow step 10a (после Visual QA): Ponytail review verdict.
  - Если `approved=false` и есть `refinement_actions` → `validation_status=needs_refinement`, `retry_recommended=true`.
  - Если `approved=true` → contribution to `complete`.
- Failure Modes: добавить ссылку на `ponytail_review.md`.

#### `control/policy_enforcer.md`

- В Decision Flow step 1: если `project_rules.ponytail` присутствует, использовать его как fallback policy source.
- Добавить `operational` policy context для Ponytail.
- Failure Modes: добавить обработку конфликта Ponytail mode с active policy.

### 4. Обновление документации (human approval gate)

#### `project_rules.md`

Добавить раздел:
```markdown
## Ponytail Protocol

- Default mode: `full` (env `PONYTAIL_DEFAULT_MODE` overrides).
- Apply the 7-step Ladder of Laziness before writing code: YAGNI → reuse → stdlib → native platform → installed dependency → one-liner → minimum code.
- Never trade away: security, data validation, error handling, accessibility, tests, database integrity.
- Slash commands: `/ponytail [lite|full|ultra|off]`, `/ponytail-review`, `/ponytail-audit`.
- Mark deliberate simplifications with `ponytail:` comments naming ceiling and upgrade path.
```

#### `CLAUDE.md`

- В Quick Reference добавить строку про Ponytail.
- В Cross-Session Memory / Active Skills упомянуть `/ponytail`.
- В Conventions добавить `ponytail:` comment convention.

#### `ARCHITECTURE.md`

- В Directory Tree добавить новых агентов в `tooll_subagents/planning/` и `tooll_subagents/self_correction/`.
- Обновить Agent Counts: `tooll_subagents` 30 → 32 (или пересчитать точно).
- В Key Decisions добавить пункт про cross-cutting Ponytail optimizer.

### 5. Валидация и тесты

- Запустить `node scripts/validate_cross_references.js` — ожидается 0 broken links, 0 isolated agents.
- Запустить `node scripts/validate_consistency.js` — ожидается 0 errors.
- Запустить `python -m pytest` или соответствующие runtime-тесты.
- Проверить, что новые агенты имеют все 4 обязательных раздела Algorithmic template.

## Порядок выполнения

1. Создать `runtime/engine/ponytail_optimizer.py`.
2. Создать markdown-агентов:
   - `tooll_subagents/planning/ponytail_injector.md`
   - `tooll_subagents/self_correction/ponytail_review.md`
   - `tooll_subagents/planning/ponytail_audit.md`
3. Обновить существующих агентов (main_loop, tool_plan_selection, tool_invocation, result_validation, policy_enforcer).
4. Запросить human approval для обновления `project_rules.md`, `CLAUDE.md`, `ARCHITECTURE.md`.
5. После approval обновить документацию.
6. Запустить валидаторы и тесты; исправить ошибки.

## Риски и ограничения

- Добавление новых агентов увеличивает счётчик агентов; ARCHITECTURE.md должен быть точно пересчитан.
- `project_rules.md` и `CLAUDE.md` требуют explicit human approval — работа не может считаться завершённой без него.
- Ponytail review может конфликтовать с safety/quality assessor; resolution mode `most_restrictive` должен применяться.
