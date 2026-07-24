# Wiki Schema

Allowed page types: concept, howto, decision, project, source, person, tool.

## Required frontmatter

```yaml
---
name: page-name
description: One-line summary.
metadata:
  type: concept
  status: draft | active | deprecated
  created: YYYY-MM-DD
  updated: YYYY-MM-DD
---
```

## Optional metadata

- `sources`: list of source URLs or file paths.
- `tags`: list of free-form tags.
- `priority`: 1–5.

## Cross-links

Use `[[page-name]]` to link to other wiki pages.
