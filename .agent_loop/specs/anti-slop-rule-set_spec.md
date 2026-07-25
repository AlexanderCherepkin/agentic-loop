# SPEC — AI-Дизайн без слопа: расширение anti-slop runtime

## Status

Approved and implemented. Verification passed: 39/39 premium-design tests green, cross-references clean, health check healthy, core pytest 736 passed.

## Goal

Усилить deterministic anti-slop layer в агентботе так, чтобы код и дизайн-системы, генерируемые через `runtime/premium_design/`, жёстко валидировались против восемнадцати banned-паттернов, зафиксированных в гайде Futura AI (июль 2026). Результат — не совет, а hard gate: если артефакт не проходит проверку, handoff к code-generation агентам блокируется.

## Scope

### Входит

1. Расширение `DEFAULT_ANTI_SLOP_RULES` в `runtime/premium_design/config.py` восемью новыми/усиленными детекторами.
2. Реализация логики проверок в `PremiumDesignEngine._run_anti_slop` (`runtime/premium_design/engine.py`).
3. Синхронизация `anti_slop_validator.md` в `tooll_subagents/self_correction/` с новыми правилами.
4. Обновление тестов в `tests/runtime/test_premium_design_engine.py` и `tests/runtime/test_premium_design_dtcg.py`.
5. Обновление `memory/wiki/` — страница `tool/anti-slop-rule-set.md` с картой banned-паттернов.

### Не входит

- Интеграция с внешними skills (Impeccable, Taste Skill, Anthropic Frontend Design) как внешними зависимостями.
- Создание новых MCP-серверов под каждый из 15 инструментов.
- Materialization starter presets под три стека.
- Автоматический веб-скрапинг источников вкуса (recent.design, Refero Styles).
- Правка оплаченных/closed-source материалов (Refactoring UI, 21st.dev, Claude Design).

## Key Decisions

1. **Не импортируем чужие skills.** Вместо этого переносим их **rule-sets** в наш Python runtime как deterministic checks. Это избавляет от зависимостей, vendor lock-in и лицензионных рисков.
2. **Hard gate, не recommendation.** Правила fail-fast. `anti_slop_validator.md` блокирует `next_phase=execution` при любом `fail`.
3. **Regex + структурный анализ, не LLM.** Детекторы работают без LLM-вызова — быстро, воспроизводимо, дешево.
4. **Два уровня проверок:**
   - **Token-level:** `detect_slop_tokens()` для `design_tokens.json`.
   - **Design-level:** `_run_anti_slop()` для `DESIGN.md` + tokens.
5. **Motion rules отдельно.** Проверка compositor-friendly motion уже частично реализована в `motion_executor.py`; в этой итерации усиливаем только правила в `config.py` и `engine.py`, не создаём новый motion engine.
6. **Старые правила не удаляем.** Добавляем 8 новых/усиленных детекторов к существующим 10.

## Banned Patterns — Extended Rule Set

### Rule 1 — `single_hero_section`

**Проблема:** первая секция — один hero на весь viewport, центрированный заголовок и одна кнопка по центру. Медиана медиан.

**Детекция:**
- В `DESIGN.md` найдены одновременно:
  - фразы: `hero section`, `full viewport`, `full-height hero`, `centered headline`, `centered heading`, `hero title centered`
  - И фраза: `centered CTA`, `centered button`, `single button`, `one button`
- И отсутствуют маркеры иерархии/асимметрии: `asymmetric`, `split`, `off-center`, `left-aligned`, `editorial`, `brutalist`, `grid`

**Реакция:** `fail`, действие — «Add asymmetry, split layout, or off-center headline; single centered hero + one button is banned unless explicitly justified.»

### Rule 2 — `generic_3col_cards`

**Проблема:** три одинаковые карточки с равным padding и одной иконкой сверху.

**Детекция:**
- В `DESIGN.md` найдены одновременно:
  - `three cards`, `3 cards`, `three-column cards`, `3 columns of cards`, `feature cards`
  - `equal padding`, `same padding`, `uniform padding`
  - `icon top`, `icon above`, `icon on top`
- И отсутствуют: `asymmetric`, `varied`, `different sizes`, `bento`, `disruption`

**Реакция:** `fail`, действие — «Break the 3-card symmetry: vary card sizes, use bento grid, or remove icons-as-decorations.»

### Rule 3 — `gradient_blobs` (усиление)

**Проблема:** градиентный blob слева или сверху как декоративный фон.

**Детекция:**
- Текущие фразы: `gradient blob`, `gradient shape`, `blurred gradient`.
- Добавить регулярки для CSS/токенов:
  - `radial-gradient\(.*ellipse.*\)`
  - `linear-gradient\(.*deg.*\)` внутри `background`/`backgroundImage`
  - фразы: `blob left`, `blob top`, `gradient blob left`, `gradient blob top`, `blurred orb`, `gradient orb`
- Allowed if: `data viz`, `heatmap`, `depth map`, `functional gradient`, `brand gradient`

**Реакция:** `fail`, действие — «Remove decorative gradient blob or justify it as functional (data viz, depth, brand gradient).»

### Rule 4 — `banned_fonts` (уже частично есть)

**Проблема:** Inter, Roboto, Arial, Space Grotesk в продакшен-стеке.

**Детекция:**
- В `DEFAULT_FORBIDDEN_FONTS` уже есть Inter, Roboto, Arial, Space Grotesk. Усилить:
  - Проверять не только `tokens["fonts"]` и `tokens["fontFamily"]`, но и `DESIGN.md` секцию Typography.
  - Whole-word match с учётом fallback-стеков.
  - Запретить, если шрифт стоит **первым** в стеке (primary), а не fallback.

**Реакция:** `fail`, действие — «Replace banned default font X with an allowed premium font.»

### Rule 5 — `generic_shadows` (усиление)

**Проблема:** тень с радиусом 8px на всех элементах; generic Tailwind shadows.

**Детекция:**
- Регулярки на `box-shadow` / `shadow`:
  - `0\s+4px\s+6px`
  - `0\s+8px\s+.*px` (radius 8)
  - `0\s+10px\s+15px`
  - `0\s+20px\s+25px`
  - `shadow-sm`, `shadow-md`, `shadow-lg` (Tailwind generic)
- Allowed: разные тени для разных elevation-слоёв (`elevation-1`, `elevation-2`, `card-elevated`)

**Реакция:** `fail`, действие — «Use distinct elevation shadows; generic 8px/card shadow is banned.»

### Rule 6 — `unfriendly_animations`

**Проблема:** анимации `width`/`height`/`top`/`left`/`margin`/`padding` вместо compositor-friendly `transform`/`opacity`/`filter`/`clip-path`.

**Детекция:**
- В `tokens["motion"]["allowed_properties"]` запрещённые свойства.
- В `DESIGN.md` фразы: `animate width`, `animate height`, `width transition`, `height transition`, `top transition`, `margin animation`.
- Allowed: `transform`, `opacity`, `filter`, `clip-path`, `background-color`, `color`

**Реакция:** `fail`, действие — «Switch motion to transform/opacity/filter/clip-path only.»

### Rule 7 — `gray_on_white` (уже частично есть)

**Проблема:** серый текст на белом вместо реальной палитры с semantic accents.

**Детекция:**
- Уже есть в `config.py` и `refactoring_ui_rules.py`. Усилить:
  - Добавить `#888888`, `#999999` в flat gray band.
  - Проверять `tokens["colors"]["background"]["base"]` / `surface` == `#FFFFFF` одновременно с `text`/`muted` в flat gray.

**Реакция:** `fail`, действие — «Shift from flat gray-on-white to a semantic palette with warm/cool off-whites and accent roles.»

### Rule 8 — `mass_fade_in` (уже есть)

**Проблема:** массовый fade-in on scroll без stagger/transform.

**Детекция:**
- Уже есть. Дополнительно ловить: `fade in`, `fade-in`, `fade up`, `fade-in-up`, `all sections fade` без `stagger`, `cascade`, `sequential`.

**Реакция:** `fail`, действие — «Replace blanket fade-in with staggered transform-based motion.»

## Deliverables

1. `runtime/premium_design/config.py` — обновлённый `DEFAULT_ANTI_SLOP_RULES` (18 правил).
2. `runtime/premium_design/engine.py` — реализация 8 новых/усиленных checks в `_run_anti_slop`.
3. `tooll_subagents/self_correction/anti_slop_validator.md` — синхронизированный список checks (18 вместо 10).
4. `tests/runtime/test_premium_design_engine.py` — ≥4 новых теста на новые детекторы.
5. `tests/runtime/test_premium_design_dtcg.py` — ≥2 новых теста на `detect_slop_tokens`.
6. `memory/wiki/tool/anti-slop-rule-set.md` — wiki-страница с картой правил и ссылками.

## Success Criteria

1. Все существующие тесты `tests/runtime/test_premium_design_*.py` проходят.
2. Новые тесты на `single_hero_section`, `generic_3col_cards`, `gradient_blobs`, `generic_shadows`, `unfriendly_animations`, `gray_on_white` проходят.
3. `PremiumDesignEngine` возвращает `status=fail` с конкретным `refinement_action` при любом banned pattern.
4. `anti_slop_validator.md` отражает все 18 checks.
5. Wiki-страница создана и проходит `wiki lint`.
6. Кросс-ссылочная целостность не нарушена (`validate_cross_references.js` без ошибок).

## Verification Plan

### Unit tests

```python
def test_engine_fails_single_hero_section(tmp_path): ...
def test_engine_fails_generic_3col_cards(tmp_path): ...
def test_engine_fails_gradient_blob_in_tokens(tmp_path): ...
def test_engine_fails_generic_shadow_radius_8(tmp_path): ...
def test_detect_slop_flags_unfriendly_animation(): ...
```

### Integration check

- Сгенерировать токены с banned pattern → `status=fail`.
- Сгенерировать токены без banned pattern → `status=pass`, `anti_slop.verdict=pass` записан в JSON.

### Regression check

- `pytest tests/runtime/test_premium_design_engine.py tests/runtime/test_premium_design_dtcg.py`
- `node .agent_loop/scripts/validate_cross_references.js`
- `python .agent_loop/scripts/health_check.py --json`

## Human Zones

- Утверждение этой SPEC.md.
- Проверка, что добавленные шрифты/палитры не нарушают существующие клиентские проекты (если таковые используют `PremiumDesignConfig`).
- Деплой/merge решения — только после green tests.

## Assumptions

- Мы работаем с публичными описаниями banned-паттернов из гайда; доступа к внутреннему коду Impeccable/Taste Skill нет.
- Правила применяются только к premium-design pipeline (`design_to_code_planner.md` route).
- Обычные (не premium) генерации не затрагиваются.
- Все изменения backwards-compatible: старые `DEFAULT_ANTI_SLOP_RULES` не удаляются, только дополняются.

## Approval Request

Спека готова. Если всё ок — ответь **«да»**, **«ok»**, **«согласен»**, **«продолжай»** или **«+».  
Если нужно изменить — скажи, что именно.
