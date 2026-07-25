---
name: model-economy
description: Runtime model economy: named modes, auxiliary slot map, drift detection, and Hermes-separated user overrides.
metadata:
  type: concept
  status: active
  created: 2026-07-25
  updated: 2026-07-25
---

# Model Economy

Контролируемая экономика моделей в Agentic Loop: именованные режимы, карта вспомогательных слотов и детектор дрейфа настроек.

## Компоненты

- `runtime/config/model_economy.yaml` — проектные режимы по умолчанию.
- `runtime/engine/model_economy_config.py` — датаклассы и загрузчик.
- `runtime/engine/mode_manager.py` — переключение режимов в рантайме.
- `runtime/engine/drift_detector.py` — сравнение текущих оверрайдов с шаблоном режима и снапшотом.

## Режимы

- `default` — баланс.
- `cheap_background` — рутина на дешёвых моделях.
- `premium_final` — архитектура и финальный review.
- `fallback` — OpenRouter-роутеры при отказе основных провайдеров.

## Auxiliary slots

- `title`, `vision`, `compression`, `approval`, `web_extract`, `code_review`, `summary`.

Каждый слот может иметь свою модель/провайдера внутри активного режима. См. [[howto-switch-mode]].

## Интеграция

`LLMEngine` использует `ModeManager` для `resolve_model(slot)` и `check_drift()`. Основной путь остаётся на `claude-sonnet-5`.

См. также [[multi-agent-profiles-moa]] для работы с профилями и MOA поверх Model Economy.
