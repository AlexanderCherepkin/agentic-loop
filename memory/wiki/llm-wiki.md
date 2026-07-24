---
name: llm-wiki
description: Karpathy-method LLM Wiki overview and conventions for the Agentic Loop project.
metadata:
  type: concept
  status: active
  created: 2026-07-24
  updated: 2026-07-24
---

# LLM Wiki

The project maintains a two-sided memory wiki under `memory/wiki/`:

- **Ingest** — raw sources, chat transcripts, and experiences are turned into markdown pages with frontmatter and cross-links.
- **Query** — before answering, the system reads relevant wiki pages.
- **Lint** — orphans, duplicates, broken links, and stale pages are surfaced for cleanup.

## Page types

- `concept` — reusable idea, protocol, or pattern.
- `howto` — step-by-step instructions.
- `decision` — recorded architectural or product decision.
- `project` — ongoing work, goals, constraints.
- `source` — auto-ingested raw material.
- `person` — stakeholder or team member notes.
- `tool` — tool, library, or skill reference.

## Conventions

- Every page has frontmatter with `name`, `description`, and `metadata.type`.
- Cross-link with `[[llm-wiki]]`.
- Keep `MEMORY.md` thin; it only links to wiki pages.
