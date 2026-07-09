# План: Закрытие модуля клиентских сайтов (multi-page, Storybook, deploy, preview)

## Цель
Реализовать оставшиеся пробелы для клиентских сайтов, выявленные при валидации предположений:
1. **Multi-page routing** — Next.js App Router, навигация, sitemap, robots.txt.
2. **Storybook integration** — генерация `.stories.tsx` из UI-компонентов.
3. **Deploy execution** — фактический запуск deploy на Vercel/Netlify/generic.
4. **Preview/approval workflow** — dev-сервер, скриншот, QR, фидбек, refinement hints.

## Архитектурные решения
- Каждый модуль оформляем по существующему шаблону: **runtime engine** (`runtime/<module>/engine.py`) + ReAct-агенты (planning → execution → validator → audit).
- Figma-специфичная часть дополняет `figma-agent-core/conductor.py` и `figma-agent-core/page_composer.py`, чтобы пайплайн Figma-to-Code мог сразу генерировать многостраничные сайты, Storybook, деплой и preview.
- Runtime-агенты используют те же `Config`/`Result`/`run()` движки, что `PwaEngine`, `CmsQueriesEngine` и т.д.
- Новые флаги планирования (`needs_multi_page`, `needs_storybook`, `needs_deploy`, `needs_preview`) добавляются в `PLANNING_FLAG_GROUPS` и автоматически подхватываются `PipelineRunner`.
- Agent count: 256 → 272 (+16 агентов: 4 planning, 4 execution, 4 self_correction, 4 observability/audit по одному на модуль).

## Модуль 1 — Multi-page routing

### Runtime engine
- `runtime/multi_page/__init__.py`
- `runtime/multi_page/config.py` — `MultiPageConfig` (target_dir, base_url, pages[], default_locale, generate_sitemap, generate_robots).
- `runtime/multi_page/engine.py` — `MultiPageEngine`:
  - Принимает список страниц (`slug`, `title`, `code`, `metadata`).
  - Пишет `app/[slug]/page.tsx` и `app/page.tsx` для `home`.
  - Генерирует `app/components/Navigation.tsx` на основе pages[] с активным пунктом.
  - Генерирует `app/sitemap.ts` (Next.js Metadata Route) с `alternates`/`priority`/`lastModified`.
  - Генерирует `app/robots.ts` с `allow: "/"` и `sitemap` URL.
  - Возвращает `MultiPageResult` со списком written files.

### ReAct-агенты
- `.agent_loop/tooll_subagents/planning/multi_page_planner.md` — определяет `needs_multi_page`, структуру страниц, slug-маппинг, флаги sitemap/robots.
- `.agent_loop/tooll_subagents/execution/multi_page_runtime_integrator.md` — вызывает `MultiPageEngine.run()` и возвращает `multi_page_report`.
- `.agent_loop/tooll_subagents/self_correction/multi_page_validator.md` — проверяет, что все slug-директории созданы, sitemap содержит все страницы, robots корректен.
- `.agent_loop/tooll_subagents/observability/multi_page_audit_agent.md` — финальный аудит модуля.

### Figma-интеграция
- Расширить `page_composer.py`:
  - `compose_navigation(pages) -> str` — React-навигация.
  - `compose_sitemap_ts(pages, base_url) -> str` — `app/sitemap.ts`.
  - `compose_robots_ts(base_url) -> str` — `app/robots.ts`.
- Добавить в `conductor.py`:
  - Флаг `--multi-page` в CLI и `config["multi_page"]`.
  - `stage_compose` вызывает `page_composer.py --multi-page` и пишет `app/[slug]/page.tsx`.
  - Новый `stage_multi_page` (после compose) генерирует Navigation/Sitemap/Robots.

### Тесты
- `tests/runtime/test_multi_page_engine.py`
- `tests/figma/test_multi_page_composer.py`

## Модуль 2 — Storybook

### Runtime engine
- `runtime/storybook/__init__.py`
- `runtime/storybook/config.py` — `StorybookConfig` (target_dir, components_dirs, output_dir).
- `runtime/storybook/engine.py` — `StorybookEngine`:
  - Сканирует `src/components/ui/*.tsx` и `src/app/components/*.tsx`.
  - Для каждого компонента генерирует `.stories.tsx` с базовым default story и аргументами из `variant_props` (если есть).
  - Обновляет `package.json` — добавляет `@storybook/nextjs`, `storybook`, `build-storybook` script.
  - Пишет `.storybook/main.ts` и `.storybook/preview.ts`.
  - Возвращает `StorybookResult`.

### ReAct-агенты
- `.agent_loop/tooll_subagents/planning/storybook_planner.md` — `needs_storybook`, выбор компонентов, исключение Next.js-only файлов.
- `.agent_loop/tooll_subagents/execution/storybook_runtime_integrator.md` — вызов движка.
- `.agent_loop/tooll_subagents/self_correction/storybook_validator.md` — проверка, что у каждого UI-компонента есть `.stories.tsx` и `storybook` script в package.json.
- `.agent_loop/tooll_subagents/observability/storybook_audit_agent.md`.

### Figma-интеграция
- Новый `figma-agent-core/storybook_generator.py` — CLI-обёртка над `StorybookEngine`.
- `conductor.py` получает stage `storybook` (опциональный, включается `--storybook`).

### Тесты
- `tests/runtime/test_storybook_engine.py`
- `tests/figma/test_storybook_generator.py`

## Модуль 3 — Deploy execution

### Runtime engine
- `runtime/deploy/__init__.py`
- `runtime/deploy/config.py` — `DeployConfig` (target_dir, provider: vercel|netlify|generic, dry_run, env).
- `runtime/deploy/engine.py` — `DeployEngine`:
  - Проверяет наличие `package.json`, `vercel.json`/`netlify.toml`, `deploy.sh`.
  - В `dry_run` режиме возвращает команду без выполнения.
  - В реальном режиме запускает subprocess с таймаутом и возвращает stdout/stderr/deploy URL.
  - Поддерживает Vercel (`npx vercel --prod --yes`), Netlify (`npx netlify deploy --prod --dir=dist`), generic (`pnpm build && echo done`).

### ReAct-агенты
- `.agent_loop/tooll_subagents/planning/deploy_planner.md` — `needs_deploy`, выбор провайдера, dry_run, env-переменные.
- `.agent_loop/tooll_subagents/execution/deploy_runtime_integrator.md` — вызов движка.
- `.agent_loop/tooll_subagents/self_correction/deploy_validator.md` — проверка exit code, наличия URL в stdout, наличия deploy-артефактов.
- `.agent_loop/tooll_subagents/observability/deploy_audit_agent.md`.

### Figma-интеграция
- Новый `figma-agent-core/deploy_executor.py` — CLI-обёртка над `DeployEngine`.
- `conductor.py` получает stage `deploy` после `package_deployment` (опциональный, `--deploy`, dry_run по умолчанию для безопасности).

### Тесты
- `tests/runtime/test_deploy_engine.py`
- `tests/figma/test_deploy_executor.py`

## Модуль 4 — Preview/approval workflow

### Runtime engine
- `runtime/preview/__init__.py`
- `runtime/preview/config.py` — `PreviewConfig` (site_dir, port, output_dir, feedback_file, auto_approve_after_timeout, allowed_domains).
- `runtime/preview/engine.py` — `PreviewEngine`:
  - Обёртывает `figma-agent-core/preview_workflow.py`.
  - Возвращает структурированный `PreviewResult`.

### ReAct-агенты
- `.agent_loop/tooll_subagents/planning/preview_planner.md` — `needs_preview`, viewport, feedback timeout, allowed domains.
- `.agent_loop/tooll_subagents/execution/preview_runtime_integrator.md` — вызов движка.
- `.agent_loop/tooll_subagents/self_correction/preview_validator.md` — проверка, что preview report создан, screenshot на месте, статус approved/rejected/awaiting корректен.
- `.agent_loop/tooll_subagents/observability/preview_audit_agent.md`.

### Figma-интеграция
- Уже есть `preview_workflow.py` и `stage_preview_workflow` в `conductor.py`.
- Дополнить: preview workflow автоматически включается при `--all` и `package_deployment`, если не указано `--no-preview`.

### Тесты
- `tests/runtime/test_preview_engine.py`
- `tests/figma/test_preview_workflow.py` (уже есть, дополнить проверкой status/rejection hints).

## Runtime wiring

### `runtime/engine/agent_invocation_map.py`
- Обновить `.agent_loop/scripts/generate_agent_invocation_map.py`:
  - Добавить `planning_multi_page`, `planning_storybook`, `planning_deploy`, `planning_preview` в `classify()`.
  - Классифицировать агенты по именам: `multi_page_*`, `storybook_*`, `deploy_*`, `preview_*`.
- Добавить флаги в `PLANNING_FLAG_GROUPS`:
  - `needs_multi_page`, `needs_storybook`, `needs_deploy`, `needs_preview`.

### `runtime/engine/pipeline_runner.py`
- В `_execution_agent_enabled` добавить маппинг префиксов → флагам:
  - `"multi_page": "needs_multi_page"`
  - `"storybook": "needs_storybook"`
  - `"deploy": "needs_deploy"`
  - `"preview": "needs_preview"`

### Mock LLM responses
- `runtime/engine/llm_engine.py`:
  - Добавить базовые `passed`/`dry_run` ответы для новых planning/execution/validator агентов.

## Валидация и документация
- `.agent_loop/scripts/validate_runtime_coverage.py`: `EXPECTED_AGENT_COUNT` 256 → 272.
- `.agent_loop/scripts/health_check.py`: `EXPECTED_AGENTS` 256 → 272.
- `.agent_loop/ARCHITECTURE.md` и `.agent_loop/TECHNICAL_ASSIGNMENT.md`:
  - Обновить counts: `tooll_subagents` 100 → 116, total 256 → 272.
  - Добавить runtime engines в таблицу модулей.
- `project_rules.md` — не трогаем без явного одобрения.

## Верификация
1. `python .agent_loop/scripts/generate_agent_invocation_map.py` — 0 unreachable.
2. `python .agent_loop/scripts/validate_runtime_coverage.py` — OK (272 agents).
3. `node .agent_loop/scripts/validate_cross_references.js` — clean.
4. `node .agent_loop/scripts/validate_consistency.js` — 0 warnings.
5. `python .agent_loop/scripts/health_check.py` — HEALTHY.
6. `pytest -m core` — проходит.
7. `graphify update .` — AST-only.
8. Git: commit + push в ветку `finish-increment-check` (Gate 2 уже одобрен ранее).

## Риски и ограничения
- Deploy execution запускает внешние CLI; по умолчанию `dry_run=True`, реальный deploy только при явном `--deploy-live`.
- Preview workflow поднимает dev-сервер; в CI будет использоваться `--preview-workflow-page-url` или пропускаться.
- Storybook требует дополнительных devDependencies; движок обновляет `package.json`, но не запускает `pnpm install`.
