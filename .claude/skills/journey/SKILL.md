---
name: journey
description: "Generate a read-only local radial graph of the memory/wiki/ knowledge base and .claude/skills/ timeline. Outputs a self-contained SVG HTML page. Does not modify text memory."
date: 2026-07-25
---

# /journey

Build a lightweight, read-only radial visualization of the project's memory graph.

## When to use

- User types `/journey`.
- User asks to see the knowledge graph, skill timeline, or memory map.

## Decision flow

1. Parse `memory/wiki/*.md` for cross-links `[[...]]` and frontmatter.
2. Parse `.claude/skills/*/SKILL.md` for skill nodes and acquisition dates.
3. Run `runtime.journey.cli` to generate `journey-out/index.html`.
4. Report node/edge counts and the file path.
5. Open the generated HTML locally only if the user explicitly asks.

## Failure modes

| Condition | Response |
|---|---|
| Missing wiki/skills directories | Generate empty graph with a warning. |
| Path outside workspace | MCPPathGuard blocks it; report error. |
| No write permission for output | Report the filesystem guard reason. |

## Usage

```
/journey
/journey --workspace .
/journey --output docs/journey.html
```
