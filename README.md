# Agentic Loop

Multi-agent AI system with hierarchical safety-first architecture.

- Agent specs across hierarchical layers
- Tool-category agents across `tools_*` pipelines
- ReAct-cycle agents in `tooll_subagents/`
- Three-circuit safety: `safety-control` → `mutual_check` → `control`
- Optional runtime modules: Figma-to-code pipeline, i18n, analytics/cookie consent, auth/identity, CMS/data queries, accessibility/WCAG 2.1, PWA/performance budget, design-token docs, multi-page routing, Storybook, preview/approval, deploy providers, git publisher, cost tracking, notifications

## Quick start

```bash
# Run health check
python .agent_loop/scripts/health_check.py

# Run validators
node .agent_loop/scripts/validate_cross_references.js
node .agent_loop/scripts/validate_consistency.js
node .agent_loop/scripts/validate_runtime_coverage.js

# Run core tests
pytest -m core
```

## Architecture

See `.agent_loop/ARCHITECTURE.md` for the full directory tree, data flow, and agent catalog.
