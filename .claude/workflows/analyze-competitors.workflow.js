export const meta = {
  name: 'analyze-competitors',
  description: 'Анализ конкурентов: по одному агенту на конкурента, затем сводная таблица с офферами, ценами, сильными/слабыми сторонами и пробелами рынка.',
  phases: [
    { title: 'Разведка', detail: 'по одному агенту на конкурента' },
    { title: 'Сведение', detail: 'сводная таблица + пробелы рынка' },
  ],
}

// args = { niche: "онлайн-курсы по AI", competitors: ["Конкурент A", "https://b.com", "Конкурент C"] }
// или просто args = ["Конкурент A", "Конкурент B"] (нишу спросит из контекста)
const input = args || {}
const niche = input.niche || 'ниша не указана'
const competitors = Array.isArray(input.competitors)
  ? input.competitors
  : (Array.isArray(args) ? args : [])

if (!competitors.length) {
  log('Не передан список конкурентов. Пример: args = { niche: "...", competitors: ["A","https://b.com","C"] }')
  return { error: 'no competitors' }
}

const MAX_COMPETITORS = 10
if (competitors.length > MAX_COMPETITORS) {
  log(`Слишком много конкурентов: ${competitors.length}. Максимум ${MAX_COMPETITORS}.`)
  return { error: 'too many competitors' }
}

const isUrl = (s) => /^https?:\/\//.test(String(s))
const labelName = (c) => {
  if (isUrl(c)) {
    try {
      return new URL(c).hostname.replace(/^www\./, '')
    } catch {
      return c
    }
  }
  return String(c)
}

const CARD = {
  type: 'object',
  properties: {
    name: { type: 'string', description: 'название конкурента или домен' },
    offer: { type: 'string', description: 'что предлагает' },
    pricing: { type: 'string', description: 'цены / тарифы; если не найдены — "не указано"' },
    positioning: { type: 'string', description: 'как себя позиционирует' },
    strengths: { type: 'array', items: { type: 'string' } },
    weaknesses: { type: 'array', items: { type: 'string' } },
  },
  required: ['name', 'offer', 'strengths', 'weaknesses'],
}

// ФАЗА 1 — разведка веером: каждый агент сидит на своём конкуренте, чистое окно.
// Модель sonnet (не самая дорогая) — разведка должна быть дешёвой.
phase('Разведка')
const cards = await parallel(competitors.map((c) => () => {
  const target = String(c)
  const label = `research:${labelName(target)}`.slice(0, 40)
  const sourceHint = isUrl(target)
    ? `Проанализируй сайт ${target} и связанные страницы (тарифы, лендинги, отзывы).`
    : `Найди информацию о компании/продукте «${target}» в нише «${niche}». Используй веб-поиск и сайт, если он известен.`

  return agent(
    `# Роль
Ты — аналитик конкурентной разведки с 10-летним опытом в B2C/инфобизнесе.

# Контекст
Компания работает в нише «${niche}». Цель разбора — понять конкурента «${target}» настолько, чтобы от него отстроиться.

# Задача (по шагам)
1. ${sourceHint}
2. Зафиксируй: что именно предлагает (продукт/услуга), цены и тарифы, как себя позиционирует (для кого, главное обещание).
3. Выдели сильные стороны (за что хвалят, в чём реально хороши) и слабые (на что жалуются, чего не хватает).

# Ограничения
- Только проверяемые факты из источников. Никаких догадок и выдуманных цифр.
- Если данных по полю нет — честно укажи это словами, не подставляй правдоподобное число.
- Где важно — приводи формулировки конкурента дословно (его оффер, обещания).
- Веб-поиск и браузерные инструменты могут быть недоступны. Если они недоступны — верни ошибку, не выдумывай данные.

# Формат
Верни результат строго по заданной JSON-схеме.`,
    { label, phase: 'Разведка', model: 'sonnet', schema: CARD }
  )
})).then((r) => r.filter(Boolean))

if (!cards.length) {
  log('Не удалось получить данные по конкурентам. Проверь доступность веб-инструментов и корректность списка.')
  return { error: 'no research results' }
}

// ФАЗА 2 — сведение: один агент собирает всё в таблицу и ищет дыры.
// Модель opus — самая умная, но включается только на финал.
phase('Сведение')
const report = await agent(
  `# Роль
Ты — продуктовый стратег, который превращает разведданные в план отстройки от конкурентов.

# Контекст
Ниша: «${niche}». Ниже — разбор ${cards.length} конкурентов (JSON):
${JSON.stringify(cards, null, 2)}

# Задача
Собери единый отчёт на русском:
1. Markdown-таблица: Конкурент | Оффер | Цены | Сильные стороны | Слабые стороны.
2. Раздел «Пробелы рынка»: чего нет ни у кого или слабо у всех — и куда можно зайти.
3. 3–5 конкретных рекомендаций по отстройке, каждая привязана к конкретному пробелу из п.2.

# Ограничения
- Опирайся только на данные выше, ничего не додумывай.
- Рекомендации — применимые и конкретные, без общих слов вроде «делать лучше» или «улучшить маркетинг».

# Формат
Чистый Markdown, готовый к вставке в документ.`,
  { label: 'synthesize', phase: 'Сведение', model: 'opus' }
)

return report
