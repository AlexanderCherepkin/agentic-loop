export const meta = {
  name: 'audience-insights',
  description: 'Анализ аудитории из кастдевов/комментариев/анкет: боли, возражения, сегменты, цитаты.',
  phases: [
    { title: 'Разметка', detail: 'агент на каждый кусок источников' },
    { title: 'Сводка', detail: 'боли, сегменты, возражения, рекомендации' },
  ],
}

// КАК ПЕРЕДАТЬ ДАННЫЕ:
//   args = { goal: "подготовка оффера для фрилансеров", sources: ["кастдев 1", "комментарий 2", ...] }
//   или просто args = ["источник1", "источник2", ...]
const input = args || {}
const goal = input.goal || 'выдели боли, возражения, сегменты и показательные цитаты аудитории'
let sources = Array.isArray(input.sources) ? input.sources : (Array.isArray(args) ? args : [])

if (!sources.length) {
  log('Передай данные: args = { goal: "...", sources: ["источник1","источник2",...] }')
  return { error: 'no sources' }
}

// Нормализуем к строкам, чтобы JSON.stringify не ломался на объектах.
sources = sources.map((x) => (typeof x === 'string' ? x.trim() : JSON.stringify(x))).filter(Boolean)

// Бьём на куски по 20 записей. Не больше 40 кусков — встроенный ограничитель расхода.
const CHUNK = 20
const MAX_CHUNKS = 40
const chunks = []
for (let i = 0; i < sources.length; i += CHUNK) chunks.push(sources.slice(i, i + CHUNK))
if (chunks.length > MAX_CHUNKS) {
  log(`Данных много: беру первые ${MAX_CHUNKS * CHUNK} записей из ${sources.length}.`)
  chunks.length = MAX_CHUNKS
}

const INSIGHT = {
  type: 'object',
  properties: {
    pains: { type: 'array', items: { type: 'string' }, description: 'конкретные боли из этого куска' },
    objections: { type: 'array', items: { type: 'string' }, description: 'возражения и барьеры' },
    segments: { type: 'array', items: { type: 'string' }, description: 'упомянутые сегменты аудитории' },
    quotes: { type: 'array', items: { type: 'string' }, description: 'дословные цитаты' },
  },
  required: ['pains', 'objections', 'segments'],
}

// ФАЗА 1 — разметка веером. Дешёвая модель haiku: это рутинный разбор.
phase('Разметка')
const partial = await parallel(chunks.map((ch, idx) => () =>
  agent(
    `# Роль
Ты — аналитик аудитории, который размечает качественные источники.

# Контекст
Цель анализа: ${goal}.
Кусок источников #${idx + 1} (кастдевы, комментарии, строки анкет), JSON:
${JSON.stringify(ch)}

# Задача
1. Выдели конкретные боли, которые озвучивают люди в этом куске.
2. Запиши возражения и барьеры (почему не купили / не сделали / засомневались).
3. Отметь упомянутые сегменты аудитории (роли, ситуации, потребности).
4. Подбери 1–2 показательные дословные цитаты.

# Ограничения
- Работай только с данными из этого куска, не обобщай на весь датасет.
- Боли и возражения — конкретные, не абстрактные.
- Цитаты — дословные, без перефразирования и без выдумывания.

# Формат
Верни строго по JSON-схеме (pains, objections, segments, quotes).`,
    { label: `chunk:${idx + 1}`, phase: 'Разметка', model: 'haiku', schema: INSIGHT }
  )
)).then((r) => r.filter(Boolean))

if (!partial.length) {
  log('Не удалось разметить ни один кусок источников.')
  return { error: 'all chunk agents failed', goal, sources_count: sources.length }
}

// ФАЗА 2 — общая сводка. Умная модель opus только на финал.
phase('Сводка')
const report = await agent(
  `# Роль
Ты — ведущий аналитик аудитории, который собирает частичные разборы в единую картину.

# Контекст
Цель анализа: ${goal}.
Частичные сводки по ${partial.length} кускам источников, JSON:
${JSON.stringify(partial, null, 2)}

# Задача
Собери единый отчёт на русском:
1. Топ-сегменты аудитории с коротким описанием каждого.
2. Топ-болей, отсортированных по частоте / силе.
3. Топ-возражений и барьеров.
4. Банк показательных дословных цитат.
5. 3–5 рекомендаций по продукту / офферу / коммуникации, вытекающих из инсайтов.

# Ограничения
- Опирайся только на данные выше.
- Рекомендации должны быть actionable и вытекать из реальных болей / возражений.

# Формат
Чистый Markdown.`,
  { label: 'rollup', phase: 'Сводка', model: 'opus' }
)

return report
