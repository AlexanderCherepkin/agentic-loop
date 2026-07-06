# План интеграции Headroom (Context Compression Layer) в Agentic Loop

## Контекст

Пользователь приложил файл `2.docx` и репозиторий [chopratejas/headroom](https://github.com/chopratejas/headroom). Headroom — локальный слой оптимизации контекста для LLM-приложений: сжимает tool outputs, логи, RAG-куски, историю диалога и файлы на 60–95 %, сохраняя точность ответов. Использует обратимое сжатие (CCR — Compress-Cache-Retrieve): оригинал хранится локально, LLM может вызвать `headroom_retrieve` для восстановления деталей.

## Решения пользователя

1. Вариант интеграции: **MCP tools + inline Python SDK** (`compress()` + `SharedContext`).
2. Зависимость: **опциональная**, как Playwright (`runtime/requirements-headroom.txt`).

## Цель интеграции

Headroom должен стать **дополнительным MCP-слоем сжатия контекста** внутри Agentic Loop:
- явное сжатие больших tool outputs / логов / файлов перед отправкой в LLM;
- восстановление оригинала по hash, когда LLM запрашивает детали;
- прозрачная статистика экономии токенов (`headroom_stats`);
- общий сжатый контекст для суб-агентов через `SharedContext`;
- graceful degradation, если `headroom-ai` не установлен.

## Архитектурный подход

Headroom не выносится в отдельную `tools_*` категорию (чтобы не нарушать 12 существующих pipeline). Вместо этого:
- новая MCP-категория `headroom` в `mcp_servers/headroom_server.py` (3 tools: `headroom_compress`, `headroom_retrieve`, `headroom_stats`);
- runtime-модуль `runtime/engine/headroom_client.py` оборачивает Python SDK (`compress`, `SharedContext`) с graceful degradation;
- новые markdown-агенты в `tooll_subagents/planning/` и `tooll_subagents/observability/` планируют и выполняют сжатие;
- существующие агенты обновляются ссылками на Headroom и используют его в ReAct-цикле.

## Изменения

### 1. Новый MCP-сервер

**Файл:** `mcp_servers/headroom_server.py`

Повторяет паттерн `figma_server.py` / `backend_server.py`:
- lazy-loaded, reports `degraded` if `headroom-ai` is not installed;
- tools:
  - `headroom_compress(content: string, model?: string, target_ratio?: float)` → `{ compressed, hash, original_tokens, compressed_tokens, tokens_saved, savings_percent, transforms }`;
  - `headroom_retrieve(hash: string)` → `{ original_content, source }`;
  - `headroom_stats()` → `{ compressions, retrievals, total_input_tokens, total_output_tokens, total_tokens_saved, savings_percent, estimated_cost_saved_usd }`.
- `_check_degraded()` проверяет наличие пакета `headroom` через `importlib.util.find_spec("headroom")`.
- Handlers используют `headroom.compress.compress()` и `headroom.cache.compression_store.get_compression_store()`.

### 2. Новый runtime-клиент

**Файл:** `runtime/engine/headroom_client.py`

Содержит:
- `HeadroomConfig` (model default, target_ratio, min_tokens_to_compress, session_ttl);
- `HeadroomClient`:
  - `is_available()` — проверка импорта `headroom`;
  - `compress_text(text: str, model: str | None = None)` → `(compressed_text, hash, before_tokens, after_tokens)`;
  - `compress_messages(messages: list[dict], model: str | None = None)` → `CompressResult`-like dict;
  - `retrieve(hash: str)` → original content or None;
  - `stats()` → session stats dict;
  - `shared_context()` → ленивый `SharedContext` singleton.
- Graceful degradation: если `headroom-ai` не установлен, все методы возвращают `available=False` и passthrough-результаты.

### 3. Новые markdown-агенты

Все следуют Algorithmic template (Role, Contract, Decision Flow, Failure Modes).

#### a) `tooll_subagents/planning/headroom_injector.md`

**Role:** планирует применение Headroom к тяжёлым участкам контекста внутри ReAct-плана.

**Contract:**
- Receives: `task_graph`, `execution_policy`, `token_budget`, `available_mcp_categories`, `headroom_enabled` (env/override).
- Returns: `compression_plan`: list of `{phase, tool_output_keys, threshold_tokens, fallback}`; `headroom_selected` boolean.
- Side effects: logs to `audit_logger.md`.

**Decision Flow:**
1. If `headroom` not in `available_mcp_categories` or `headroom_enabled=false` → return empty plan.
2. Identify context-heavy phases in `task_graph` (runcom outputs, search results, file reads > threshold, RAG chunks, multi-agent handoffs).
3. For each heavy phase, decide compression strategy:
   - tool outputs > 500 tokens → `headroom_compress` before passing to next agent;
   - multi-agent shared context → `headroom_shared_context.put/get`;
   - repeated file reads → cache marker + `headroom_retrieve` on demand.
4. Insert `headroom_compressor.md` and `headroom_retriever.md` into tool plan where needed.
5. Set `headroom_selected=true` if any compression planned.

**Failure Modes:**
| Condition | Response |
|---|---|
| Headroom MCP unavailable | Empty compression plan; log degraded state |
| `token_budget` too small to afford compression overhead | Skip compression; log reason |
| Compression target smaller than threshold | Skip; not worth overhead |

#### b) `tooll_subagents/observability/headroom_compressor.md`

**Role:** выполняет сжатие наблюдаемых результатов (tool outputs, runtime logs, RAG chunks) перед передачей в следующий шаг ReAct.

**Contract:**
- Receives: `raw_content` (string or list of messages), `content_type` (`tool_output`, `log`, `file`, `rag`, `messages`), `model` (optional), `target_ratio` (optional), `force` (bool).
- Returns: `compressed_content`, `hash`, `original_tokens`, `compressed_tokens`, `tokens_saved`, `savings_percent`, `retrieval_hint`.
- Side effects: stores original in local CCR store; logs to `audit_logger.md`.

**Decision Flow:**
1. Check `headroom` availability via `runtime/engine/headroom_client.py`.
2. If unavailable or `force=false` and content length < `min_tokens_to_compress` → return passthrough.
3. Route by `content_type`:
   - `messages` → `headroom.compress.compress(messages, model=...)`;
   - single text → wrap as `[{"role":"tool","content":text}]` and compress.
4. Store original in CCR store; capture hash.
5. Return compressed result + retrieval hint.

**Failure Modes:**
| Condition | Response |
|---|---|
| headroom-ai not installed | Passthrough with `available=false`; no hash |
| Compression raises exception | Return original content + error marker; log to `anomaly_detector.md` |
| Result longer than original | Return original; log negative compression |

#### c) `tooll_subagents/observability/headroom_retriever.md`

**Role:** восстанавливает оригинальные несжатые данные по hash, когда другой агент или LLM запрашивает детали.

**Contract:**
- Receives: `hash` (string), `source_hint` (`local`, `proxy`, `auto`).
- Returns: `original_content` or `not_found` + `source`.
- Side effects: logs retrieval to `audit_logger.md`; updates stats.

**Decision Flow:**
1. Validate hash format (non-empty string).
2. Try local CCR store via `headroom_client.py` / `headroom.cache.compression_store`.
3. If not found and proxy configured, try `HEADROOM_PROXY_URL`.
4. Return original content or structured not-found response with recovery hints.

**Failure Modes:**
| Condition | Response |
|---|---|
| Hash empty/invalid | Return error; do not call store |
| Content expired | Return not_found + "re-run original command/read" hint |
| Proxy unreachable | Return local result or not_found; log network issue |

### 4. Обновление существующих агентов

#### `main_loop.md`

- Добавить в `Receives`: `headroom_enabled` (bool, optional override), `headroom_config` (dict, optional).
- Decision Flow step 1: загрузить `HEADROOM_ENABLED` env (default `true`), передать в `tooll_subagents/user/context.md`.
- Decision Flow step 6g (context compaction): если `headroom_enabled=true`, вместо или вместе с `context_compressor.md` вызывать `headroom_compressor.md` для сжатия ReAct-истории.
- Failure Modes: добавить обработку ошибки Headroom compression — skip compression, continue loop.

#### `tooll_subagents/planning/tool_plan_selection.md`

- В Decision Flow step 2 (map to tool categories) добавить: для тяжёлых контекстных задач включать MCP-категорию `headroom` (`headroom_compress`, `headroom_retrieve`, `headroom_stats`).
- Добавить explicit step: перед code-generation, если контекст большой, вызвать `headroom_injector.md`.
- Failure Modes: добавить строку про недоступность `headroom` — выбрать fallback `context_compressor.md`.

#### `tooll_subagents/execution/tool_invocation.md`

- Decision Flow step 4c: если инструмент из MCP-категории `headroom`, маршалить аргументы и отправлять через `mcp_servers/gateway.py`.
- Добавить обработку slash-команд (опционально):
  - `/headroom-stats` → `headroom_stats`;
  - `/headroom-compress <content>` → `headroom_compress`.
- Failure Modes: добавить обработку `headroom` MCP degradation.

#### `tooll_subagents/observability/memory_enrichment.md`

- Decision Flow step 4 (summarize): если `headroom_enabled=true`, для больших `observation_artifacts` вызывать `headroom_compressor.md` перед записью в memory;
- хранить `headroom_hash` в memory entry для последующего `headroom_retriever.md`.

#### `mcp_servers/bootstrap.py`

- Импортировать `HeadroomMCPServer`;
- Добавить `"headroom": HeadroomMCPServer` в `constructors`;
- Добавить описание в `descriptions`;
- Добавить self-test для `headroom` в `test_all_servers` (degraded acceptable).

#### `mcp_servers/registry.py`

- Добавить `"headroom": "Headroom context compression pipeline"` в `CATEGORY_MAP`.

#### `runtime/engine/llm_engine.py`

- НЕ оборачивать реальный LLM-вызов автоматически (рискует нарушить safety/control/audit flow). Вместо этого добавить опциональный helper:
  - `LLMConfig.headroom_enabled: bool`;
  - в `LLMEngine` добавить метод `compress_messages(messages)` для явного сжатия перед вызовом, если вызывающий код решит использовать.

### 5. Обновление документации и правил

#### `project_rules.md`

Добавить раздел:
```markdown
## Headroom Context Compression

- Enabled by default when `headroom-ai` is installed (`HEADROOM_ENABLED=true` overrides; `false` disables).
- Use `headroom_compress` on tool outputs, logs, search results, and RAG chunks > 500 tokens before passing them to the next agent.
- Store original content via Headroom CCR; retrieve full details on demand with `headroom_retrieve` and the returned hash.
- `headroom_stats` tracks session token savings and estimated cost reduction.
- For multi-agent handoffs use `SharedContext` (wrapped in `runtime/engine/headroom_client.py`) to share compressed context without inflating tokens.
- If Headroom is unavailable, fall back to the built-in `context_compressor.md` and continue without blocking.
```

#### `CLAUDE.md`

- Quick Reference: добавить строку `headroom` в таблицу tool categories? Нет, headroom — MCP категория, не `tools_*`. Добавить в Core Architecture bullet:
  - "Headroom context compression: `mcp_servers/headroom_server.py` exposes `headroom_compress`, `headroom_retrieve`, `headroom_stats` for 60–95 % token reduction on tool outputs and logs; optional `headroom-ai` dependency."
- Current Progress: обновить counts (187 → 190 agents, tooll_subagents 33 → 36).

#### `.agent_loop/ARCHITECTURE.md`

- Directory Tree:
  - `planning/` — добавить `headroom_injector.md`;
  - `observability/` — добавить `headroom_compressor.md`, `headroom_retriever.md`.
- Agent Counts:
  - `tooll_subagents` 33 → 36;
  - `Total` 187 → 190.
- Key Decisions: добавить пункт #13 про Headroom MCP category.
- Runtime / MCP: добавить `mcp_servers/headroom_server.py` bullet.

### 6. Зависимости

**Файл:** `runtime/requirements-headroom.txt`

```text
# Optional Headroom context-compression dependencies for Agentic Loop.
# Install only when Headroom tools are needed:
#     pip install -r runtime/requirements.txt -r runtime/requirements-headroom.txt

headroom-ai[proxy,mcp]>=0.28.0
```

Не добавлять в core `requirements.txt` — сохранить лёгкость базовой установки.

## Порядок выполнения

1. Создать `runtime/engine/headroom_client.py`.
2. Создать `mcp_servers/headroom_server.py`.
3. Создать markdown-агентов:
   - `tooll_subagents/planning/headroom_injector.md`
   - `tooll_subagents/observability/headroom_compressor.md`
   - `tooll_subagents/observability/headroom_retriever.md`
4. Обновить `mcp_servers/bootstrap.py` и `mcp_servers/registry.py`.
5. Обновить `main_loop.md`, `tool_plan_selection.md`, `tool_invocation.md`, `memory_enrichment.md`, `llm_engine.py`.
6. Создать `runtime/requirements-headroom.txt`.
7. Запросить human approval для обновления `project_rules.md`, `CLAUDE.md`, `ARCHITECTURE.md`.
8. После approval обновить документацию.
9. Запустить валидаторы и тесты; исправить ошибки.
10. Сделать коммит.

## Валидация и тесты

- `node .agent_loop/scripts/validate_cross_references.js` → 0 broken links, 0 isolated agents.
- `node .agent_loop/scripts/validate_consistency.js` → 0 errors (warnings допустимы).
- `python -m pytest` → все runtime-тесты проходят.
- Smoke-test `HeadroomClient` в режиме degraded (без `headroom-ai`) и при наличии пакета (если установлен).
- `python -m mcp_servers.bootstrap --test` → `headroom` сервер возвращает degraded или operational.

## Риски и ограничения

- `headroom-ai` тянет Rust-расширение и тяжёлые ML-зависимости, поэтому остаётся **опциональным**. Все пути имеют graceful degradation.
- Автоматическое сжатие LLM-сообщений не внедряется без явного вызова агента — чтобы не нарушать safety/control/audit flow.
- Добавление 3 новых агентов меняет counts в `ARCHITECTURE.md` и `CLAUDE.md` (187 → 190); требуется точный пересчёт.
- `project_rules.md`, `CLAUDE.md`, `ARCHITECTURE.md` требуют explicit human approval — работа не считается завершённой без него.
