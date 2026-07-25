---
name: fork-subagents
description: Background worker swarm (/fork, /agents) with human approval gate and local terminal status panel.
metadata:
  type: concept
  status: active
  created: 2026-07-25
  updated: 2026-07-25
---

# Fork-субагенты

`/fork <задача>` запускает фоновый рой помощников внутри локального терминального процесса. `/agents` показывает живую панель: кто чем занят, сколько выполнено, какой статус.

## Команды

- `/fork <задача>` — предложить рой. Перед стартом появляется human approval gate.
- `/agents` — показать панель статусов текущих и завершённых воркеров.

## Архитектура

- `runtime/engine/fork_pool.py` — `ForkPool` на `asyncio.gather`.
- `runtime/tui/fork_panel.py` — отрисовка таблицы статусов.
- `runtime/tui.py` — обработка команд `/fork` и `/agents`.

## Жёсткие ограничения

- `MAX_FORK_WORKERS=8` — больше воркеров не запускается, даже если задача просит.
- Approval gate: без explicit `да/yes/ok` рой не стартует.
- Каждый воркер — изолированная `asyncio.Task`; ошибка одного не ломает остальных.
- Результаты хранятся в памяти сессии + опциональный JSON-дамп в `.agent_loop/state/fork/`. Без перманентной базы.

## Почему не Agent/Workflow инструмент

Для предсказуемости и отладки выбран `asyncio.gather`, а не внешний оркестратор. Это даёт прямой контроль над concurrency, отменой задач и потреблением памяти.

## Политика безопасности

- Фоновые задачи не делают `git push`, deploy, `rm -rf`, не открывают браузер.
- Если воркер пытается запустить инструмент из human zone, approval gate должен переспросить пользователя.
