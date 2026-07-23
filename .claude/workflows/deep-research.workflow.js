export const meta = {
  name: 'deep-research',
  description: 'Глубокий ресёрч темы: раскладывает вопрос на углы, ищет параллельно, состязательно проверяет каждый факт (3 голоса) и собирает отчёт со ссылками.',
  phases: [
    { title: 'Scope', detail: 'разложить вопрос на 3–5 углов' },
    { title: 'Поиск', detail: 'поиск по каждому углу параллельно' },
    { title: 'Проверка', detail: '3 независимых голоса на каждый факт' },
    { title: 'Сведение', detail: 'отчёт со ссылками' },
  ],
}

// КАК ПЕРЕДАТЬ ДАННЫЕ:
//   args = "Куда пойдёт курс рубля к доллару в ближайший квартал?"
//   или args = { question: "..." }
const question = (typeof args === 'string' ? args : (args && args.question)) || ''
if (!question) {
  log('Передай вопрос: args = "твой вопрос"')
  return { error: 'no question' }
}

// ФАЗА 1 — разложить вопрос на углы. Дешёвая модель haiku.
phase('Scope')
const ANGLES = {
  type: 'object',
  properties: { angles: { type: 'array', items: { type: 'string' }, minItems: 3, maxItems: 5 } },
  required: ['angles'],
}
const scope = await agent(
  `# Роль
Ты — research lead, который проектирует план исследования.

# Контекст
Главный вопрос исследования: «${question}».

# Задача
Разложи вопрос на 3–5 разных углов (аспектов), которые в сумме дают полный ответ.

# Ограничения
- Углы не должны дублировать друг друга — каждый про свой пласт (например: данные/статистика, причины, риски, прогнозы, контраргументы).
- Формулируй угол как самостоятельный поисковый запрос, а не общую тему.

# Формат
Верни строго по JSON-схеме (массив angles).`,
  { label: 'scope', phase: 'Scope', model: 'haiku', schema: ANGLES }
)

if (!scope || !Array.isArray(scope.angles) || !scope.angles.length) {
  return { error: 'failed to derive research angles', question }
}

// ФАЗА 2 — поиск веером: по агенту на угол, с реальным web_search.
phase('Поиск')
const CLAIMS = {
  type: 'object',
  properties: {
    claims: {
      type: 'array',
      items: {
        type: 'object',
        properties: { claim: { type: 'string' }, source: { type: 'string' } },
        required: ['claim'],
      },
    },
  },
  required: ['claims'],
}
const found = await parallel(scope.angles.map((a) => () =>
  agent(
    `# Роль
Ты — дотошный ресёрчер, который добывает только проверяемые факты.

# Контекст
Исходный вопрос: «${question}». Твой угол: «${a}».

# Задача
1. Выполни поиск в интернете по углу «${a}» — используй доступный web_search.
2. Извлеки конкретные проверяемые факты (цифры, даты, утверждения).
3. К каждому факту приложи источник (URL).

# Ограничения
- Бери свежие и авторитетные источники (официальные данные, профильные издания, исследования).
- Никаких догадок и общих рассуждений — только факты, которые можно проверить по ссылке.
- Один факт = одна запись. Если источника нет — факт не включай.

# Формат
Верни строго по JSON-схеме (массив claims с полями claim и source).`,
    { label: `search:${a}`.slice(0, 40), phase: 'Поиск', model: 'sonnet', schema: CLAIMS, tools: ['web_search'] }
  )
)).then((r) => r.filter(Boolean).flatMap((x) => x.claims || []))

if (!found.length) {
  return { error: 'no claims found', question, angles: scope.angles }
}

// Жёсткий кап на проверку — иначе тройная проверка размножает агентов.
const MAX_VERIFY = 30
const toVerify = found.slice(0, MAX_VERIFY)
if (found.length > MAX_VERIFY) {
  log(`Найдено ${found.length} фактов; проверяю первые ${MAX_VERIFY}.`)
}

// ФАЗА 3 — состязательная проверка: 3 голоса на факт, нужно ≥2 «за», иначе факт выбрасываем.
phase('Проверка')
const VERDICT = {
  type: 'object',
  properties: { refuted: { type: 'boolean' }, note: { type: 'string' } },
  required: ['refuted'],
}
const verified = await parallel(toVerify.map((f) => () =>
  parallel([0, 1, 2].map((i) => () =>
    agent(
      `# Роль
Ты — скептик-факт-чекер. Твоя работа — попытаться ОПРОВЕРГНУТЬ факт, а не подтвердить.

# Проверяемый факт
«${f.claim}»
Источник: ${f.source || 'не указан'}.

# Задача
Оцени, выдерживает ли факт критику: правдоподобен ли, не устарел ли, не противоречит ли известным данным, надёжен ли источник.

# Ограничение (важно)
Действуй строго: если есть обоснованные сомнения или факт нельзя подтвердить — ставь refuted=true. В note кратко объясни решение.

# Формат
Верни строго по JSON-схеме (refuted, note).`,
      { label: `verify:${i}`, phase: 'Проверка', model: 'sonnet', schema: VERDICT }
    )
  )).then((votes) => {
    const passed = votes.filter(Boolean).filter((v) => !v.refuted).length
    return passed >= 2 ? f : null
  })
)).then((r) => r.filter(Boolean))

// ФАЗА 4 — отчёт. Умная модель opus только на финал.
phase('Сведение')
const report = await agent(
  `# Роль
Ты — аналитик-редактор, который пишет ясный отчёт по проверенным данным.

# Контекст
Вопрос: «${question}».
Подтверждённые факты (прошли тройную проверку), JSON:
${JSON.stringify(verified, null, 2)}

# Задача
Напиши отчёт на русском:
1. Короткий вывод-ответ на вопрос (2–4 предложения) в начале.
2. Разбор по углам/аспектам с опорой на факты.
3. Список источников в конце.

# Ограничения
- Используй только подтверждённые факты выше. Если данных не хватает для уверенного вывода — так и напиши.
- Без воды и общих фраз.

# Формат
Чистый Markdown.`,
  { label: 'synthesize', phase: 'Сведение', model: 'opus' }
)

return report
