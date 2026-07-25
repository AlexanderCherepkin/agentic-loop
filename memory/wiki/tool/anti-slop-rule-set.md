---
name: anti-slop-rule-set
description: Deterministic banned-pattern rule set for premium AI-generated design in Agentic Loop, derived from Futura AI anti-slop methodology.
type: tool
---

# Anti-Slop Rule Set

Это исполняемый реестр banned-паттернов, который использует `runtime/premium_design/` и `anti_slop_validator.md` как hard gate перед генерацией кода. Правила основаны на гайде Futura AI «AI-дизайн без слопа» (июль 2026) и первоисточниках: [[refactoring-ui]], Anthropic Skills, [[awesome-design-md]].

## Почему hard gate, а не рекомендация

Модели обучены на медиане интернета. Просьба «сделай красивый сайт» возвращает медианный шаблон. Hard gate принудительно выбирает визуальное направление **до** первой строки кода.

## Исполняемые правила

### 1. Fonts — запрещённые шрифты как primary

Запрещено использовать первым в стеке:

- Inter, Roboto, Arial, Space Grotesk
- Open Sans, Helvetica, Segoe UI, San Francisco, Myriad Pro, Calibri, Verdana, Century Gothic

Почему: это default-шрифты моделей. Primary typeface должен быть выбран осознанно.

Ссылка: [[premium-design-config]]

### 2. Card Shadows — декоративные тени

Банятся generic shadows:

- `0 4px 6px …`
- `0 8px …px …`
- `0 10px 15px …`
- `0 20px 25px …`
- Tailwind `shadow-sm`, `shadow-md`, `shadow-lg`

Разрешены: distinct elevation shadows для разных слоёв.

### 3. Centered Buttons — центрированная кнопка без иерархии

Бан: `centered CTA`, `centered button`, `single button`, `one button` без `asymmetry`, `split`, `off-center`, `brutalist`.

### 4. Gradient Blobs — бессмысленные градиентные пятна

Бан: `gradient blob`, `blurred gradient`, `blob left`, `gradient orb`, декоративные `radial-gradient(ellipse…)` и `linear-gradient(…deg…)`.

Разрешены: data viz, heatmap, depth map, functional gradient, brand gradient.

### 5. Uniform Padding — равномерный padding

Spacing scale должен содержать ≥3 осознанных ритмических уровня, а не равные 8px-шаги.

### 6. Generic 3-Column — шаблонные три колонки

Любое упоминание `3 column` / `three column` / `3-col` требует `asymmetric`, `disruption`.

### 7. Generic 3-Column Cards — три одинаковые карточки

Бан: `three cards`, `3 cards`, `feature cards` + `equal padding` / `same padding` + `icon top` / `icon above`.

Разрешено: `asymmetric`, `varied`, `different sizes`, `bento`, `disruption`.

### 8. Single Hero Section — один hero на весь экран

Бан: `hero section`, `full viewport`, `full-height hero`, `centered headline` + `centered CTA` / `single button`.

Разрешено: `asymmetric`, `split`, `off-center`, `editorial`, `brutalist`, `grid`.

### 9. Gray on White — плоский серый на белом

Бан: body text `#666666`–`#999999` на `#ffffff`. Нужна semantic palette с warm/cool off-whites и accent-ролями.

### 10. Layout Animations — анимации layout-свойств

Бан в `allowed_properties`: `width`, `height`, `top`, `left`, `right`, `bottom`, `margin`, `padding`.

Разрешены: `transform`, `opacity`, `filter`, `clip-path`.

### 11. Hover Banality — только opacity

Бан hover, который полагается только на `opacity: 0.8`. Нужен `transform`, `color shift` или `underline`.

### 12. Mass Fade-In — массовый fade-in

Бан: `fade in`, `fade-in`, `fade up`, `fade-in-up`, `all sections fade` без `stagger`, `cascade`, `sequential`, `transform`.

## Как это используется в пайплайне

1. `premium_design_analyst.md` выбирает направление до кода.
2. `premium_design_system_generator.md` пишет `DESIGN.md` + `design_tokens.json`.
3. `anti_slop_validator.md` / `PremiumDesignEngine._run_anti_slop()` запускает 18 checks.
4. `fail` → блокировка handoff к `project_developer.md` + concrete refinement actions.
5. `pass` → `anti_slop.verdict=pass` записывается в tokens, pipeline продолжается.

## First Sources

- [[refactoring-ui]] — иерархия, палитра, тени, spacing, type pairing, states.
- Anthropic Skills docs — формат SKILL.md с lazy loading.
- [[awesome-design-md]] — готовые DESIGN.md реальных брендов для механики brief до кода.

## Связанные runtime-модули

- [[premium-design-config]]
- [[premium-design-engine]]
- [[refactoring-ui-rules]]
- [[motion-executor]]
- [[dtcg-engine]]

## Источник методологии

Гайд: Futura AI — «AI-дизайн без слопа», июль 2026. Автор: Эдуард Гришин, futuraai.ru, Telegram @eduardgrishin27.
