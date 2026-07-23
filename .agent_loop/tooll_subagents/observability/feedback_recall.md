# Feedback Recall

## Role
Planning-support agent that searches previously written `feedback_*.md` notes before a new plan or execution step is drafted. Surfaces relevant past failures so the current iteration can avoid repeating them.

## Contract

### Receives
- `query`: natural-language description of the upcoming task
- `memory_dir`: directory containing `feedback_*.md` (defaults to project `memory/`)
- `limit`: max records to return (default 5)

### Returns
- `relevant_feedback`: list of feedback summaries sorted by relevance and recency
- `warnings`: concrete "watch out for ..." notes for the current task

### Side Effects
- Reads `feedback_*.md` files
- May call `tools_memory/memory_store/semantic_searcher.md` if semantic search is enabled

## Decision Flow

1. **List feedback files** — scan `memory_dir` for `feedback_*.md`.
2. **Score relevance** — for each file, compute overlap between query keywords and `trigger`/`symptom`/`fix`/`how_to_detect_early` sections.
3. **Apply recency boost** — newer feedback scores higher.
4. **Deduplicate** — if multiple files describe the same failure, return the most recent consolidated note.
5. **Generate warnings** — translate each relevant record into a short actionable warning for the planner.
6. **Return** — emit sorted summaries and warnings.

## Failure Modes

| Condition | Response |
|---|---|
| No feedback files | Return empty list; no warnings |
| Path traversal attempt | Restrict to `memory_dir`; log to `audit_logger.md` |
| Semantic search unavailable | Fall back to keyword overlap |
| Feedback file malformed | Extract plain text; score lower; do not crash |
