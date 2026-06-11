# Memory Enrichment

## Role
Session-memory augmentation agent that extracts key facts, decisions, constraints, and lessons from the current execution phase and persists them into long-term memory. Ensures the agent system retains context across turns, sessions, and restarts for improved future performance.

## Contract

### Receives
- `execution_outcome`: structured result from completed tool invocations
- `observation_artifacts`: outputs from `environment_result.md`, `runtime_output.md`, `file_context.md`
- `memory_policy`: enum (`minimal`, `standard`, `comprehensive`) — controls retention depth
- `memory_tags`: list of topical keywords for retrieval indexing

### Returns
- `memory_entries`: list of created or updated memory records with IDs and confidence scores
- `compression_ratio`: float — how much the raw observations were compressed into memory
- `recall_keys`: list of identifiers that can be used to retrieve this context later
- `enrichment_status`: enum (`complete`, `partial`, `failed`) — whether all observations were successfully memorized

### Side Effects
- Writes to `tools_memory/memory_store/memory_writer.md`
- Updates embedding index via `tools_memory/memory_store/embedding_agent.md`
- May trigger `tools_memory/memory_store/eviction_policy.md` if store near capacity

## Decision Flow

1. **Classify observation types** — categorize artifacts into: facts (file paths, values), decisions (chosen tool, approved plan), constraints (policies, limitations), lessons (what worked, what failed), and user preferences (style, format, priority).
2. **Filter by policy** — `minimal` retains only decisions and critical facts; `standard` adds constraints and lessons; `comprehensive` retains all categorized observations with context.
3. **Deduplicate** — check for semantically similar existing memory entries; update rather than duplicate if similarity > 0.9.
4. **Summarize** — compress raw observations into concise, retrieval-optimized statements with preserved key identifiers.
5. **Assign tags and keys** — attach `memory_tags`, source timestamp, and expiration policy to each entry.
6. **Generate embeddings** — compute vector representations for semantic retrieval via `embedding_agent.md`.
7. **Write to store** — persist entries via `memory_writer.md`; handle capacity pressure via `eviction_policy.md`.
8. **Verify write** — spot-check that critical entries are retrievable by `memory_reader.md`.
9. **Return** — emit memory entries, compression ratio, recall keys, status.

## Failure Modes

| Condition | Response |
|---|---|
| Memory store write failure | Buffer locally; retry 3× with exponential backoff; if still failing, `enrichment_status=failed` |
| Embedding computation unavailable | Store plaintext with tags only; `compression_ratio=0.0`; queue embedding for later batch |
| Store capacity exceeded | Trigger `eviction_policy.md`; if insufficient, `memory_policy` temporarily downgraded to `minimal` |
| Critical observation too large to summarize | Store as chunked segments with linked recall keys; `compression_ratio` computed per chunk |
| Deduplication false-positive (distinct but similar facts) | Split merged entry; store both versions with disambiguation tags; log to `feedback_aggregator.md` |
