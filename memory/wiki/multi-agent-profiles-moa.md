---
name: multi-agent-profiles-moa
description: Bundle of three local CLI/TUI mechanics: fork subagents, per-profile models, and Mixture of Agents (MOA).
metadata:
  type: concept
  status: active
  created: 2026-07-25
  updated: 2026-07-25
---

# Multi-Agent, Profiles и MOA

Это три локальные CLI/TUI-механики, работающие внутри одного терминального процесса Agentic Loop.

- [[fork-subagents]] — фоновый рой помощников с панелью статусов.
- [[profiles]] — своя модель и системный промпт под каждую роль/профессию.
- [[moa]] — консилиум моделей-советников + агрегатор (Opus-уровня).

## Общие ограничения

- Работают только локально: никакого MCP или веб-дашборда.
- Не хранятся в git: профили живут в `~/.hermes/profiles/`, снапшоты форка — в памяти сессии.
- Все три интегрированы поверх [[model-economy]]: не ломают `ModeManager`, `DriftDetector` и auxiliary slots.

## Когда использовать

- Fork — параллельная обработка независимых подзадач.
- Profiles — ролевое переключение: архитектор, ревьюер, копирайтер, тестировщик.
- MOA — сложный вопрос, где нужно услышать несколько точек зрения и свести их в одно решение.
