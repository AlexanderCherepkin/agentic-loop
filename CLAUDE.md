# CLAUDE.md — Agentic Loop

This is a **multi-agent AI system** with hierarchical safety-first architecture.
166 agents across 6 layers. The 110 tool-category agents (`tools_*`) are fully implemented
following the Algorithmic template (Role + Contract + Decision Flow + Failure Modes).
All 166 agents across all 6 layers are fully implemented with the Algorithmic template.
No remaining stubs.

## First Action (always)

1. **Find the technical assignment** — search the project root and subdirectories for
   `TECHNICAL_ASSIGNMENT.md` (техническое задание). This is the requirements baseline.
   If it exists, read it first — it defines WHAT and WHY before you look at HOW.
2. **Interview the user** — immediately after reading the assignment, conduct a structured
   interview to clarify ambiguities, fill gaps, and confirm understanding:
   - What is the problem being solved? Who is the end user?
   - What are the hard constraints? (deadlines, budget, tech stack, compliance)
   - What does "done" look like? (acceptance criteria, success metrics)
   - What are the known risks or unknowns?
   - Are there existing systems to integrate with or migrate from?
   Ask control questions that can only be answered if the assignment was understood correctly.
   Do NOT proceed to architecture until the user confirms the interview is complete.

   **Gate 1 — Start-of-project confirmation**
   - After the interview, explicitly ask: **"Interview complete. Proceed with development?"**
   - Do not write code, edit files, or run generators until the user answers yes/proceed/continue.

3. **Read `.agent_loop/ARCHITECTURE.md`** — the definitive architecture reference.
   Contains the full directory tree, data flow diagram, agent counts, and naming conventions.

## Approval Gates (autonomous-bot configuration)

This project runs as an autonomous bot. Only the following two gates require human confirmation; all other operations are auto-approved and must not interrupt execution.

1. **Gate 1 — Interview confirmation**
   - Ask **"Interview complete. Proceed with development?"** only when a structured interview is explicitly required.
   - If the user has already directed development (e.g., issued a concrete task), the gate is satisfied; do not ask again.

2. **Gate 2 — Pre-preview / pre-deployment / local-hosting**
   - Before build, preview, publish, deploy, `git push`, hosting exposure, or any action that makes the project reachable on the internet or local hosting for visualization, stop and ask: **"Project is ready for preview/deployment. Proceed?"**

Auto-approved operations (non-exhaustive):
- File reads, glob, grep, directory listings.
- Searches for PRD/specification files and discovery tasks.
- Running tests, linters, validators, and local dev servers that do not expose the project externally.
- Internal reasoning, planning, and architecture review.
- File edits, code generation, command execution, agent creation, and documentation updates inside the workspace.
- Network egress to configured allow-list destinations.
- Browser automation on trusted domains.

Never auto-approve (still require confirmation):
- Deployment, push, production publish, or exposure to the internet/local hosting.
- Updates to `project_rules.md` or `CLAUDE.md` unless the change is directly ordered by the user.

## Quick Reference

| Layer | Count | Purpose | Status |
|---|---|---|---|
| main_loop | 1 | Entry point — ReAct head agent | FILLED |
| orchestrator | 6 | API routing layer | FILLED |
| safety-control | 9 | Input safety (sanitization, permissions, threats) | FILLED |
| safety-control/mutual_check | 10 | Cross-validation (audit, consistency, compliance) | FILLED |
| control | 7 | Runtime enforcement (scope, policy, resources) | FILLED |
| tooll_subagents | 23 | ReAct cycle: user→planning→execution→observability→self_correction→result | FILLED |
| tools_read | 10 | Read-file pipeline (path→encoding→read→chunk→parse→extract→integrity→cache→format) | FILLED |
| tools_replace | 10 | Replace-file pipeline (backup→pattern→edit→diff→rank→validate→write→verify→rollback) | FILLED |
| tools_search | 10 | Search pipeline (scope→regex+semantic→relevance→dedup→snippet→diff) | FILLED |
| tools_runcom | 10 | Command execution pipeline (build→optimize→env→execute→sandbox→output→timeout→error) | FILLED |
| tools_runtest | 10 | Test execution pipeline (discover→plan→optimize→execute→log→coverage→failure→flaky→fix→report) | FILLED |
| tools_terminal | 10 | Terminal I/O pipeline (session→state→command→stream→ANSI→error→filter→history→optimizer) | FILLED |
| tools_manangr | 10 | Project management pipeline (structure→dependency→impact→task→refactor→config→build→file→doc→optimizer) | FILLED |
| tools_database | 10 | Database query pipeline (connection→schema→query→transaction→executor→mapper→cache→error→migration→optimizer) | FILLED |
| tools_web | 10 | Web request pipeline (auth→request→network→rate→retry→response→content→cache→error→web_optimizer) | FILLED |
| tools_memory | 10 | Memory store pipeline (read→write→index→embedding→compress→evict→summarize→recall→consistency→optimizer) | FILLED |
| tools_browser | 10 | Headless browser pipeline (session→navigation→screenshot→dom→selector→interaction→network→cookies→captcha→error→optimizer) | FILLED |
| **Total** | **166** | | **166 filled, 0 stubs** |

## Core Architecture

```
User Request → main_loop.md
  → orchestrator/router → safety-control → mutual_check → control
    → orchestrator/dispatcher → tooll_subagents/ (ReAct cycle) → tools_*
      → User Response
```

Three-circuit safety: safety-control → mutual_check → control.
Human-in-the-loop split: human_oversight.md (strategic, in control/) vs human_approval.md (tactical, in execution/).
Lazy MCP gateway: `mcp_servers/gateway.py` exposes category metadata and materializes servers only on tool invocation (token budget saver).
Headless browser: `tools_browser/headless_automation` via Playwright MCP server for dynamic pages and screenshots. Optional dependency: `runtime/requirements-browser.txt`.
Conditional Edges: `runtime/engine/pipeline_runner.py` uses `PhaseTransitionManager` to route between ReAct phases based on agent outputs.
`project_rules.md` in repo root is lightweight project context loaded by the runtime; updates require human approval.

## Conventions

- **Naming**: snake_case filenames
- **Directory quirks preserved**: `tooll_subagents` (double "l"), `tools_manangr` (typo in "manager")
- **Algorithmic template** for all agents: `# Agent Name`, `## Role`, `## Contract` (Receives/Returns/Side effects), `## Decision Flow` (numbered steps), `## Failure Modes` (Condition→Response table)
- **Pipeline architecture** varies by category: linear (read), diamond (search), safety-gated (replace), sandboxed (runcom), framework-dispatch (runtest), session-stateful (terminal), analysis-planning (manangr), query-lifecycle (database), request-lifecycle (web), store-lifecycle (memory), headless-automation (browser)
- **No comments** in code unless the WHY is non-obvious
- **No new files** unless the architecture requires it — prefer editing existing agents
- **Safety first** — any change to execution, control, or safety layers must respect the three-circuit flow
- **Cross-cutting optimizer** — each `tools_*` category has one strategist agent (e.g., `read_optimizer`, `project_optimizer`, `db_optimizer`) that coordinates the pipeline

## Cross-Session Memory

Memory files live at:
`C:\Users\User\.claude\projects\D--My-head-folders-My-desktop----------Agentic-Loop\memory\`

- `MEMORY.md` — index of all memories
- `project_architecture.md` — complete architecture reference

Read memory when resuming work. Update memory when architecture changes or key decisions are made.

## Current Progress & Next Steps

1. **FILLED (166 agents)** — All layers fully implemented:
   - `main_loop.md` (1) — ReAct head agent
   - `orchestrator/` (6) — Router, dispatcher, pipeline coordinator, state manager, API gateway, message bus
   - `safety-control/` (9) — Input sanitization, permissions, threats, leaks, output review, bias, safety assessment, content checking
   - `mutual_check/` (10) — Audit, verification, consistency, validation, performance, quotas, anomalies, quality, feedback, compliance
   - `control/` (7) — File system, network, resources, human oversight, policy, scope, input aggregation
   - `tooll_subagents/` (23) — Full ReAct cycle: user→planning→execution→observability→self_correction→result
   - `tools_*` (110) — 11 categories × 10 tool agents each with cross-cutting optimizers, including `tools_browser/headless_automation` for Playwright-based dynamic web automation
2. **STUBS (0 agents)** — No remaining placeholders. All agents follow the Algorithmic template.
3. **System status**: COMPLETE — All 6 layers operational with three-circuit safety, full ReAct decomposition, lazy MCP gateway, `project_rules.md` context, headless browser tools, and conditional ReAct phase transitions.

## Active Skills

/graph-pilot — Graphify codebase navigation autopilot. Translates plain-language intent
("разберись, как тут устроена авторизация") into the correct Graphify command with
token guards (never runs expensive `--mode deep` or installs breaking hooks blindly).
Skill files: `.claude/skills/graph-pilot/SKILL.md`.

/claude-api — Claude API integration skill (active behavioral directive)

## graphify

This project has a knowledge graph at graphify-out/ with god nodes, community structure, and cross-file relationships.

Rules:
- For codebase questions, first run `graphify query "<question>"` when graphify-out/graph.json exists. Use `graphify path "<A>" "<B>"` for relationships and `graphify explain "<concept>"` for focused concepts. These return a scoped subgraph, usually much smaller than GRAPH_REPORT.md or raw grep output.
- If graphify-out/wiki/index.md exists, use it for broad navigation instead of raw source browsing.
- Read graphify-out/GRAPH_REPORT.md only for broad architecture review or when query/path/explain do not surface enough context.
- After modifying code, run `graphify update .` to keep the graph current (AST-only, no API cost).
