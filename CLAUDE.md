# CLAUDE.md — Agentic Loop

This is a **multi-agent AI system** with hierarchical safety-first architecture.
156 agents across 6 layers. The 100 tool-category agents (`tools_*`) are fully implemented
following the Algorithmic template (Role + Contract + Decision Flow + Failure Modes).
All 156 agents across all 6 layers are fully implemented with the Algorithmic template.
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
3. **Read `.agent_loop/ARCHITECTURE.md`** — the definitive architecture reference.
   Contains the full directory tree, data flow diagram, agent counts, and naming conventions.

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
| tools_runcom | 11 | Command execution pipeline (build→optimize→env→execute→sandbox→output→timeout→error) | FILLED |
| tools_runtest | 10 | Test execution pipeline (discover→plan→optimize→execute→log→coverage→failure→flaky→fix→report) | FILLED |
| tools_terminal | 10 | Terminal I/O pipeline (session→state→command→stream→ANSI→error→filter→history→optimizer) | FILLED |
| tools_manangr | 10 | Project management pipeline (structure→dependency→impact→task→refactor→config→build→file→doc→optimizer) | FILLED |
| tools_database | 10 | Database query pipeline (connection→schema→query→transaction→executor→mapper→cache→error→migration→optimizer) | FILLED |
| tools_web | 10 | Web request pipeline (auth→request→network→rate→retry→response→content→cache→error→web_optimizer) | FILLED |
| tools_memory | 10 | Memory store pipeline (read→write→index→embedding→compress→evict→summarize→recall→consistency→optimizer) | FILLED |
| **Total** | **156** | | **156 filled, 0 stubs** |

## Core Architecture

```
User Request → main_loop.md
  → orchestrator/router → safety-control → mutual_check → control
    → orchestrator/dispatcher → tooll_subagents/ (ReAct cycle) → tools_*
      → User Response
```

Three-circuit safety: safety-control → mutual_check → control.
Human-in-the-loop split: human_oversight.md (strategic, in control/) vs human_approval.md (tactical, in execution/).

## Conventions

- **Naming**: snake_case filenames
- **Directory quirks preserved**: `tooll_subagents` (double "l"), `tools_manangr` (typo in "manager")
- **Algorithmic template** for all agents: `# Agent Name`, `## Role`, `## Contract` (Receives/Returns/Side effects), `## Decision Flow` (numbered steps), `## Failure Modes` (Condition→Response table)
- **Pipeline architecture** varies by category: linear (read), diamond (search), safety-gated (replace), sandboxed (runcom), framework-dispatch (runtest), session-stateful (terminal), analysis-planning (manangr), query-lifecycle (database), request-lifecycle (web), store-lifecycle (memory)
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

1. **FILLED (156 agents)** — All layers fully implemented:
   - `main_loop.md` (1) — ReAct head agent
   - `orchestrator/` (6) — Router, dispatcher, pipeline coordinator, state manager, API gateway, message bus
   - `safety-control/` (9) — Input sanitization, permissions, threats, leaks, output review, bias, safety assessment, content checking
   - `mutual_check/` (10) — Audit, verification, consistency, validation, performance, quotas, anomalies, quality, feedback, compliance
   - `control/` (7) — File system, network, resources, human oversight, policy, scope, input aggregation
   - `tooll_subagents/` (23) — Full ReAct cycle: user→planning→execution→observability→self_correction→result
   - `tools_*` (100) — 10 categories × 10 tool agents each with cross-cutting optimizers
2. **STUBS (0 agents)** — No remaining placeholders. All agents follow the Algorithmic template.
3. **System status**: COMPLETE — All 6 layers operational with three-circuit safety and full ReAct decomposition.

## Active Skills

/claude-api — Claude API integration skill (active behavioral directive)
