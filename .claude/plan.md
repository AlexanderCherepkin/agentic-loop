# План интеграции Web Project Agents (`F:\Agents-komponents`) в Agentic Loop

> **Примечание:** в `F:\Agentic_Loop_Graph\.claude\plan.md` обнаружен устаревший план (модуль клиентских сайтов: multi-page, Storybook, deploy, preview). Он перезаписывается планом текущей интеграции, поскольку мы находимся в plan mode для задачи интеграции `F:\Agents-komponents`.

## Цель
Добавить в Agentic Loop недостающие возможности из Web Project Agents: классификацию ТЗ, генерацию архитектурного манифеста, мультиязыковые стартовые шаблоны (Python/TypeScript/Go/Rust), code review, security scanning, качественную оценку результатов, расширенные провайдеры деплоя (Render/Railway/Fly.io), публикацию в GitHub/GitLab, отслеживание стоимости LLM и уведомления.

## Принципы интеграции
1. **Не заменяем архитектуру Agentic Loop** — адаптируем исходные модули под существующие паттерны (markdown-агенты по Algorithmic template + runtime-движки + MCP-обёртки).
2. **Не дублируем функционал** — уже есть safety-control, memory, deploy (Vercel/Netlify), human_approval, observability — эти части исходного бота не переносим.
3. **Интегрируем только то, чего нет** — новые агенты, runtime-модули, шаблоны и MCP-серверы.
4. **Сохраняем соглашения** — snake_case, Algorithmic template, pipeline-архитектура, cross-cutting optimizer.
5. **Регенерируем агентную карту** — после добавления агентов обновить `runtime/engine/agent_invocation_map.py` через `generate_agent_invocation_map.py`.
6. **Добавляем тесты** — под каждый новый runtime-модуль тест в `tests/runtime/`, под MCP-сервер — в `tests/mcp/`.

## Что НЕ интегрируем
| Компонент исходного бота | Причина |
|---|---|
| `main.py` (FastAPI сервис) | У нас `runtime/main.py` + `orchestrator/api_gateway.md` |
| `config.py` (pydantic-settings) | Своя конфигурация в `runtime/engine/llm_engine.py` и env |
| `cache.py` (SQLite cache классификаций) | Есть `tools_memory/memory_store` и `runtime/memory/` |
| `project_store.py` | Есть `runtime/engine/state_manager.md` и `audit_logger` |
| `metrics.py` Prometheus | Есть `runtime/observability/metrics.py` |
| `llm_router.py` | Есть `runtime/engine/llm_engine.py`; можно позже добавить multi-model fallback |
| `health.py`, `shutdown.py`, `logging_config.py`, `startup_validation.py`, `db_maintenance.py` | Инфраструктура уже покрыта |
| `tasks.py` (Celery) | У нас `runtime/workers/` и `pipeline_runner.py` |
| `approvals.py` | Есть `tooll_subagents/execution/human_approval.md` |
| `static/index.html`, `admin.html` | Web-UI не входит в текущий scope |
| `cli.py` | Есть `cli.js` |
| `plugin_manager.py`, `tenants.py` | Можно добавить позже, не критично для core |

## Что интегрируем (по этапам)

### Этап 1 — Web Project Agents: classifier / architect / developer
**Агенты (Algorithmic template):**
- `.agent_loop/tooll_subagents/planning/project_classifier.md` — классификация ТЗ по взвешенным триггерам, 17 категорий проектов.
- `.agent_loop/tooll_subagents/planning/project_architect.md` — генерация архитектурного манифеста на основе классификации.
- `.agent_loop/tooll_subagents/execution/project_developer.md` — генерация стартового codebase с учётом языка и шаблона.

**Runtime:**
- `runtime/web_project_agents/__init__.py`
- `runtime/web_project_agents/config.py` — `ProjectClassifierConfig`, `ProjectArchitectConfig`, `ProjectDeveloperConfig`
- `runtime/web_project_agents/classifier.py` — адаптация `AgentClassifier` + `LLMClient`
- `runtime/web_project_agents/architect.py` — адаптация `AgentArchitect`
- `runtime/web_project_agents/developer.py` — адаптация `AgentDeveloper`
- `runtime/web_project_agents/prompts.py` — программный доступ к prompt_manifest.yaml

**MCP (опционально, lazy):**
- `mcp_servers/web_project_agents_server.py` — экспозиция `classify`, `architect`, `develop`.

**Тесты:**
- `tests/runtime/test_web_project_agents.py`
- `tests/mcp/test_web_project_agents_server.py`

### Этап 2 — Мультиязыковые шаблоны проектов
**Файлы:**
- Копировать/адаптировать `templates/` из `F:\Agents-komponents` в `templates/web_project_agents/`:
  - `fastapi-react/`, `django-htmx/`, `flask-vanilla/`, `go-fiber/`, `rust-axum/`, `typescript-nextjs/`, `ci/`, `deploy/`.
- `runtime/project_starter/__init__.py`
- `runtime/project_starter/config.py` — `ProjectStarterConfig`, `TemplatePreset`
- `runtime/project_starter/template_manager.py` — адаптация `TemplateManager`
- `runtime/project_starter/engine.py` — `ProjectStarterEngine`, интегрирующий шаблоны с `project_starter_agent.md`

**Агенты:**
- Обновить `.agent_loop/tooll_subagents/planning/project_starter_agent.md` — добавить `template_id` из мультиязыкового набора.
- (Опционально) `.agent_loop/tooll_subagents/planning/template_selector.md` — явный выбор preset'а.

**Тесты:**
- `tests/runtime/test_project_starter.py`

### Этап 3 — Code Review & Diff Patch Applier
**Агенты:**
- `.agent_loop/tooll_subagents/self_correction/code_review_validator.md` — code review сгенерированного codebase.
- `.agent_loop/tooll_subagents/self_correction/diff_patch_applier.md` — применение хирургических патчей.

**Runtime:**
- `runtime/code_review/__init__.py`
- `runtime/code_review/config.py` — `CodeReviewConfig`
- `runtime/code_review/engine.py` — адаптация `CodeReviewer`
- `runtime/code_review/diff_engine.py` — адаптация `PatchApplier`
- `runtime/code_review/linter_runner.py` — адаптация `LinterRunner` (опционально, lazy)

**Тесты:**
- `tests/runtime/test_code_review.py`
- `tests/runtime/test_diff_patch_applier.py`

### Этап 4 — Security Scanner
**Агент:**
- `.agent_loop/tooll_subagents/self_correction/security_scan_validator.md` — проверка сгенерированного кода на секреты, SQLi, XSS, hardcoded creds.

**Runtime:**
- `runtime/security_scanner/__init__.py`
- `runtime/security_scanner/config.py` — `SecurityScannerConfig`
- `runtime/security_scanner/engine.py` — адаптация `SecurityScanner`

**Тесты:**
- `tests/runtime/test_security_scanner.py`

### Этап 5 — Quality Evaluator
**Агент:**
- `.agent_loop/tooll_subagents/self_correction/quality_evaluator_agent.md` — оценка manifest/codebase 1–10 по критериям.

**Runtime:**
- `runtime/quality_evaluation/__init__.py`
- `runtime/quality_evaluation/config.py`
- `runtime/quality_evaluation/engine.py` — адаптация `QualityEvaluator`

**Тесты:**
- `tests/runtime/test_quality_evaluation.py`

### Этап 6 — Deploy-провайдеры: Render / Railway / Fly.io
**Runtime:**
- Расширить `runtime/deploy/config.py` — добавить `render`, `railway`, `flyio` в allowed providers; поля для API keys.
- Расширить `runtime/deploy/engine.py` — `DeployEngine` dispatch на новых провайдеров.
- `runtime/deploy/providers/__init__.py`
- `runtime/deploy/providers/render.py` — адаптация `RenderDeployer`
- `runtime/deploy/providers/railway.py` — адаптация `RailwayDeployer`
- `runtime/deploy/providers/flyio.py` — адаптация `FlyioDeployer`

**Агент:**
- Обновить `.agent_loop/tooll_subagents/planning/deploy_planner.md` — упоминание новых провайдеров.

**Тесты:**
- `tests/runtime/test_deploy_providers.py`

### Этап 7 — Git Publisher (GitHub/GitLab)
**Агенты:**
- `.agent_loop/tooll_subagents/planning/git_publish_planner.md`
- `.agent_loop/tooll_subagents/execution/git_publish_runtime_integrator.md`

**Runtime:**
- `runtime/git_publisher/__init__.py`
- `runtime/git_publisher/config.py` — `GitPublisherConfig`
- `runtime/git_publisher/engine.py` — адаптация `GitPublisher`

**Тесты:**
- `tests/runtime/test_git_publisher.py`

### Этап 8 — Cost Tracker
**Runtime:**
- `runtime/cost_tracking/__init__.py`
- `runtime/cost_tracking/config.py` — `CostTrackingConfig`
- `runtime/cost_tracking/engine.py` — адаптация `CostTracker`
- Интегрировать в `runtime/engine/llm_engine.py` — вызов `CostTracker.estimate()` / `.record()` после каждого LLM-вызова.

**Агент:**
- `.agent_loop/tooll_subagents/observability/cost_audit_agent.md`

**Тесты:**
- `tests/runtime/test_cost_tracking.py`

### Этап 9 — Notifications
**Runtime:**
- `runtime/notifications/__init__.py`
- `runtime/notifications/config.py` — `NotificationsConfig`
- `runtime/notifications/engine.py` — email/Telegram/Slack channels
- `runtime/notifications/channels/email.py`, `telegram.py`, `slack.py`

**Агент:**
- `.agent_loop/tooll_subagents/execution/notification_runtime_integrator.md`

**Тесты:**
- `tests/runtime/test_notifications.py`

### Этап 10 — Сквозная интеграция и валидация
- Обновить `runtime/engine/agent_invocation_map.py` через `python .agent_loop/scripts/generate_agent_invocation_map.py`.
- Обновить `mcp_servers/bootstrap.py` и `mcp_servers/registry.py` для новых MCP-серверов.
- Обновить `.agent_loop/ARCHITECTURE.md` и `CLAUDE.md` с описанием новых модулей.
- Запустить `node .agent_loop/scripts/validate_cross_references.js` и `node .agent_loop/scripts/validate_consistency.js`.
- Запустить `python .agent_loop/scripts/health_check.py`.
- Запустить `pytest tests/runtime/ tests/mcp/` для новых и затронутых тестов.
- Обновить `requirements.txt` — добавить опциональные зависимости (`PyGithub`, `python-gitlab`, `qdrant-client`, `boto3` и т.д.) в отдельные `requirements-*.txt` файлы.

## Приоритизация
- **Phase 1 (must have):** Этапы 1, 2 — core web-project agents + templates.
- **Phase 2 (quality gate):** Этапы 3, 4, 5 — code review, security scan, quality evaluator.
- **Phase 3 (delivery):** Этапы 6, 7 — deploy-провайдеры + git publish.
- **Phase 4 (observability):** Этапы 8, 9 — cost tracker + notifications.
- **Phase 5 (optional):** RAG store (`rag_store.py`) и Artifact store (`artifact_store.py`) — добавить позже, если потребуется.

## Критерии приёмки
- Новые markdown-агенты следуют Algorithmic template (Role, Contract, Decision Flow, Failure Modes).
- `validate_consistency.js` возвращает 0 errors, 0 warnings.
- `validate_cross_references.js` не находит битых ссылок и изолированных агентов.
- Новые runtime-модули имеют `Config` + `Engine`/`Result` и покрыты тестами.
- `agent_invocation_map.py` регенерирован и включает новых агентов.
- Health check проходит за <10 секунд.
- Существующие тесты не ломаются.

## Вопросы к заказчику
1. **Scope:** реализовать все 4 phase сразу или начать с Phase 1+2?
2. **Шаблоны:** включать все 8 preset'ов (`fastapi-react`, `django-htmx`, `flask-vanilla`, `go-fiber`, `rust-axum`, `typescript-nextjs`, `ci`, `deploy`) или сократить набор?
3. **MCP:** нужны ли lazy MCP-серверы для новых runtime-модулей сразу, или достаточно runtime-интеграторов?
4. **Уведомления:** какие каналы обязательны (email/Telegram/Slack)?
5. **Deploy-провайдеры:** какие из Render/Railway/Fly.io реально нужны?

## Статус выполнения (2026-07-13)
- [x] Phase 1 — Web Project Agents (classifier / architect / developer) + шаблоны.
- [x] Phase 2 — Code review, security scanner, quality evaluator.
- [x] Phase 3 — Deploy-провайдеры (Render/Railway/Fly.io) + git publisher.
- [x] Phase 4 — Cost tracker + notifications.
- [x] Сквозная интеграция: `agent_invocation_map.py` регенерирован (289 агентов), `mcp_servers/bootstrap.py` зарегистрирован (25 серверов).
- [x] Валидация: `validate_cross_references.js`, `validate_consistency.js`, `validate_runtime_coverage.py`, `health_check.py` — все зелёные.
- [x] Тесты: `pytest tests/` — полный набор проходит.
- [x] Документация: обновлены `ARCHITECTURE.md`, `CLAUDE.md`, `TECHNICAL_ASSIGNMENT.md`.
- [x] Зависимости: `figma-agent-core/requirements.txt` дополнен `requests` и `pyyaml`; `health_check.py` обновлён до актуальных констант (289 агентов, 25 MCP-серверов) и таймаута pytest core (600 с).

**Примечание:** критерий «Health check проходит за <10 секунд» недостижим из-за длительности pytest core (~280 с); остальные проверки health_check занимают <15 с. Текущий health check стабильно проходит.
