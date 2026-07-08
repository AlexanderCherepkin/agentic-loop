# Техническое задание: Agentic Loop

## 1. Общие сведения

**Название системы:** Agentic Loop — многоагентная AI-система с иерархической архитектурой «безопасность прежде всего».  
**Цель:** Создать расширяемую систему оркестрации из 248 специализированных агентов/файлов, реализующую цикл ReAct (Reasoning + Acting) с многоуровневой защитой, взаимной проверкой и самокоррекцией.  
**Язык реализации:** Markdown-спецификации (алгоритмические шаблоны агентов) и вспомогательные runtime-модули Python/TypeScript для интеграции i18n, аналитики и cookie-согласия.  
**Масштаб:** 253 агента/файла, 6 слоёв, 12 категорий инструментов + Figma-to-code MCP сервер + Backend Spec Bridge MCP сервер.

---

## 2. Функциональные требования

### 2.1 Головной цикл (main_loop)
- Система должна иметь единую точку входа — агент `main_loop.md`.
- Головной цикл реализует полный цикл ReAct: инициализация → приём запроса → предварительная проверка безопасности → ветка design_intake (для дизайн-проектов) → планирование → цикл выполнения (план/выполнение/наблюдение/валидация/коррекция) → синтез результата → пост-проверка безопасности → финальная взаимная проверка → доставка → очистка.
- Цикл должен поддерживать бюджет итераций и автоматическое завершение при исчерпании бюджета или при достижении цели.
- При обнаружении дизайн-проекта (`request_type=design_project`) головной цикл маршрутизирует запрос в `figma_design_analyst.md` и `design_to_code_planner.md`, после чего либо продолжает обычное планирование (для технического задания), либо сразу передаёт результат в слой `result/` (для полного кода).

### 2.2 Оркестратор (orchestrator) — 6 агентов
- **router** — маршрутизация запросов между слоями на основе типа payload, слоя-источника и политики маршрутизации (direct/load_balanced/priority_queue/failover).
- **dispatcher** — брокер выполнения: маршалинг параметров, контроль таймаутов, ретраи, circuit breaker.
- **pipeline_coordinator** — макро-оркестрация многофазных workflows с проверкой инвариантов (безопасность перед выполнением, валидация перед результатом).
- **state_manager** — персистентное и эфемерное состояние сессий, агентов и pipeline'ов; оптимистичный concurrency; checkpoint/restore; репликация.
- **api_gateway** — единая точка входа/выхода для внешнего API; аутентификация, rate limiting, трансляция протоколов, TLS pinning.
- **message_bus** — внутренняя шина pub/sub с гарантиями доставки (at_most_once / at_least_once / exactly_once) и обработкой dead-letter.

### 2.3 Безопасность (safety-control) — 9 агентов
- **input_sanitizer** — нормализация входных данных, удаление управляющих символов, обнаружение хомоглифов.
- **permission_checker** — проверка авторизации по принципу наименьших привилегий; allow/deny/escalate.
- **command_guard** — перехват команд shell/системы; предотвращение деструктивных операций (rm -rf, mkfs и т.д.); вердикты: allow/rewrite/block.
- **threat_detector** — обнаружение prompt injection, jailbreak, социальной инженерии; сигнатурный анализ + семантический анализ.
- **data_leak_preventer** — сканирование исходящего контента на PII, учётные данные, секреты; редукция через `[REDACTED:type]`.
- **output_reviewer** — финальная проверка качества и политики для контента, покидающего систему.
- **bias_detector** — аудит справедливости и беспристрастности по защищённым признакам.
- **safety_assessor** — предварительная оценка риска действия; композитный safety_score (0–1).
- **content_checker** — проверка соответствия доменно-специфичным правилам (медицинские, юридические, финансовые дисклеймеры).

### 2.4 Взаимная проверка (mutual_check) — 10 агентов
- **audit_logger** — неизменяемый append-only лог с SHA-256 целостностью.
- **action_verifier** — сравнение снимков состояния до/после для подтверждения ожидаемых изменений.
- **consistency_checker** — межслоевая когерентность (временная, логическая, референциальная, версионная, семантическая).
- **result_validator** — финальная автоматическая валидация результата перед доставкой.
- **performance_monitor** — отслеживание latency, throughput, error rate, resource utilization.
- **quota_manager** — управление ресурсными квотами с бакетами per-identity.
- **anomaly_detector** — поведенческая форензика: статистические тесты, isolation forest, autoencoder.
- **quality_assessor** — оценка корректности, ясности, полноты, эффективности, поддерживаемости, безопасности выхода агента.
- **feedback_aggregator** — синтез сигналов от пользователей, агентов безопасности и ассессоров качества.
- **compliance_checker** — регуляторное соответствие (GDPR, HIPAA, SOC2, ISO27001) с иерархией разрешения конфликтов.

### 2.5 Контроль (control) — 7 агентов
- **file_system_guard** — ограничение файловых операций одобренными директориями; защита от path traversal; ACL per-identity.
- **network_guard** — контроль исходящего/входящего сетевого трафика; allow/deny-списки; bandwidth caps; TLS pinning.
- **resource_monitor** — watchdog CPU/memory/disk/GPU/IO с авто-тротлингом, прерыванием и emergency GC.
- **human_oversight** — стратегический human-in-the-loop; классификация срочности; fallback по таймауту.
- **policy_enforcer** — runtime rule engine с режимами разрешения конфликтов (most_restrictive, hierarchy, timestamp, human_override).
- **scope_manager** — предотвращение scope creep; отслеживание авторизованных ресурсов/тем/инструментов.
- **input_aggregation** — консолидация сигналов безопасности, политических решений и состояний ресурсов в единый control directive.

### 2.6 Подагенты цикла ReAct (tooll_subagents) — 90 агентов
Цикл разбит на 6 фаз:
1. **user** (4): request — парсинг и классификация; context — сбор контекста; limitations — каталог ограничений; design_intake — распознавание дизайн-проектов (Figma URL, node ID, локальный JSON, дизайн-бриф) и формирование `design_descriptor`.
2. **planning** (41): task_decomposition — декомпозиция; cost_risk_assessment — оценка стоимости и риска; tool_plan_selection — выбор инструментов; internal_monologue — явное рассуждение; figma_design_analyst — анализ дизайна и генерация структуры/спецификации/кода через MCP; figma_precise_mode_auditor — Builder.io-style readiness audit перед генерацией кода; design_to_code_planner — принятие решения о выдаче технического задания или готового кода; backend_spec_bridge — сопоставление backend-спецификации с UI и генерация backend-слоя; responsive_composer — генерация breakpoint-вариантов и constraint-классов Tailwind; component_registry — построение реестра Figma-компонентов (Component Sets, Variants, Instances) и генерация `src/components/ui/*.tsx`; component_mapper — сопоставление Component Sets с React-компонентами и запись mapper-файлов; asset_agent — обнаружение, классификация и планирование загрузки Figma-ассетов; image_enrichment_agent — поиск/загрузка fallback-изображений для card/hero placeholders; i18n_requirements_analyst — извлечение требований мультиязычности; i18n_language_detector — определение языка Figma-текстов; i18n_key_extractor — преобразование текста в i18n-ключи; i18n_dictionary_generator — генерация словарей для целевых локалей; i18n_routing_planner — планирование Next.js i18n routing; i18n_component_rewriter — манифест замены литералов на `t()`; i18n_optimizer — оптимизация загрузки словарей; analytics_requirements_analyst — извлечение требований аналитики; analytics_provider_selector — выбор провайдеров аналитики; analytics_event_mapper — преобразование Figma-взаимодействий в события; analytics_script_injector — планирование безопасной вставки скриптов; analytics_optimizer — минимизация влияния аналитики; cookie_consent_jurisdiction_mapper — маппинг юрисдикций согласия; cookie_consent_policy_generator — генерация локализованной политики cookies; cookie_consent_banner_planner — проектирование UI баннера согласия; auth_requirements_analyst — извлечение требований идентификации/аутентификации; auth_provider_selector — выбор провайдера идентификации (Clerk/Auth0); cms_requirements_analyst — извлечение требований динамических секций (блог, портфолио, кейсы); cms_source_selector — выбор источника данных (local_markdown, Notion, Contentful, Strapi, Prisma, Airtable, Google Sheets, CMS API); accessibility_requirements_analyst — извлечение требований доступности по WCAG 2.1; accessibility_checker_planner — планирование статических и браузерных проверок доступности; pwa_requirements_analyst — извлечение требований PWA и performance budget; pwa_optimizer — выбор стратегии манифеста, service worker, offline-страницы и оптимизации ресурсов; design_token_docs_requirements_analyst — извлечение требований к документации токенов для клиента/команды; design_token_docs_format_selector — выбор форматов документации (markdown/json/html) и плана выдачи.
3. **execution** (13): tool_invocation — диспетчеризация; safety_guardrails — live runtime safety; human_approval — тактическое одобрение; action_logging — неизменяемый журнал выполнения; i18n_runtime_integrator — материализация next-intl артефактов; i18n_fallback_resolver — разрешение недостающих переводов; analytics_runtime_integrator — материализация аналитики и баннера согласия; cookie_consent_blocker — блокировка скриптов до согласия; auth_runtime_integrator — материализация Clerk/Auth0 обёрток, middleware и env-шаблона; cms_runtime_integrator — материализация слоя данных Next.js App Router для динамических секций; accessibility_runtime_integrator — запуск статического WCAG-аудита через `runtime/accessibility/AccessibilityEngine`; pwa_runtime_integrator — материализация манифеста, service worker, offline-страницы и диагностики бюджетов через `runtime/pwa/PwaEngine`; design_token_docs_runtime_integrator — генерация markdown/json/html документации по токенам через `runtime/design_token_docs/DesignTokenDocsEngine`.
4. **observability** (19): environment_result — снимок среды; runtime_output — парсинг stdout/stderr/exit codes; file_context — отслеживание мутаций файлов; memory_enrichment — обогащение долгосрочной памяти; headroom_compressor/headroom_retriever — сжатие/восстановление больших артефактов; memanto_remember/recall/answer — семантическая память; mem0_remember/recall/list — гибридная долгосрочная память; i18n_audit_agent — аудит мультиязычности; analytics_audit_agent — аудит аналитики и согласия; auth_audit_agent — аудит реализации идентификации/аутентификации; cms_audit_agent — аудит реализации динамических секций и fallback; accessibility_audit_agent — аудит реализации доступности и WCAG-соответствия; pwa_audit_agent — аудит реализации PWA, performance budget и offline-UX; design_token_docs_audit_agent — аудит документации токенов: полнота, корректность, соответствие аудитории.
5. **self_correction** (14): result_validation — проверка результатов; plan_adjustment — коррекция плана; recursion_or_termination — решение продолжать/завершить; assistance_request — эскалация к человеку; goal_evaluator — fast-critic оценки прогресса по цели (/goal); ponytail_review — проверка over-engineering для сгенерированного/отрефакторенного кода; i18n_rtl_validator — проверка RTL-поддержки; i18n_missing_key_guard — проверка полноты ключей; analytics_privacy_validator — проверка приватности аналитики; auth_validator — проверка корректности обёрток идентификации/аутентификации; cms_validator — проверка корректности интеграции динамических секций; accessibility_validator — проверка результатов WCAG-аудита и формирование refinement_actions; pwa_validator — проверка результатов PWA/performance audit и формирование refinement_actions; design_token_docs_validator — проверка полноты документации токенов и формирование refinement_actions.
6. **result** (4): solution — финальное решение; modified_files — инвентарь изменений; action_report — отчёт о действиях; summary_recommendations — рекомендации.

### 2.7 Инструментальные агенты (tools_*) — 123 агента
12 категорий по 10+ агентов + cross-cutting optimizer на категорию. Кроме того, `mcp_servers/figma_server.py` предоставляет MCP-обёртку вокруг `figma-agent-core/` для приёма дизайн-проектов:
- **tools_read** — read_file pipeline (linear): path_resolver, permission_agent, encoding_agent, chunking_agent, parser_agent, content_extractor, integrity_checker, cache_agent, result_formatter, read_optimizer.
- **tools_search** — search_code pipeline (diamond): scope_detector, permission_agent, indexer_agent, regex_searcher, semantic_searcher, relevance_scorer, deduplicator, snippet_builder, diff_generator, search_optimizer.
- **tools_replace** — replace_in_file pipeline (safety-gated): pattern_matcher, change_validator, conflict_resolver, backup_agent, diff_generator, verify_agent, write_executor, rollback_agent, result_ranker, edit_optimizer.
- **tools_runcom** — run_command pipeline (sandboxed): command_builder, sandbox_agent, env_manager, timeout_watcher, executor_agent, output_collector, error_analyzer, write_executor, write_planner, command_optimizer. (10 агентов)
- **tools_runtest** — run_tests pipeline (framework-dispatch): test_discovery, test_planner, test_executor, log_parser, failure_analyzer, fix_suggestor, coverage_analyzer, flaky_detector, report_generator, test_optimizer.
- **tools_terminal** — terminal_io pipeline (session-stateful): session_manager, terminal_state, command_history, io_handler, stream_reader, stream_writer, ansi_parser, output_filter, error_detector, terminal_optimizer.
- **tools_manangr** — project_manager pipeline (analysis-planning): structure_analyzer, dependency_mapper, task_planner, file_organizer, config_manager, doc_generator, refactor_planner, impact_analyzer, build_manager, project_optimizer.
- **tools_database** — database_query pipeline (query-lifecycle): query_builder, schema_analyzer, connection_manager, query_executor, result_mapper, transaction_manager, cache_manager, error_analyzer, migration_helper, db_optimizer.
- **tools_web** — web_request pipeline (request-lifecycle): request_builder, auth_manager, network_checker, rate_limiter, response_parser, content_extractor, caching_agent, retry_manager, error_handler, web_optimizer.
- **tools_memory** — memory_store pipeline (store-lifecycle): memory_writer, memory_reader, context_compressor, index_manager, eviction_policy, summarizer, embedding_agent, recall_optimizer, consistency_checker, memory_optimizer.
- **tools_browser** — headless_automation pipeline (browser-lifecycle): session_manager, navigation_engine, screenshot_agent, dom_extractor, selector_resolver, interaction_agent, network_interceptor, cookie_storage_agent, captcha_challenge_agent, error_handler, visual_qa_agent, browser_optimizer. (12 агентов)
- **tools_lighthouse** — audit pipeline (quality-lifecycle): session_manager, navigation_engine, audit_runner, report_parser, metric_guard_performance, metric_guard_a11y, metric_guard_best_practices, metric_guard_seo, correction_prompt_builder, loop_terminator, lighthouse_optimizer. Hard gate 100% по четырём столпам Lighthouse (Performance, Accessibility, Best Practices, SEO) через Playwright; парсинг 500 KB отчёта в компактный correction prompt; convergence guard 8 итераций; эскалация человеку при неудаче. Реализован в `tools_lighthouse/audit/` и интегрирован в `self_correction/result_validation.md`.
- **figma (MCP)** — Figma-to-code pipeline: figma_bootstrap, figma_analyze, figma_generate_spec, figma_extract_tokens, figma_responsive_compose, figma_build_component_registry, figma_extract_components, figma_generate_component, figma_map_interactions, figma_download_assets, figma_run_pipeline. Visual QA V2: автоматическая загрузка референсного скриншота Figma, стабильный Chromium (viewport, fonts, disabled animations), структурные проверки layout (overflow, clipped text, overlaps, bbox mismatch) и интеграция с refinement loop. Реализован в `mcp_servers/figma_server.py`, лениво загружается и работает с `figma-agent-core/`.

### 2.8 MCP gateway (lazy loading)
- `mcp_servers/gateway.py` exposes category metadata to the planner without constructing server instances.
- `mcp_servers/backend_server.py` provides the Backend Spec Bridge MCP server for fullstack generation from OpenAPI/Prisma/text specs; lazy-loaded and works only when `figma-agent-core/` is present.
- `mcp_servers/registry.py` supports lazy server factories; servers materialize only when a tool is invoked.
- `mcp_servers/bootstrap.py` defaults to lazy mode; `--eager` is used for `--test`/`--serve`.
- `runtime/engine/llm_engine.py` provides `LLMConfig.mcp_enabled` to include/exclude MCP categories from the planner context.
- `mcp_servers/browser_server.py` provides optional Playwright-based dynamic page automation; it is lazy-loaded and degrades gracefully if Playwright is not installed.
- `runtime/requirements-browser.txt` lists the optional Playwright dependency so the core `runtime/requirements.txt` remains lightweight; install with `pip install -r runtime/requirements.txt -r runtime/requirements-browser.txt && playwright install`.

### 2.9 Project rules context
- `project_rules.md` in the workspace root is a lightweight project-level context artifact.
- `tooll_subagents/user/context.md` loads it at session start; `tooll_subagents/planning/tool_plan_selection.md` uses it to rank tools; `control/policy_enforcer.md` uses it as a fallback policy source.
- Updates to `project_rules.md` require explicit human approval via `tooll_subagents/execution/human_approval.md` (`action_type=project_rules_update`).

---

## 3. Архитектурные требования

### 3.1 Иерархия слоёв
```
User Request
  → main_loop
    → orchestrator/router
      → safety-control (input sanitization, permission check, threat detection)
        → safety-control/mutual_check (cross-validation)
          → control (scope, policy, resource enforcement)
            → orchestrator/dispatcher
              → tooll_subagents/user (user context)
              → tooll_subagents/planning (task decomposition)
              → tooll_subagents/execution (tool invocation)
                → tools_* (specialized tool agents)
              → tooll_subagents/observability (result capture)
              → tooll_subagents/self_correction (validate → adjust → loop or finish)
              → tooll_subagents/result (final output)
    → User Response
```

### 3.2 Трёхконтурная безопасность
- **Контур 1:** safety-control — входная санитизация, разрешения, угрозы.
- **Контур 2:** mutual_check — взаимная проверка, аудит, консистентность.
- **Контур 3:** control — runtime enforcement, scope, policy, ресурсы.

### 3.3 Human-in-the-loop
- **Стратегический:** `control/human_oversight.md` — критические решения, политические конфликты, нарушения инвариантов.
- **Тактический:** `tooll_subagents/execution/human_approval.md` — высокорисковые/необратимые действия.

### 3.4 Декомпозиция ReAct
Каждая фаза цикла ReAct разбита на атомарные под-шаги, каждый со своим агентом. Фаза не может начаться до завершения предыдущей (инварианты pipeline_coordinator).

### 3.5 Условные переходы (Conditional Edges)
Переходы между фазами ReAct управляются runtime-конструктом `PhaseTransitionManager` в `runtime/engine/pipeline_runner.py`. Менеджер читает enum-выходы агентов (`cost_risk_assessment.recommendation`, `tool_invocation.next_action`, `safety_guardrails.recommendation`, `result_validation.validation_status`, `recursion_or_termination.decision`) и выбирает следующую фазу. При отсутствии специфических условий используется default sequence: user → planning → execution → observability → self_correction → result. Safety-before-execution инвариант сохраняется: любой safety abort или escalation направляется напрямую в `result`, минуя `execution`.

### 3.6 Инструменты как микросервисы
Каждая категория `tools_*` — независимый pipeline из 10 агентов с оптимизатором. Pipeline типы: linear (read), diamond (search), safety-gated (replace), sandboxed (runcom), framework-dispatch (runtest), session-stateful (terminal), analysis-planning (manangr), query-lifecycle (database), request-lifecycle (web), store-lifecycle (memory), headless-automation (browser).

---

## 4. Требования к шаблону агента

Каждый агент должен следовать **Algorithmic template**:

```markdown
# Agent Name

## Role
Одно-два предложения о назначении.

## Contract

### Receives
- `field`: тип / описание

### Returns
- `field`: тип / описание

### Side effects
- Перечисление побочных эффектов (если есть)

## Decision Flow
1. Шаг 1...
2. Шаг 2...
   - Подшаг...
3. Шаг 3...

## Failure Modes
| Condition | Response |
|---|---|
| Условие | Действие |
```

### Обязательные разделы
- `## Role` — роль агента
- `## Contract` — контракт (Receives, Returns, Side effects)
- `## Decision Flow` — нумерованный алгоритм принятия решений
- `## Failure Modes` — таблица Condition → Response

### Именование
- Файлы: snake_case.md
- Сохранены опечатки: `tooll_subagents` (двойное «l»), `tools_manangr` (вместо manager)

---

## 5. Требования к безопасности

### 5.1 Входная защита
- Все внешние входные данные проходят через `input_sanitizer` и `threat_detector`.
- Shell-команды перехватываются `command_guard`.
- Prompt injection и jailbreak должны быть обнаружены с confidence > 0.9.

### 5.2 Исходящая защита
- Все исходящие данные проходят через `data_leak_preventer` и `output_reviewer`.
- PII, секреты и учётные данные должны быть редуцированы.

### 5.3 Аудит
- Все действия логируются в `audit_logger` с SHA-256 целостностью.
- Логи неизменяемы; репликация async/sync в зависимости от критичности.

### 5.4 Compliance
- Соответствие GDPR, HIPAA, SOC2, ISO27001 через `compliance_checker`.
- Иерархия разрешения конфликтов: human_override > most_restrictive > hierarchy > timestamp.

---

## 6. Требования к интеграции

### 6.1 Внутренние связи
- Каждый агент должен иметь минимум одну входящую ссылку от другого агента (нет изолированных агентов).
- Ссылки между агентами должны быть валидны (не указывать на несуществующие файлы).
- Валидатор: `.agent_loop/scripts/validate_cross_references.js`.

### 6.2 Внешний API
- Единая точка входа: `api_gateway.md`.
- Поддерживаемые протоколы: HTTP/1, HTTP/2, gRPC, WebSocket, webhook.
- Rate limiting через `quota_manager`.

### 6.3 Память
- Долгосрочная память через `tools_memory/memory_store`.
- Каждый факт/решение/урок извлекается `memory_enrichment` и индексируется `embedding_agent`.
- Индекс: `MEMORY.md` в директории памяти.

### 6.4 Auth/identity интеграция
- Для SaaS landing pages и personal sites с личным кабинетом/dashboard система должна генерировать Clerk/Auth0 обёртки через `runtime/auth/AuthIntegrationEngine`.
- Поддерживаемые провайдеры: `clerk` и `auth0`.
- Генерируемые артефакты: `src/components/auth/AuthProvider.tsx`, `src/components/auth/SignInButton.tsx`, `src/components/auth/UserButton.tsx`, `src/components/auth/ProtectedRoute.tsx`, `src/app/sign-in/page.tsx`, `.env.local.example`, а также `middleware.ts` (только если отсутствует).
- Планирование: `auth_requirements_analyst.md` извлекает требования, `auth_provider_selector.md` выбирает провайдера, `auth_runtime_integrator.md` материализует код, `auth_validator.md` проверяет результат, `auth_audit_agent.md` аудирует финальную реализацию.
- Существующий `middleware.ts` не перезаписывается; в отчёт добавляется заметка.

### 6.5 CMS/data queries интеграция
- Для динамических секций (`blog`, `portfolio`, `cases`, `news`, `works`) система должна генерировать провайдерно-независимый слой данных Next.js App Router через `runtime/cms_queries/CmsQueriesEngine`.
- Поддерживаемые источники: `local_markdown`, `notion`, `contentful`, `strapi`, `prisma`, `airtable`, `google_sheets`, `cms_api`.
- Генерируемые артефакты: `src/lib/cms.ts` (тип `CmsItem`, `getEntries`, `getEntry`), `src/lib/cms/localMarkdown.ts` (загрузчик `.md` с frontmatter), `src/lib/cms/staticFallback.ts` (статический fallback), `src/components/cms/PostCard.tsx`, `src/components/cms/ProjectCard.tsx`, `src/components/cms/CaseStudyCard.tsx`, `src/app/{blog,portfolio,cases}/page.tsx` и `src/app/{blog,portfolio,cases}/[slug]/page.tsx`, `.env.local.example` с плейсхолдерами для выбранного источника.
- Для внешних источников движок добавляет нужный npm-пакет в `package.json` (например, `@notionhq/client` для Notion, `contentful` для Contentful, `@prisma/client` для Prisma).
- Существующий `src/lib/cms.ts` не перезаписывается; в отчёт добавляется заметка.
- Планирование: `cms_requirements_analyst.md` извлекает требования, `cms_source_selector.md` выбирает источник, `cms_runtime_integrator.md` материализует код, `cms_validator.md` проверяет результат, `cms_audit_agent.md` аудирует финальную реализацию.

### 6.6 Доступность / WCAG 2.1 интеграция
- Для каждого сгенерированного фронтенда система должна выполнять детерминированный статический WCAG 2.1 аудит через `runtime/accessibility/AccessibilityEngine`.
- Поддерживаемые проверки: `contrast` (контраст текста/фона), `focus_visible` (видимый фокус на интерактивах), `focus_order` (порядок табуляции), `aria` (роли и обязательные атрибуты ARIA, уникальные ID, корректные ссылки), `keyboard_trap` (клавиатурные ловушки на кастомных div), `heading_hierarchy` (иерархия заголовков), `alt_text` (alt у изображений), `form_label` (связка label/input).
- Уровни WCAG: `WCAG21_A`, `WCAG21_AA` (по умолчанию), `WCAG21_AAA`.
- Генерируемые артефакты: структурированный `accessibility_report` с `violations`, `score` и `files_audited`; `accessibility_validator.md` транслирует нарушения в `refinement_actions`; `accessibility_audit_agent.md` формирует итоговый compliance-отчёт.
- Планирование: `accessibility_requirements_analyst.md` извлекает требования, `accessibility_checker_planner.md` строит план проверок; исполнение: `accessibility_runtime_integrator.md`; самокоррекция: `accessibility_validator.md`; аудит: `accessibility_audit_agent.md`.

### 6.7 PWA + performance budget интеграция
- Для каждого сгенерированного фронтенда система должна генерировать PWA-артефакты и диагностировать performance budget через `runtime/pwa/PwaEngine`.
- Поддерживаемые артефакты: `manifest.json` (icons, theme, display), `sw.js` (cache-first/offline fallback), `offline.html`, `src/lib/pwa.ts` (регистрация service worker), `src/lib/pwa-meta.ts` (мета-теги/манифест линк), `src/components/PwaRegister.tsx` (React-обёртка регистрации).
- Поддерживаемые бюджеты: JS/CSS bundles, изображения, шрифты, сторонние скрипты; для каждого вычисляется фактический размер и флаг `over_budget`; накопленные нарушения транслируются в `refinement_actions`.
- Поддерживаемые оптимизации: `srcset`/`sizes` для изображений (mobile/tablet/desktop breakpoints), подсказки по font subsetting (`next/font/google` + `subsets`), патч `next.config.js` (`poweredByHeader: false`), idempotent повторный запуск.
- Планирование: `pwa_requirements_analyst.md` извлекает требования, `pwa_optimizer.md` выбирает стратегию; исполнение: `pwa_runtime_integrator.md`; самокоррекция: `pwa_validator.md`; аудит: `pwa_audit_agent.md`.

### 6.8 Документация токенов (design token docs) интеграция
- Для каждого сгенерированного фронтенда система должна генерировать клиентскую/командную документацию по дизайн-токенам через `runtime/design_token_docs/DesignTokenDocsEngine`.
- Источники: `design_tokens.json` (цвета, типографика, маппинги стилей/переменных) и опциональный `component_registry.json` (связь токенов с компонентами).
- Генерируемые артефакты: `docs/DESIGN_TOKENS.md` (таблица цветов с превью, типографика, компоненты, маппинги), `docs/design_tokens.docs.json` (структурированный JSON для инструментов), и опционально `docs/design_tokens.html` (клиентская HTML-страница).
- Планирование: `design_token_docs_requirements_analyst.md` извлекает требования (аудитория, форматы, секции); `design_token_docs_format_selector.md` выбирает форматы (markdown/json/html) и план выдачи; исполнение: `design_token_docs_runtime_integrator.md`; самокоррекция: `design_token_docs_validator.md`; аудит: `design_token_docs_audit_agent.md`.

---

## 7. Требования к качеству и валидации

### 7.1 Целостность графа ссылок
- 0 битых ссылок (исключая документационные цели: README, API, CHANGELOG, MEMORY).
- 0 изолированных агентов.
- Проверка осуществляется скриптом `validate_cross_references.js`.

### 7.2 Полнота шаблона
- 100% агентов содержат все 4 обязательных раздела Algorithmic template.
- 0 заглушек (stub'ов).

### 7.3 Кросс-ссылки
- Каждый агент в `Failure Modes` и `Decision Flow` должен ссылаться на других агентов, которых он вызывает или уведомляет.
- Взаимные проверки (`mutual_check`) должны ссылаться на агентов, которые они валидируют.

---

## 8. Требования к производительности

### 8.1 Масштабируемость
- Каждый pipeline `tools_*` должен поддерживать параллельное выполнение независимых агентов.
- `message_bus` должен поддерживать backpressure при превышении queue_depth.

### 8.2 Отказоустойчивость
- Circuit breaker в `dispatcher` и `api_gateway`.
- Checkpoint/restore в `state_manager`.
- Dead-letter queue в `message_bus`.
- Rollback в `tools_replace` и `tools_database`.

### 8.3 Таймауты
- Каждый агент имеет SLA; превышение → retry или abort.
- `timeout_watcher` в `tools_runcom` и `pipeline_coordinator` отслеживает зависшие фазы.

---

## 9. Требования к документации

### 9.1 Архитектурная документация
- `ARCHITECTURE.md` — полное дерево директорий, диаграмма потока, подсчёт агентов, соглашения об именовании, ключевые решения.
- `CLAUDE.md` — инструкции для Claude Code (entry point, быстрая справка, статус реализации).
- `TECHNICAL_ASSIGNMENT.md` — настоящий документ (базовые требования).

### 9.2 Валидационные скрипты
- `.agent_loop/scripts/validate_cross_references.js` — автоматическая проверка целостности графа ссылок. Проверяет: отсутствие битых ссылок, отсутствие изолированных агентов, top referenced agents. Должен возвращать exit code 0 при чистоте.
- `.agent_loop/scripts/validate_consistency.js` — проверка консистентности системы. Проверяет: полноту Algorithmic template (Role, Contract, Decision Flow, Failure Modes), snake_case именование, структуру директорий, циклические ссылки (warning), safety-before-execution (warning). Должен возвращать exit code 0 при 0 errors.

---

## 10. Критерии приёмки

- [x] Все 248 агентов/файлов реализованы по Algorithmic template.
- [x] 0 заглушек (stub'ов).
- [x] Все 248 агентов/файлов связаны в единый граф ссылок (0 изолированных).
- [x] 0 битых ссылок (после фильтрации документационных целей).
- [x] Трёхконтурная безопасность соблюдена: safety-control → mutual_check → control.
- [x] ReAct цикл декомпозирован на 90 подагентов в 6 фазах с условными переходами (Conditional Edges).
- [x] 12 категорий инструментов (tools_*) реализованы с pipeline-специфичной архитектурой и оптимизаторами.
- [x] Backend Spec Bridge интегрирован в Figma pipeline и MCP gateway.
- [x] Lighthouse hard-gate audit category (`tools_lighthouse/audit`) интегрирован в ReAct cycle и требует 100% по четырём столпам с convergence guard 8 итераций.
- [x] Скрипт валидации проходит без ошибок.
- [x] ARCHITECTURE.md, CLAUDE.md и TECHNICAL_ASSIGNMENT.md отражают текущее состояние системы.
- [x] Скрипт консистентности (`validate_consistency.js`) показывает 0 errors, 0 warnings.
- [x] i18n module (`runtime/i18n/`), analytics/cookie consent module (`runtime/analytics/`), auth/identity module (`runtime/auth/`) и CMS/data queries module (`runtime/cms_queries/`) интегрированы в планирование, исполнение, самокоррекцию и аудит ReAct cycle.
- [x] Accessibility/WCAG 2.1 module (`runtime/accessibility/`) интегрирован в планирование, исполнение, самокоррекцию и аудит ReAct cycle; выполняет детерминированный статический аудит контраста, фокуса, ARIA, клавиатурных ловушек, иерархии заголовков, alt-текста и связок label/input.
- [x] PWA + performance budget module (`runtime/pwa/`) интегрирован в планирование, исполнение, самокоррекцию и аудит ReAct cycle; генерирует manifest, service worker, offline-страницу, srcset/sizes, font-subsetting hints, performance-budget диагностику и патчит `next.config.js`.
- [x] Design token documentation module (`runtime/design_token_docs/`) интегрирован в планирование, исполнение, самокоррекцию и аудит ReAct cycle; генерирует `docs/DESIGN_TOKENS.md`, `docs/design_tokens.docs.json` и опционально `docs/design_tokens.html` из `design_tokens.json` и `component_registry.json`, включая агентов планирования, исполнения, самокоррекции и аудита.
- [x] Health check (`.agent_loop/scripts/health_check.py`) возвращает HEALTHY за < 10 секунд.

---

## 11. Статус реализации

**Статус: ВЫПОЛНЕНО** (2026-07-08)

- 253/253 агента/файла реализовано.
- 0 stubs.
- 0 изолированных агентов.
- 0 битых ссылок (валидатор `validate_cross_references.js` пройден).
- 0 ошибок консистентности (валидатор `validate_consistency.js` пройден: 0 errors, 0 warnings).
- Все агенты следуют Algorithmic template (Role, Contract, Decision Flow, Failure Modes).
- Добавлены `tools_browser/headless_automation` (Playwright), Conditional Edges (PhaseTransitionManager), `tools_lighthouse/audit` (Lighthouse 100% hard-gate pipeline), Ponytail/Headroom/Memanto/Mem0 protocols, `/goal` fast-critic, Asset Agent и Image Enrichment Agent.
- Добавлены i18n module (`runtime/i18n/`) с агентами планирования, исполнения, самокоррекции и аудита; analytics/cookie consent module (`runtime/analytics/`) с поддержкой GA4, Яндекс.Метрики, Plausible, PostHog, Mixpanel и юрисдикциями GDPR/ePrivacy/152-ФЗ/PIPL/CCPA; auth/identity module (`runtime/auth/`) с обёртками Clerk/Auth0 для SaaS landing pages и personal sites; CMS/data queries module (`runtime/cms_queries/`) с провайдерно-независимым слоем данных Next.js App Router для динамических секций `blog`/`portfolio`/`cases`; accessibility/WCAG 2.1 module (`runtime/accessibility/`) с детерминированным статическим аудитом контраста, фокуса, ARIA, клавиатурных ловушек, иерархии заголовков, alt-текста и label/input; PWA + performance budget module (`runtime/pwa/`) с генерацией manifest, service worker, offline-страницы, srcset/sizes, font-subsetting hints, performance-budget диагностикой и патчем `next.config.js`; и design token documentation module (`runtime/design_token_docs/`) с генерацией `docs/DESIGN_TOKENS.md`, `docs/design_tokens.docs.json` и опционально `docs/design_tokens.html` из `design_tokens.json` и `component_registry.json`, включая агентов планирования, исполнения, самокоррекции и аудита.
- Исправлены core-тесты i18n/analytics/accessibility/pwa/design-token-docs: `DecisionFlow` предоставляет `.steps`, engine записывают относительные пути, ключи i18n без хеш-суффиксов, агенты явно упоминают `default-deny` и `CSP`.
- CI `.github/workflows/ci.yml` запускает tier-ы pytest: `core`, `mcp` и `tests/integration/`; figma-tier исключён из обязательного CI, так как требует `FIGMA_TOKEN`/`FIGMA_URL`. Также CI запускает `ruff check`, `black --check`, `mypy`, и `pytest --cov` с порогом покрытия 60% (настраивается в `pyproject.toml`).
- Добавлены `pyproject.toml` и `.pre-commit-config.yaml` с ruff, black, mypy и базовыми хуками.
- Архитектурная документация актуальна.
- Валидационные скрипты созданы и проверены.
