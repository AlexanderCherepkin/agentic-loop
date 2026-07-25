---
name: profiles
description: Per-profile model + system prompt stored in ~/.hermes/profiles/<id>/ with config.yaml and SOUL.md.
metadata:
  type: concept
  status: active
  created: 2026-07-25
  updated: 2026-07-25
---

# Profiles (модель-под-профиль)

Каждая «профессия» или роль в Agentic Loop может иметь свою модель и свой системный промпт. Профили хранятся в `~/.hermes/profiles/<id>/` и не попадают в git.

## Структура профиля

```
~/.hermes/profiles/
  architect/
    config.yaml
    SOUL.md
  code-reviewer/
    config.yaml
    SOUL.md
  copywriter/
    config.yaml
    SOUL.md
```

### config.yaml

```yaml
name: architect
model: claude-opus-4-8
provider: anthropic
mode: premium_final
guardrail_template: |
  You are a senior software architect. Prefer simplicity and explicit contracts.
```

### SOUL.md

Markdown-файл с персоной. Первая непустая строка после frontmatter считается основным системным промптом.

```markdown
---
name: architect
---

You are a senior software architect. Design minimal, reversible systems.
```

## ProfileResolver

- `runtime/engine/profile_resolver.py` — `ProfileResolver` поверх `ModeManager`.
- При вызове `LLMEngine.execute(..., profile_id="architect")` или `raw_chat_completion(..., profile_id="architect")` Resolver:
  1. Читает `config.yaml` и `SOUL.md`.
  2. Переопределяет модель/провайдер, если они заданы.
  3. Добавляет персону как системный префикс.
  4. Не ломает `ModeManager` и `DriftDetector`.

## Порядок применения

1. Базовый системный промпт из AgentSpec.
2. Guardrail из active mode (Model Economy).
3. Guardrail из профиля (если задан).
4. Персона из `SOUL.md`.
5. Пользовательский `extra_context`.

## Fallback

Если `profile_id` не найден в `~/.hermes/profiles/`, `LLMEngine` падает с `KeyError`, а не использует default. Это предотвращает «тихое» выпадение из роли.
