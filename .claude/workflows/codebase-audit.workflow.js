export const meta = {
  name: 'codebase-audit',
  description: 'Аудит кодовой базы: по агенту на файл/модуль ищет проблемы, второй слой агентов состязательно их проверяет, в отчёт попадает только подтверждённое.',
  phases: [
    { title: 'Поиск', detail: 'агент на файл/модуль' },
    { title: 'Проверка', detail: 'состязательная верификация находок' },
    { title: 'Отчёт', detail: 'только подтверждённые проблемы' },
  ],
}

// args = { paths: ["src/api/", "src/auth.ts", "src/db.ts"], focus: "security" }
// или просто args = ["src/a.ts", "src/b.ts"]
const input = args || {}
const focus = input.focus || 'баги, риски безопасности, очевидные проблемы'
let paths = Array.isArray(input.paths) ? input.paths : (Array.isArray(args) ? args : [])

if (!paths.length) {
  log('Передай файлы/папки: args = { paths: ["src/a.ts","src/api/"], focus: "security" }')
  return { error: 'no paths' }
}

const MAX = 80
if (paths.length > MAX) {
  log(`Целей много: беру первые ${MAX} из ${paths.length}.`)
  paths = paths.slice(0, MAX)
}

const cleanLabel = (prefix, s) => {
  const base = String(s).replace(/[\s\/\\:]/g, '_')
  const full = `${prefix}:${base}`
  return full.length > 40 ? full.slice(0, 40) : full
}

const FIND = {
  type: 'object',
  properties: {
    findings: {
      type: 'array',
      items: {
        type: 'object',
        properties: {
          title: { type: 'string' },
          where: { type: 'string', description: 'файл:строка' },
          severity: { type: 'string', description: 'critical / high / medium / low' },
          detail: { type: 'string' },
        },
        required: ['title', 'where'],
      },
    },
  },
  required: ['findings'],
}
const VERD = {
  type: 'object',
  properties: { real: { type: 'boolean' }, reason: { type: 'string' } },
  required: ['real'],
}

// pipeline: каждый путь сразу идёт «поиск → проверка», без барьера между фазами.
// Поиск — sonnet, проверка — sonnet (состязательно). Быстрый файл не ждёт медленный.
const results = await pipeline(
  paths,
  (p) => agent(
    `# Роль
Ты — senior-инженер и аудитор безопасности кода.

# Контекст
Файл/папка для аудита: ${p}. Фокус проверки: ${focus}.

# Задача
1. Прочитай код по пути ${p}.
2. Найди реальные проблемы по фокусу: баги, уязвимости, гонки, утечки, небезопасные паттерны, явные ошибки логики.
3. По каждой находке укажи: заголовок, где (файл:строка), серьёзность (critical/high/medium/low), суть и почему это проблема.

# Ограничения
- Только реальные проблемы. Не придирайся к стилю и форматированию.
- Если уверенности нет — лучше не включать (ложные срабатывания отсеет следующий слой).
- Если read-tool недоступен или ${p} не найден — верни пустой findings.

# Формат
Верни строго по JSON-схеме (массив findings). Если проблем нет — пустой массив.`,
    { label: cleanLabel('scan', p), phase: 'Поиск', model: 'sonnet', schema: FIND }
  ),
  (res, p) => {
    const findings = (res && res.findings) || []
    if (!findings.length) return []
    return parallel(findings.map((f) => () =>
      agent(
        `# Роль
Ты — скептик-ревьюер. Твоя задача — отсеять ложные срабатывания.

# Проверяемая находка
Файл/папка: ${p}
Заголовок: «${f.title}»
Где: ${f.where}
${f.detail ? 'Описание: ' + f.detail : ''}

# Задача
Перепроверь код и реши: это действительно проблема (real=true) или ложное срабатывание / не баг (real=false)?

# Ограничение (важно)
Если есть обоснованные сомнения, что это реальная проблема, — ставь real=false. В reason кратко поясни.

# Формат
Верни строго по JSON-схеме (real, reason).`,
        { label: cleanLabel('verify', p), phase: 'Проверка', model: 'sonnet', schema: VERD }
      ).then((v) => (v && v.real ? f : null))
    )).then((arr) => arr.filter(Boolean))
  }
)

const confirmed = results.flat().filter(Boolean)

// ФАЗА 3 — отчёт. Умная модель opus только на финал.
phase('Отчёт')
const report = await agent(
  `# Роль
Ты — тех-лид, который оформляет результаты аудита для команды.

# Контекст
Подтверждённые находки (прошли проверку), ${confirmed.length} шт., JSON:
${JSON.stringify(confirmed, null, 2)}

# Задача
Собери отчёт на русском:
1. Сгруппируй находки по серьёзности (critical → low).
2. По каждой: где (файл:строка), в чём суть, как чинить.
3. В начале — короткое резюме (сколько и какой серьёзности).

# Ограничения
- Только подтверждённые находки выше.
- Если находок нет — честно напиши, что проблем не обнаружено.

# Формат
Чистый Markdown.`,
  { label: 'report', phase: 'Отчёт', model: 'opus' }
)

return report
