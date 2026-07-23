# Feedback Writer

## Role
Observation-layer agent that persists normalized feedback records from `tooll_subagents/observability/feedback_collector.md` into durable `feedback_<topic>.md` notes under the project memory directory.

## Contract

### Receives
- `feedback_records`: list from `feedback_collector.md`
- `memory_dir`: target directory (defaults to project `memory/`)
- `overwrite_policy`: enum (`merge`, `append`, `skip`)

### Returns
- `written_files`: list of paths
- `status`: enum (`ok`, `partial`, `failed`)

### Side Effects
- Writes/updates `memory/feedback_<topic>.md` files
- Logs writes to `audit_logger.md`

## Decision Flow

1. **Validate destination** — ensure `memory_dir` is inside the workspace; reject path traversal.
2. **Derive topic filename** — from `topic` or by slugifying `trigger` + primary file/agent.
3. **Format note** — each file uses the canonical structure:
   - `trigger`
   - `symptom`
   - `root_cause`
   - `fix`
   - `how_to_detect_early`
   - `related_agents`
   - `last_seen`
4. **Merge or append** — if file exists, append a new dated entry unless `overwrite_policy=skip`.
5. **Write atomically** — write to temp then rename.
6. **Return** — emit written paths and status.

## Failure Modes

| Condition | Response |
|---|---|
| Path outside workspace | `status=failed`; reject write |
| Invalid topic (empty or unsafe chars) | Slugify; if still invalid, skip record |
| File system error | Retry once; on persistent failure, buffer in memory and report partial |
| Feedback record missing required fields | Infer from available fields; skip only if `trigger` and `symptom` are both missing |
