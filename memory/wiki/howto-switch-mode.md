---
name: howto-switch-mode
description: Operational howto for switching model economy modes, checking drift, and resetting snapshots.
metadata:
  type: howto
  status: active
  created: 2026-07-25
  updated: 2026-07-25
---

# Howto: switch model economy mode

## Программно

```python
from runtime.engine.llm_engine import LLMEngine, LLMConfig

engine = LLMEngine(LLMConfig())
engine.mode_manager.set_mode("cheap_background")
engine.mode_manager.override("summary", "google", "gemini-flash-latest")
report = engine.check_drift()
```

## Через конфиг

Положи overrides в `~/.hermes/config.yaml`:

```yaml
model_economy:
  default_mode: premium_final
  modes:
    default:
      main:
        provider: anthropic
        model: claude-opus-4-8
```

## Снапшот

```python
engine.mode_manager.persist_snapshot()  # .agent_loop/state/model_economy_snapshot.json
engine.mode_manager.load_snapshot()
```

## Дрейф

`engine.check_drift()` сравнивает текущие эффективные настройки с:
- шаблоном активного режима;
- последним сохранённым снапшотом.

Критический дрейф можно поднять ошибкой: `engine.check_drift(critical=True)`.

Подробнее: [[model-economy]].
