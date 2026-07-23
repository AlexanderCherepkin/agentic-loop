export const meta = {
  name: 'data-analytics',
  description: 'Аналитика массива записей (отзывы, заявки, строки таблицы): размечает данные кусками веером и собирает сводку — темы, тональность, инсайты, цитаты.',
  phases: [
    { title: 'Разметка', detail: 'агент на каждый кусок данных' },
    { title: 'Сводка', detail: 'темы, тональность, инсайты' },
  ],
}

// КАК ПЕРЕДАТЬ ДАННЫЕ:
//   args = { goal: "выдели боли клиентов", items: ["отзыв 1", "отзыв 2", ...] }
//   или просто args = ["строка1", "строка2", ...]
const input = args || {}
const goal = input.goal || 'выдели главные темы, тональность и инсайты'
let items = Array.isArray(input.items) ? input.items : (Array.isArray(args) ? args : [])

if (!items.length) {
  log('Передай данные: args = { goal: "...", items: ["запись1","запись2",...] }')
  return { error: 'no items' }
}

// Нормализуем к строкам, чтобы JSON.stringify не ломался на объектах.
items = items.map((x) => (typeof x === 'string' ? x.trim() : JSON.stringify(x))).filter(Boolean)

// Бьём на куски по 20 записей. Не больше 40 кусков — встроенный ограничитель расхода.
const CHUNK = 20
const MAX_CHUNKS = 40
const chunks = []
for (let i = 0; i < items.length; i += CHUNK) chunks.push(items.slice(i, i + CHUNK))
if (chunks.length > MAX_CHUNKS) {
  log(`Данных много: беру первые ${MAX_CHUNKS * CHUNK} записей из ${items.length}.`)
  chunks.length = MAX_CHUNKS
}

const SUM = {
  type: 'object',
  properties: {
    themes: { type: 'array', items: { type: 'string' } },
    sentiment: { type: 'string', description: 'общая тональность куска' },
    quotes: { type: 'array', items: { type: 'string' } },
  },
  required: ['themes', 'sentiment'],
}

// ФАЗА 1 — разметка веером. Дешёвая модель haiku: это рутинный разбор.
phase('Разметка')
const partial = await parallel(chunks.map((ch, idx) => () =>
  agent(
    `# Роль
Ты — data-аналитик, который размечает качественные данные.

# Контекст
Цель анализа: ${goal}.
Кусок данных #${idx + 1} (массив записей), JSON:
${JSON.stringify(ch)}

# Задача
1. Выдели повторяющиеся темы в этом куске.
2. Определи общую тональность (позитив / нейтрал / негатив / смешанная).
3. Подбери 1–2 показательные дословные цитаты, иллюстрирующие главные темы.

# Ограничения
- Работай только с данными из этого куска, не обобщай на весь датасет.
- Цитаты — дословные, без перефразирования и без выдумывания.

# Формат
Верни строго по JSON-схеме (themes, sentiment, quotes).`,
    { label: `chunk:${idx + 1}`, phase: 'Разметка', model: 'haiku', schema: SUM }
  )
)).then((r) => r.filter(Boolean))

if (!partial.length) {
  log('Не удалось разметить ни один кусок данных.')
  return { error: 'all chunk agents failed', goal, items_count: items.length }
}

// ФАЗА 2 — общая сводка. Умная модель opus только на финал.
phase('Сводка')
const report = await agent(
  `# Роль
Ты — ведущий аналитик, который собирает частичные разборы в единую картину.

# Контекст
Цель анализа: ${goal}.
Частичные сводки по ${partial.length} кускам данных, JSON:
${JSON.stringify(partial, null, 2)}

# Задача
Собери единый отчёт на русском:
1. Топ-темы, отсортированные по частоте упоминаний.
2. Общая тональность по всему массиву.
3. 3–5 ключевых инсайтов (неочевидные выводы, а не пересказ тем).
4. Банк показательных дословных цитат.
5. 3–5 рекомендаций, вытекающих из инсайтов.

# Ограничения
- Опирайся только на данные выше.
- Инсайты должны давать новое понимание, а не дублировать список тем.

# Формат
Чистый Markdown.`,
  { label: 'rollup', phase: 'Сводка', model: 'opus' }
)

return report
