---
name: moa
description: Mixture of Agents mode: up to 5 advisors answer in structured JSON, then an Opus-level aggregator synthesizes the final response.
metadata:
  type: concept
  status: active
  created: 2026-07-25
  updated: 2026-07-25
---

# MOA (Mixture of Agents)

MOA — это локальный режим, а не бейдж. Один вопрос → ответы от ≤5 советников в строгом JSON + сводный ответ от агрегатора уровня Opus.

## Как работает

1. Пользователь вводит вопрос.
2. `MOAEngine` строит план вызовов.
3. `dry_run()` показывает: список советников, модели, оценку токенов — без API-запросов.
4. После approval запускаются советники параллельно (до `max_advisors=5`).
5. Каждый советник возвращает `AdvisorResult`:
   ```json
   {
     "advisor_id": "advisor_1",
     "model": "claude-sonnet-5",
     "answer": "...",
     "confidence": 0.85,
     "reasoning": "..."
   }
   ```
6. Агрегатор получает массив `AdvisorResult[]` и возвращает `MOAOutput`:
   ```json
   {
     "advisor_outputs": [...],
     "final_summary": "...",
     "dissent": [...],
     "confidence": 0.82
   }
   ```

## Конфликты и битые ответы

- Если советники противоречат, агрегатор должен явно отметить `dissent` с указанием, чьи ответы расходятся.
- Если советник вернул битый JSON, пустой ответ или превысил лимит токенов, его `AdvisorResult` помечается `status="invalid"`, но консилиум продолжает работу.
- Минимум 2 валидных ответа требуется для финального summary. Иначе возвращается ошибка.

## Ограничения

- `max_advisors=5` по умолчанию.
- Только локальные вызовы через `LLMEngine`; никакого распределённого оркестратора.
- `dry_run()` обязателен перед каждым реальным запуском.

## Расположение

- `runtime/engine/moa.py` — `MOAEngine`, `MOAConfig`, `AdvisorResult`, `MOAOutput`.
- `tests/runtime/engine/test_moa.py` — property-based fuzz и сценарии конфликтов.
