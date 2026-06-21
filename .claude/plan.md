# Интерактивные формы с валидацией — Plan

## Vision
Превратить Figma-формы, которые Backend Bridge уже сопоставляет с backend-моделями, в полноценные Next.js формы с client-side + server-side валидацией, состояниями загрузки/ошибки и доступностью. Генерация должна быть детерминированной и работать как часть существующего conductor pipeline.

## Scope
Supported:
- Zod-схемы, генерируемые из backend-моделей (OpenAPI/Prisma/text spec).
- React Hook Form + zodResolver для client-side валидации.
- Server Action (`create{Model}Action`) с встроенной Zod-проверкой и возвратом `{success, error, id}`.
- `useFormState` / `useFormStatus` (React 19 / Next.js 15) для loading/error/success состояний.
- Автоматический рендеринг `<form>`, `<input>`, `<textarea>`, `<select>` в `page_composer` на основе `backend_field`/`backend_action` из AST.
- Client-side сообщения об ошибках под каждым полем на основе Zod-схемы.
- Поддержка типов полей: text, email, number, checkbox, date, textarea, select.

Out of scope:
- Сложные кастомные валидаторы (regex, cross-field) на первом шаге.
- Файловые инпуты и rich-text редакторы.
- Интеграция с authentication / CSRF-токенами.

## Output Artifacts
- `backend_bridge_output/lib/schemas.ts` — Zod-схемы для всех мапленных моделей.
- `backend_bridge_output/actions/{model}Action.ts` — Server Action с Zod-валидацией.
- `backend_bridge_output/api/{model}.ts` — CRUD route (обновлён под схему, если нужно).
- `backend_mapping.json` — дополнен `zod_schema`, `validation_rules`.
- `src/app/page.tsx` — форма с react-hook-form (при прохождении через pipeline).

## Architecture

### `figma-agent-core/backend_bridge.py`
1. **Расширить `ModelField`**:
   - Добавить `min_length`, `max_length`, `min`, `max`, `pattern`, `is_enum` (опционально, извлекать из OpenAPI/Prisma/JSON по мере возможности).
2. **Добавить `ZodSchemaGenerator`**:
   - `generate(model_name, fields) -> str` — код TS с `import { z } from "zod"`.
   - Маппинг типов: String → `z.string()`, Int → `z.coerce.number().int()`, Float → `z.coerce.number()`, Boolean → `z.boolean()`, DateTime → `z.coerce.date()`.
   - Добавить `.email()` для email, `.min()`/`.max()` если заданы, `.optional()` для non-required.
   - Экспортировать inferred type: `export type {Model}Schema = z.infer<typeof schema>`.
3. **Обновить `ActionGenerator`**:
   - Импортировать схему из `@/lib/schemas`.
   - Внутри action: `const parsed = schema.safeParse(Object.fromEntries(formData))`.
   - При ошибке вернуть `{ success: false, error: parsed.error.flatten().fieldErrors }`.
   - При успехе: create в prisma, вернуть `{ success: true, id: item.id }`.
   - Убрать raw `formData.forEach` без валидации.
4. **Обновить `BackendBridge.run`**:
   - Создавать `(output_dir / "lib").mkdir()`.
   - Для каждой мапленной модели генерировать `lib/schemas.ts` (один файл на все модели).
   - Добавить пути схем в `generated_files.schemas`.
   - Дополнить `mapping` полем `zod_schemas` и `validation_rules`.

### `figma-agent-core/page_composer.py`
1. **Detect validated forms**:
   - Если нода имеет `backend_action` и хотя бы один descendant с `backend_field`, пометить как validated form.
2. **Imports**:
   - Добавить `"use client"` для страниц с формами.
   - `import { useForm } from "react-hook-form"`
   - `import { zodResolver } from "@hookform/resolvers/zod"`
   - `import { schema, {Model}Schema } from "@/lib/schemas"`
   - `import { useFormState, useFormStatus } from "react-dom"`
   - `import { actionName } from "@/app/actions/..."`
3. **State hooks**:
   - `const [state, formAction] = useFormState(action, { success: false })`.
   - `const { register, handleSubmit, formState: { errors } } = useForm<{Model}Schema>({ resolver: zodResolver(schema), mode: "onBlur" })`.
4. **Render form**:
   - Обернуть в `<form action={formAction} onSubmit={handleSubmit(() => {})}>`.
   - Для каждого input-поля: render label, input с `name={field}`, `type={input_type}`, `{...register(field)}`.
   - Рендерить `{errors.field && <span className="text-red-500 text-sm">{errors.field.message}</span>}`.
   - Submit button с `useFormStatus`: `{pending ? "Submitting..." : "Submit"}`.
   - Глобальное сообщение: `state.success ? "Saved!" : state.error ? JSON.stringify(state.error) : null`.
5. **Input types**:
   - Улучшить `_node_to_tsx`: если `backend_field`, определять tag по `input_type`: `input`, `textarea`, `select`.
   - Для select рендерить options из enum-модели, если backend_mapping предоставляет values.

### `figma-agent-core/layout_engine.py`
1. **Semantic tags для форм**:
   - В `_semantic_tag` добавить: если имя содержит form/contact/lead/signup/login/subscribe → `form`.
   - Если backend_field и имя содержит message/comment/bio → `textarea`; select/country/role → `select`.
2. **Validation hints**:
   - Добавить в TailwindNode поля `min_length`, `max_length`, `min`, `max`, `pattern` и заполнять из backend_mapping или ModelField.

### `mcp_servers/backend_server.py`
- Убедиться, что результат `backend_run_bridge` включает `generated_files.schemas` и `validation_rules`.
- Добавить tool `backend_generate_validation` (опционально, если MCP server имеет дискретные tools).

### Conductor
- Никаких изменений не требуется: `stage_backend_bridge` и `stage_compose` уже получают/пишут нужные файлы.

## Acceptance Criteria
- `pytest tests/backend -q` проходит с новыми тестами на Zod-схемы, Server Action validation и рендеринг формы.
- Сгенерированная страница с формой компилируется без TypeScript ошибок (при наличии зависимостей).
- Все существующие figma/MCP/backend тесты остаются зелёными.
- Validators 0 errors.
- Graphify обновлён AST-only.
- Memory file создан: `2026-06-21-form-validation.md`.
- Commit и push по Gate 2.

## Tracker Tasks
1. Расширить `ModelField` и парсеры для validation-метаданных.
2. Добавить `ZodSchemaGenerator` и обновить `BackendBridge.run` для генерации `lib/schemas.ts`.
3. Обновить `ActionGenerator` для Zod-валидации и ошибок.
4. Улучшить `_semantic_tag`/`_apply_backend_hints` в `layout_engine.py` для form/textarea/select.
5. Обновить `page_composer.py` для react-hook-form + zodResolver + useFormState/useFormStatus.
6. Добавить тесты в `tests/backend/`.
7. Обновить `mcp_servers/backend_server.py` при необходимости.
8. Прогнать тесты, validators, graphify, написать memory, закоммитить и запушить.
