export const meta = {
  name: 'content-angles',
  description: 'Генерация контент-идей под тему: несколько независимых углов из разных линз, судейская панель отбирает топ-идеи с обоснованием.',
  phases: [
    { title: 'Идеи', detail: 'углы под тему из разных линз' },
    { title: 'Отбор', detail: 'судейская панель (3 судьи)' },
    { title: 'Финал', detail: 'топ-3 идеи с обоснованием' },
  ],
}

// args = { topic: "AI-агенты для бизнеса", format: "YouTube-ролик" }
// или просто args = "тема"
const input = args || {}
const topic = input.topic || (typeof args === 'string' ? args : '')
const format = input.format || 'YouTube-ролик / Telegram-пост'

if (!topic) {
  log('Передай тему: args = { topic: "...", format: "youtube" }')
  return { error: 'no topic' }
}

// Каждая линза — отдельный угол подачи. По агенту на линзу.
const LENSES = [
  'боль аудитории',
  'неожиданный контрарианский тезис',
  'практический how-to',
  'личная история / кейс',
  'разбор частой ошибки или мифа',
  'тренд / свежий инфоповод',
]

phase('Идеи')
const IDEA = {
  type: 'object',
  properties: {
    title: { type: 'string' },
    hook: { type: 'string', description: 'крючок первых 10 секунд' },
    angle: { type: 'string', description: 'суть угла' },
    why: { type: 'string', description: 'почему зайдёт' },
  },
  required: ['title', 'hook', 'angle'],
}
const ideas = await parallel(LENSES.map((lens) => () =>
  agent(
    `# Роль
Ты — сценарист и контент-стратег с чутьём на вирусные форматы.

# Контекст
Тема: «${topic}». Формат: ${format}. Твоя линза подачи: «${lens}».

# Задача
Придумай 1 сильную идею именно через свою линзу:
1. Цепляющий заголовок (кликабельный, но без кликбейта-обмана).
2. Хук первых 10 секунд — что заставит не пролистнуть.
3. Суть угла — о чём контент и какая в нём ценность.
4. Почему зайдёт этой аудитории.

# Ограничения
- Идея должна быть конкретной, а не общей («поговорим про AI» — плохо).
- Не выходи из своей линзы — это гарантирует разнообразие между агентами.
- Без воды и штампов.

# Формат
Верни строго по JSON-схеме (title, hook, angle, why).`,
    { label: `idea:${lens}`.slice(0, 40), phase: 'Идеи', model: 'sonnet', schema: IDEA }
  )
)).then((r) => r.filter(Boolean))

if (!ideas.length) {
  log('Не удалось сгенерировать идеи. Попробуй уточнить тему или формат.')
  return { error: 'no ideas generated' }
}

// ФАЗА 2 — судейская панель: 3 независимых судьи оценивают все идеи.
phase('Отбор')
const SCORE = {
  type: 'object',
  properties: {
    scores: {
      type: 'array',
      items: {
        type: 'object',
        properties: {
          title: { type: 'string' },
          hookScore: { type: 'number' },
          noveltyScore: { type: 'number' },
          fitScore: { type: 'number' },
        },
        required: ['title', 'hookScore', 'noveltyScore', 'fitScore'],
      },
    },
  },
  required: ['scores'],
}
const verdicts = await parallel([0, 1, 2].map((i) => () =>
  agent(
    `# Роль
Ты — строгий контент-редактор и стратег ${format}.

# Контекст
Список идей-кандидатов, JSON:
${JSON.stringify(ideas)}

# Задача
Оцени КАЖДУЮ идею по шкале 0–10 по трём критериям:
- hookScore — сила хука (зацепит ли в первые секунды).
- noveltyScore — новизна (не заезжено ли).
- fitScore — попадание в формат «${format}» и аудиторию.

# Ограничения
- Оценивай честно и независимо, без поблажек.
- Верни оценку для каждой идеи из списка (по полю title).

# Формат
Верни строго по JSON-схеме (массив scores).`,
    { label: `judge:${i}`, phase: 'Отбор', model: 'sonnet', schema: SCORE }
  )
)).then((r) => r.filter(Boolean))

if (!verdicts.length) {
  log('Судьи не вернули оценки. Возвращаю сырые идеи без ранжирования.')
  return { topic, format, ideas }
}

// ФАЗА 3 — финал. Умная модель opus только на финал.
phase('Финал')
const report = await agent(
  `# Роль
Ты — главный по контенту, который принимает финальное решение.

# Контекст
Идеи, JSON:
${JSON.stringify(ideas)}

Оценки независимых судей (${verdicts.length} шт.), JSON:
${JSON.stringify(verdicts)}

# Задача
1. Посчитай средний балл каждой идеи по трём критериям и судьям.
2. Выбери топ-3.
3. По каждой из топ-3 дай: заголовок, хук, краткий план раскрытия (3–5 пунктов), почему выбрана (со ссылкой на оценки).

# Ограничения
- Решение — на основе оценок судей, без вкусовщины.
- План раскрытия — конкретный и снимаемый/пишущийся.

# Формат
Чистый Markdown на русском.`,
  { label: 'final', phase: 'Финал', model: 'opus' }
)

return report
