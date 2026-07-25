---
name: anti-slop
description: Use whenever the user asks Claude Code to generate, design, or redesign a website, landing page, web app, or design system, especially when the request is vague like "make a beautiful site", "сделай красивый сайт", "redesign my landing page", "build a SaaS landing page", or "make it look premium". Prevents AI-slop by enforcing a visual direction, banning default fonts (Inter/Roboto/Arial/Space Grotesk), generic 3-card layouts, gradient blobs, and centered-hero-single-button patterns. Selects one of three Futura AI stacks and routes the build through the runtime premium-design anti-slop hard gate.
---

# 🛡 anti-slop

> Автопилот против AI-slop. Срабатывает, когда ты просишь сделать сайт, лендинг,
> веб-приложение или дизайн-систему — особенно если просьба размыта: «сделай красивый
> сайт», «передизайнь лендинг», «premium look».
>
> Источник методологии: гайд Futura AI «AI-дизайн без слопа», июль 2026.
> Автор: Эдуард Гришин, futuraai.ru.

AI-модели обучены на медиане интернета. Без явного визуального направления они
возвращают один и тот же шаблон:

- один hero на весь экран + кнопка по центру
- градиентный blob слева
- Inter / Roboto / Arial / Space Grotesk
- три одинаковые карточки с иконкой сверху
- серый текст на белом
- тень `0 4px 6px` на всём
- анимации `width`/`height` вместо `transform`/`opacity`

Этот skill заставляет Claude Code выбрать направление **до** первой строки кода и
валидирует результат через deterministic anti-slop hard gate.

---

## Когда срабатывать

Активируй на запросы генерации/редизайна:

- «сделай лендинг / сайт / страницу»
- «передизайнь мой сайт»
- «хочу красивый сайт для SaaS / продукта / портфолио»
- «make a landing page», "redesign my site", "build a premium website"
- «сгенерируй дизайн-систему без слопа»
- **`anti-slop:`** — явный вызов

**НЕ срабатывай:**

- тривиальные правки одного CSS-свойства
- «запусти тесты», «сделай коммит», «исправь баг»
- запросы, которые не касаются дизайна/вёрстки

---

## 🧠 ГЛАВНАЯ ТАБЛИЦА: пользователь → стек

Сопоставь запрос с одним из трёх стеков Futura AI. Стек выбирается **до** генерации.

| Профиль пользователя | Стек | Ключевые инструменты |
|---|---|---|
| Соло-разработчик, нет времени на ручную дизайн-систему | **Stack 1 — Solo Frontend** | Anthropic Frontend Design Skill (базовая гигиена) + Impeccable (audit/polish) + Motion (анимации) + Refactoring UI |
| Команда на Claude Pro/Max/Team/Enterprise, есть дизайн-система в GitHub | **Stack 2 — Team Claude** | Claude Design + /design-sync + Brand compliance + Impeccable (PR review) + Transitions.dev |
| OSS / privacy-first / NDA, нельзя класть дизайн-систему в чужое облако | **Stack 3 — OSS Privacy** | Open Design (nexio) + Taste Skill (VARIANCE/MOTION/DENSITY) + ux-ui-agent-skills (DTCG + WCAG 2.2), BYOK |

Если пользователь не подходит явно ни под один профиль — задай **один** уточняющий вопрос.

---

## 🛡 ГАРДЫ

### Гард 1 — Направление до кода

Перед любыми изменениями Claude должен зафиксировать **одно** из направлений:

- `brutalist`
- `editorial`
- `swiss`
- `retro_futuristic`
- `glassmorphism`
- `bento`
- `minimal_tech`

**«Clean minimal» не является направлением.** Если пользователь сказал «clean minimal» — уточни: «Это скорее Swiss, Editorial или Minimal tech?»

### Гард 2 — Banned-паттерны — hard gate

Любой из следующих паттернов в `DESIGN.md` или `design_tokens.json` блокирует handoff к code agents:

1. **Шрифты:** Inter, Roboto, Arial, Space Grotesk как primary typeface.
2. **Один centered hero + одна кнопка по центру.**
3. **Градиентный blob слева/сверху без функции.**
4. **Три одинаковые карточки с равным padding и иконкой сверху.**
5. **Серый текст на белом (#666666–#999999 на #ffffff).**
6. **Generic shadows:** `0 4px 6px`, `0 8px …`, `shadow-sm/md/lg`.
7. **Анимации `width`/`height`/`top`/`left`/`margin`/`padding`.**
8. **Mass fade-in on scroll без stagger/transform.**

При fail — вернуться к планированию с concrete refinement action.

### Гард 3 — Тривиальность

- Если запрос — одна правка существующего файла, обойтись без полного premium-design pipeline.
- Если запрос — новый сайт/редизайн — запускать anti-slop pipeline.

### Гард 4 — Человек остаётся в контуре на необратимом

Deploy, publish, `git push --force`, production secrets, bulk emails, оплата — только вручную.

---

## 📋 АЛГОРИТМ

### Шаг 1 — Определить профиль / стек

По таблице выше выбери Stack 1, 2 или 3. Если неоднозначно — задай один вопрос:

> «Ты один работаешь, в команде с дизайн-системой, или нужен local-first/privacy-first вариант?»

### Шаг 2 — Зафиксировать направление

Спроси или предложи направление. Записать в `DESIGN.md`:

```markdown
## Direction
{direction}

## Stack
{stack_1|stack_2|stack_3}
```

### Шаг 3 — Сгенерировать DESIGN.md + design_tokens.json

Использовать `runtime/premium_design/PremiumDesignEngine` или вызвать соответствующего planning агента:

- `premium_design_analyst.md` — выбор направления
- `premium_design_system_generator.md` — генерация DESIGN.md + design_tokens.json
- `dtcg_engine.py` — DTCG tokens с variance/density/motion knobs

### Шаг 4 — Anti-slop hard gate

Запустить `anti_slop_validator.md` / `PremiumDesignEngine._run_anti_slop()`.

- `pass` → разрешить handoff к `project_developer.md` / code generation.
- `fail` → вернуться к планированию с refinement actions; не генерировать код.

### Шаг 5 — Verify before handoff

- Lighthouse hard gate (если применимо).
- `detect_slop_tokens` повторно.
- Визуальная проверка, что не появился banned pattern в сгенерированном коде.

---

## 🪤 ГРАБЛИ

| Симптом | Что делать |
|---|---|
| Пользователь говорит «сделай как лучше» | Направление обязательно. Предложить 2–3 варианта и зафиксировать выбор. |
| Claude хочет начать код до выбора направления | Стоп. Вернуться к Шагу 2. |
| Anti-slop gate fail | Не игнорировать. Вернуться к `premium_design_system_generator.md` с refinement action. |
| Пользователь настаивает на Inter / 3 карточках / blob | Требовать `human_approval.md` для explicit override и логировать override в audit. |
| Скилл не активировался | Скажи явно: `anti-slop: сделай лендинг для …` |

---

## ✅ Что этот скилл гарантирует

- Не даст Claude сгенерировать медианный AI-slop по умолчанию.
- Вынудит зафиксировать визуальное направление до кода.
- Провалидирует дизайн-систему через deterministic banned-pattern gate.
- Оставит человека в контуре на deploy/publish/необратимых действиях.

---

*Методология: Futura AI «AI-дизайн без слопа», июль 2026.  
Internal reference: [[anti-slop-rule-set]] in memory/wiki/tool/.*
