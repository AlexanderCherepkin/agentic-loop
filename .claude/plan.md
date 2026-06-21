# Asset Pipeline — план реализации

## Цель
Создать этап Asset Pipeline для Figma-to-Next.js конвейера: скачивание SVG/PNG/шрифтов из Figma, оптимизация, генерация `next/image` и `@font-face`/`next/font/google`.

## Решения пользователя
- Шрифты V1: Google Fonts через `next/font/google`.
- SVG: inline для простых, `next/image` для сложных.
- Оптимизация: graceful fallback если `svgo`/`sharp` не установлены.
- Выходная директория: `public/assets/figma/`.

## Изменения

### 1. Новый модуль `figma-agent-core/asset_pipeline.py`
- `AssetExtractor` — рекурсивно находит ноды `IMAGE`, `VECTOR`, `INSTANCE` с `isAsset`, а также `fills` типа `IMAGE`.
- `AssetDownloader` — через Figma Images API запрашивает URL для PNG/SVG и скачивает в `public/assets/figma/`.
- `AssetOptimizer` — запускает `svgo` (SVG) и `sharp` (PNG) через subprocess; при отсутствии инструментов копирует файл без изменений и логирует warning.
- `FontCollector` — собирает `fontFamily` из текстовых стилей, мапит популярные шрифты на `next/font/google`, генерирует фрагмент для `layout.tsx`.
- `AssetRegistry` — пишет JSON `{imageRef/node_id -> publicPath, fonts: [...], stats}`.
- CLI: `--file`, `--public-dir`, `--registry`, `--format`, `--skip-download`, `--optimize/--no-optimize`.

### 2. Обновить `figma-agent-core/layout_engine.py`
- CLI `--assets asset_registry.json`.
- `_convert_asset`: заменить `src=imageRef` на `src=publicPath` из реестра; сохранять `width`/`height` для next/image.
- `_apply_fills` IMAGE: заменить `background-image: url('imageRef')` на `url('publicPath')`.
- Добавить `data-asset-type="svg"`/`"raster"` для page_composer.

### 3. Обновить `figma-agent-core/page_composer.py`
- `_detect_image_imports`: при наличии растровых ассетов добавлять `import Image from "next/image"`.
- `_node_to_tsx`: для `tag="img"` с `data-asset-type="raster"` генерировать `<Image src=... alt=... width=... height=... />`.
- Для `data-asset-type="svg"` inline: в V1 fallback на `<img>`; если SVG простой (≤500 байт, нет `<script>`/`<foreignObject>`), вставить inline.
- `_detect_font_imports`: расширить маппинг Google Fonts; генерировать `const inter = Inter(...)` и CSS-переменную.
- `_wrap_page` и `compose_layout`: инжектировать `font-sans` класс из next/font в `<body>`.

### 4. Обновить `figma-agent-core/conductor.py`
- `stage_assets` переписать на вызов `asset_pipeline.py`.
- Добавить CLI-аргументы: `--public-dir`, `--assets-registry`, `--skip-assets-download`, `--optimize-assets/--no-optimize-assets`.
- `stage_layout` передаёт `--assets <registry>`.

### 5. Обновить `mcp_servers/figma_server.py`
- `figma_download_assets` вызывает `asset_pipeline.py` с `--public-dir`, `--registry`.
- Обновить описание инструмента.

### 6. Тесты
- `tests/figma/test_asset_pipeline.py`:
  - fixture с IMAGE и VECTOR нодами;
  - unit-тесты discovery, registry generation, Google Fonts mapping, optimizer graceful fallback.
- `tests/figma/test_layout_engine.py`: asset path resolution.
- `tests/figma/test_page_composer.py`: next/image output, inline SVG threshold.
- `tests/mcp/test_figma_server.py`: обновить счётчики/названия инструментов.

### 7. Обновить агентные спецификации
- `.agent_loop/tooll_subagents/planning/figma_design_analyst.md` — добавить `asset_registry` в `design_blueprint` и шаг `figma_download_assets`.
- `.agent_loop/tooll_subagents/planning/design_to_code_planner.md` — включить `public/assets/figma/` и font imports в `generated_code`.
- `.agent_loop/tooll_subagents/planning/tool_plan_selection.md` — `figma_download_assets` в списке.
- `.agent_loop/main_loop.md`, `.agent_loop/ARCHITECTURE.md`, `.agent_loop/TECHNICAL_ASSIGNMENT.md` — актуализировать описание Figma pipeline.

### 8. Memory
- Новый файл `memory/2026-06-21-asset-pipeline.md` + строка в `MEMORY.md`.

## Acceptance criteria
- `conductor.py --only assets` с fixture скачивает/мокает ассеты и пишет `asset_registry.json`.
- `conductor.py --only layout,compose` генерирует `page.tsx` с `next/image` для растра и `layout.tsx` с `next/font/google`.
- `pytest tests/figma tests/mcp` остаётся зелёным.
- Валидаторы: 0 errors.
- Граф обновлён (`graphify update .`).
