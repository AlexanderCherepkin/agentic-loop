# CLAUDE.md — Agentic Loop

This is a **multi-agent AI system** with hierarchical safety-first architecture.
289 agents/files across 6 layers. The 124 tool-category agents (`tools_*`) are fully implemented
following the Algorithmic template (Role + Contract + Decision Flow + Failure Modes).
All 289 agents/files across all 6 layers are fully implemented with the Algorithmic template.
i18n / multilanguage, analytics / cookie-consent, auth / identity, CMS / data-query, accessibility / WCAG 2.1, PWA / performance-budget, design-token documentation, web-project classification/architecture/development, project-starter templating, code review, security scanning, quality evaluation, image deploy providers, git publishing, cost tracking, and notification modules are fully wired through planning, execution, self-correction, and observability agents; all core tests pass.
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
| tooll_subagents | 132 | ReAct cycle: user→planning→execution→observability→self_correction→result, including Ponytail injector/review/audit, Headroom injector/compressor/retriever, Memanto remember/recall/answer, Mem0 remember/recall/list, i18n requirements/language/key/dictionary/routing/rewrite/optimizer/fallback/RTL/missing-key/audit, analytics requirements/provider/event/script/optimizer/banner/jurisdiction/policy/privacy/blocker/audit, auth requirements/provider/runtime/validator/audit, CMS requirements/source/runtime/validator/audit, accessibility requirements/checker/runtime/validator/audit, PWA requirements/optimizer/runtime/validator/audit, design-token docs requirements/format/runtime/validator/audit, web-project classifier/architect/developer, project-starter planner, git-publish planner/integrator, notification integrator, code-review validator, diff-patch applier, security-scan validator, quality evaluator, and cost-audit agents | FILLED |
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
| tools_browser | 12 | Headless browser pipeline (session→navigation→screenshot→dom→selector→interaction→network→cookies→captcha→error→visual_qa→optimizer) | FILLED |
| tools_lighthouse | 11 | Lighthouse hard-gate pipeline (session→navigation→audit→parse→performance→a11y→best-practices→seo→correction-prompt→loop-terminator→optimizer) | FILLED |
| **Total** | **289** | | **289 filled, 0 stubs** |

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
Headroom context compression: optional local LLM CCR layer exposed as MCP category `headroom` (`headroom_compress`, `headroom_retrieve`, `headroom_stats`) and as `runtime/engine/headroom_client.py` with `SharedContext` for inter-agent handoffs. Integrated into `main_loop.md` context compaction, `tool_plan_selection.md`, `tool_invocation.md`, `memory_enrichment.md`, and `llm_engine.py`. Falls back to plaintext passthrough if `headroom-ai` is not installed. Optional dependency: `runtime/requirements-headroom.txt`.
Memanto semantic memory: optional active memory agent exposed as MCP category `memanto` (`memanto_create_agent`, `memanto_remember`, `memanto_recall`, `memanto_answer`) and as `runtime/engine/memanto_client.py`. Integrated into `main_loop.md` session lifecycle, `tool_plan_selection.md` recall-before-planning, `tool_invocation.md` MCP routing, and `memory_enrichment.md` long-term persistence. Falls back to in-memory store when the Memanto server is unreachable. Optional dependency: `runtime/requirements-memanto.txt`.
Mem0 long-term memory: optional hybrid semantic + keyword memory layer exposed as MCP category `mem0` (`mem0_add`, `mem0_search`, `mem0_get_all`, `mem0_delete`) and as `runtime/engine/mem0_client.py`. Integrated into `main_loop.md` session lifecycle, `tool_plan_selection.md` recall-before-planning, `tool_invocation.md` MCP routing, and `memory_enrichment.md` long-term persistence. Supports embedded local vector stores (Chroma/Qdrant) or the managed Mem0 cloud API. Falls back to in-memory store when `mem0ai` is not installed or the API is unreachable. Optional dependency: `runtime/requirements-mem0.txt`.
Web Project Agents MCP categories: optional `security_scanner` (`scan_codebase`), `git_publisher` (`publish_repository`, `check_configured`), `cost_tracking` (`estimate_cost`, `get_report`, `check_budget`, `set_budget`), and `notifications` (`dispatch_notification`) servers wrap the new runtime modules and degrade gracefully when dependencies/env are missing.
Lighthouse hard gate: `tools_lighthouse/audit` runs Lighthouse via Playwright, parses 500 KB reports into compact correction prompts, and enforces 100% on Performance, Accessibility, Best Practices, and SEO with a 8-iteration convergence guard. Integrated into `self_correction/result_validation.md` and `recursion_or_termination.md`.
Backend Spec Bridge: `figma-agent-core/backend_bridge.py` parses OpenAPI/Prisma/text specs, maps UI forms to backend models, and generates `prisma/schema.prisma`, `app/api/*.ts` routes, and `app/actions/*Action.ts` Server Actions. MCP category `backend` registered in `mcp_servers/backend_server.py`.
Visual QA V2: `figma-agent-core/figma_reference_downloader.py` fetches Figma reference screenshots; `figma-agent-core/visual_qa.py` runs stable Chromium (exact viewport, font/image loading wait, disabled animations), structural layout checks (overflow, clipped text, overlaps, bbox mismatch), and feeds structured reports into `figma-agent-core/refinement_loop.py` for deterministic AST adjustments.
Conditional Edges: `runtime/engine/pipeline_runner.py` uses `PhaseTransitionManager` to route between ReAct phases based on agent outputs.
i18n module: `runtime/i18n/` exposes `I18nIntegrationEngine` for deterministic Next.js `next-intl` generation, plus planning agents for requirements, language detection, key extraction, dictionary generation, routing, component rewriting, RTL validation, missing-key guards, and audit.
Analytics and cookie consent module: `runtime/analytics/` exposes `AnalyticsIntegrationEngine` for deterministic analytics provider + consent UI generation across GA4, Yandex, Plausible, PostHog, Mixpanel, with GDPR/ePrivacy/152-FZ/PIPL/CCPA jurisdiction mapping, default-deny categories, CSP helpers, privacy validation, and audit.
CMS / data queries module: `runtime/cms_queries/` exposes `CmsQueriesEngine` for deterministic Next.js App Router data-layer generation for dynamic sections (`blog`, `portfolio`, `cases`) across `local_markdown`, `notion`, `contentful`, `strapi`, `prisma`, `airtable`, `google_sheets`, and `cms_api`, with static fallback, SDK dependency injection, and provider-agnostic typed wrappers.
PWA / performance budget module: `runtime/pwa/` exposes `PwaEngine` for deterministic Next.js PWA artifact generation (`manifest.json`, `sw.js`, `offline.html`, `src/lib/pwa.ts`, `src/lib/pwa-meta.ts`, `src/components/PwaRegister.tsx`) plus performance-budget diagnostics (JS/CSS/image/font/third-party budgets), `srcset`/`sizes` image hints, font-subsetting guidance, and `next.config.js` patching.
Design token docs module: `runtime/design_token_docs/` exposes `DesignTokenDocsEngine` for deterministic client/team handoff documentation (`docs/DESIGN_TOKENS.md`, `docs/design_tokens.docs.json`, optional `docs/design_tokens.html`) from `design_tokens.json` and `component_registry.json`, plus planning/execution/validator/audit agents.
Web Project Agents module: `runtime/web_project_agents/` exposes `ProjectClassifier`, `ProjectArchitect`, and `ProjectDeveloper` for classifying technical briefs, producing architecture manifests, and generating code across Python/TypeScript/Go/Rust; planning agents live in `tooll_subagents/planning/project_classifier.md`, `project_architect.md`, and `tooll_subagents/execution/project_developer.md`.
Project starter module: `runtime/project_starter/` exposes `ProjectStarterEngine` + `TemplateManager` for discovering and materializing starter presets under `templates/web_project_agents/`; wired to `tooll_subagents/planning/project_starter_agent.md`.
Code review module: `runtime/code_review/` exposes `CodeReviewer` and `PatchApplier` for deterministic code review and surgical patch application; wired to `tooll_subagents/self_correction/code_review_validator.md` and `diff_patch_applier.md`.
Security scanner module: `runtime/security_scanner/` exposes `SecurityScanner` with regex/hardcoded-credential checks; wired to `tooll_subagents/self_correction/security_scan_validator.md`.
Quality evaluation module: `runtime/quality_evaluation/` exposes `QualityEvaluator` for scoring manifests and generated codebases 1–10; wired to `tooll_subagents/self_correction/quality_evaluator_agent.md`.
Image deploy providers: `runtime/deploy/providers/` exposes `RenderDeployer`, `RailwayDeployer`, and `FlyioDeployer` as optional image/container deploy targets used by `runtime/deploy/DeployEngine` for `render`/`railway`/`flyio` providers; API keys are read from environment only.
Git publisher module: `runtime/git_publisher/` exposes `GitPublisherEngine` for creating GitHub/GitLab repositories and committing generated files; optional dependencies `PyGithub` and `python-gitlab`; wired to `tooll_subagents/planning/git_publish_planner.md` and `tooll_subagents/execution/git_publish_runtime_integrator.md`.
Cost tracking module: `runtime/cost_tracking/` exposes `CostTrackingEngine` + `SQLiteCostBackend` for estimating and recording LLM call costs with per-scope budgets; integrated into `runtime/engine/llm_engine.py` and audited by `tooll_subagents/self_correction/cost_audit_agent.md`.
Notifications module: `runtime/notifications/` exposes `NotificationsEngine` with email/Telegram/Slack channels for pipeline completion alerts; wired to `tooll_subagents/execution/notification_runtime_integrator.md`.
Ponytail protocol: `runtime/engine/ponytail_optimizer.py` injects the 7-step Ladder of Laziness into code-generation system prompts via `ponytail_injector.md`; `ponytail_review.md` validates results for over-engineering; `ponytail_audit.md` provides repository-wide over-engineering audits on `/ponytail-audit`.
`project_rules.md` in repo root is lightweight project context loaded by the runtime; updates require human approval.

## Conventions

- **Naming**: snake_case filenames
- **Directory quirks preserved**: `tooll_subagents` (double "l"), `tools_manangr` (typo in "manager")
- **Algorithmic template** for all agents: `# Agent Name`, `## Role`, `## Contract` (Receives/Returns/Side effects), `## Decision Flow` (numbered steps), `## Failure Modes` (Condition→Response table)
- **Pipeline architecture** varies by category: linear (read), diamond (search), safety-gated (replace), sandboxed (runcom), framework-dispatch (runtest), session-stateful (terminal), analysis-planning (manangr), query-lifecycle (database), request-lifecycle (web), store-lifecycle (memory), headless-automation (browser), quality-lifecycle (lighthouse). tools_* totals 124 agents across 12 categories.
- **No comments** in code unless the WHY is non-obvious; deliberate Ponytail simplifications are marked with `ponytail:` comments naming the ceiling and upgrade path
- **No new files** unless the architecture requires it — prefer editing existing agents
- **Safety first** — any change to execution, control, or safety layers must respect the three-circuit flow
- **Cross-cutting optimizer** — each `tools_*` category has one strategist agent (e.g., `read_optimizer`, `project_optimizer`, `db_optimizer`) that coordinates the pipeline
- **Ponytail protocol** — code-generation agents receive the 7-step Ladder of Laziness in their system prompt (mode `lite`/`full`/`ultra`/`off`); over-engineering is reviewed in self-correction
- **Headroom protocol** — optional context compression for large tool outputs, logs, RAG chunks, and multi-agent handoffs; enabled by default via `HEADROOM_ENABLED`; safety/control/audit layers always receive uncompressed originals unless an explicit compression step is planned
- **Memanto protocol** — optional active semantic memory for durable cross-session facts; enabled via `MEMANTO_ENABLED`/`MEMANTO_URL`; degrades to in-memory fallback when the server is unavailable; safety/control/audit layers never route sensitive data through Memanto unless explicitly allowed by policy
- **Mem0 protocol** — optional hybrid semantic + keyword long-term memory for user preferences, project facts, and session context; enabled via `MEM0_ENABLED`; supports local Chroma/Qdrant (embedded) or Mem0 Cloud (`MEM0_API_KEY`); degrades to in-memory fallback when `mem0ai` is not installed or the API is unreachable; safety/control/audit layers never route sensitive data through Mem0 unless explicitly allowed by policy

## Cross-Session Memory

Memory files live at:
`C:\Users\User\.claude\projects\D--My-head-folders-My-desktop----------Agentic-Loop\memory\`

- `MEMORY.md` — index of all memories
- `project_architecture.md` — complete architecture reference

Read memory when resuming work. Update memory when architecture changes or key decisions are made.

## Current Progress & Next Steps

1. **FILLED (253 agents/files)** — All layers fully implemented:
   - `main_loop.md` (1) — ReAct head agent with Lighthouse hard-gate and Headroom context-compaction integration
   - `orchestrator/` (6) — Router, dispatcher, pipeline coordinator, state manager, API gateway, message bus
   - `safety-control/` (9) — Input sanitization, permissions, threats, leaks, output review, bias, safety assessment, content checking
   - `mutual_check/` (10) — Audit, verification, consistency, validation, performance, quotas, anomalies, quality, feedback, compliance
   - `control/` (7) — File system, network, resources, human oversight, policy, scope, input aggregation
   - `tooll_subagents/` (95) — Full ReAct cycle: user→planning→execution→observability→self_correction→result, including `figma_precise_mode_auditor.md`, `asset_agent.md`, `image_enrichment_agent.md`, `backend_spec_bridge.md`, `responsive_composer.md`, `component_registry.md`, Visual QA V2 refinements in `result_validation.md`, Lighthouse convergence guard in `recursion_or_termination.md`, Ponytail protocol agents (`ponytail_injector.md`, `ponytail_review.md`, `ponytail_audit.md`), Headroom agents (`headroom_injector.md`, `headroom_compressor.md`, `headroom_retriever.md`), Memanto agents (`memanto_remember.md`, `memanto_recall.md`, `memanto_answer.md`), Mem0 agents (`mem0_remember.md`, `mem0_recall.md`, `mem0_list.md`), `/goal` fast-critic `goal_evaluator.md`, i18n agents (`i18n_requirements_analyst.md`, `i18n_language_detector.md`, `i18n_key_extractor.md`, `i18n_dictionary_generator.md`, `i18n_routing_planner.md`, `i18n_component_rewriter.md`, `i18n_optimizer.md`, `i18n_runtime_integrator.md`, `i18n_fallback_resolver.md`, `i18n_rtl_validator.md`, `i18n_missing_key_guard.md`, `i18n_audit_agent.md`), analytics/consent agents (`analytics_requirements_analyst.md`, `analytics_provider_selector.md`, `analytics_event_mapper.md`, `analytics_script_injector.md`, `analytics_optimizer.md`, `analytics_runtime_integrator.md`, `analytics_privacy_validator.md`, `analytics_audit_agent.md`, `cookie_consent_jurisdiction_mapper.md`, `cookie_consent_policy_generator.md`, `cookie_consent_banner_planner.md`, `cookie_consent_blocker.md`), auth/identity agents (`auth_requirements_analyst.md`, `auth_provider_selector.md`, `auth_runtime_integrator.md`, `auth_validator.md`, `auth_audit_agent.md`), CMS/data-query agents (`cms_requirements_analyst.md`, `cms_source_selector.md`, `cms_runtime_integrator.md`, `cms_validator.md`, `cms_audit_agent.md`), accessibility/WCAG agents (`accessibility_requirements_analyst.md`, `accessibility_checker_planner.md`, `accessibility_runtime_integrator.md`, `accessibility_validator.md`, `accessibility_audit_agent.md`), PWA/performance agents (`pwa_requirements_analyst.md`, `pwa_optimizer.md`, `pwa_runtime_integrator.md`, `pwa_validator.md`, `pwa_audit_agent.md`), and design-token docs agents (`design_token_docs_requirements_analyst.md`, `design_token_docs_format_selector.md`, `design_token_docs_runtime_integrator.md`, `design_token_docs_validator.md`, `design_token_docs_audit_agent.md`)
   - `tools_*` (123) — 12 categories × 10+ tool agents each with cross-cutting optimizers, including `tools_browser/headless_automation` (12 agents with `visual_qa_agent.md`) for Playwright-based dynamic web automation and `tools_lighthouse/audit` for Lighthouse 100% hard-gate audits
   - `runtime/accessibility/` — deterministic static WCAG 2.1 audit engine (`AccessibilityEngine`) with `AccessibilityConfig`, `AccessibilityResult`, Tailwind/CSS color parsing, contrast calculation, focus/ARIA/keyboard/heading/alt/form-label checks, and optional async browser hook
   - `runtime/pwa/` — deterministic PWA + performance-budget engine (`PwaEngine`) with `PwaConfig`, `PwaResult`, manifest/service worker/offline-page generation, `srcset`/`sizes` image hints, font-subsetting guidance, JS/CSS/image/font/third-party budget diagnostics, and `next.config.js` patching
   - `runtime/design_token_docs/` — deterministic design-token documentation engine (`DesignTokenDocsEngine`) with `DesignTokenDocsConfig`, `DesignTokenDocsResult`; generates `docs/DESIGN_TOKENS.md`, `docs/design_tokens.docs.json`, and optional `docs/design_tokens.html` from `design_tokens.json` and `component_registry.json`
2. **STUBS (0 agents)** — No remaining placeholders. All agents follow the Algorithmic template.
3. **System status**: COMPLETE — All 6 layers operational with three-circuit safety, full ReAct decomposition, lazy MCP gateway, `project_rules.md` context, headless browser tools, Lighthouse hard-gate pipeline, safe-component generation, Backend Spec Bridge, Responsive Composer, Component Registry, automatic Figma reference download, stable Chromium Visual QA, structural layout checks, conditional ReAct phase transitions, Ponytail cross-cutting optimization protocol, optional Headroom context-compression layer with reversible CCR, MCP tools, and runtime client, optional Memanto semantic-memory pipeline with MCP tools, runtime client, and ReAct integration, optional Mem0 long-term memory pipeline with MCP tools, runtime client, local embedded vector-store support, cloud API support, and ReAct integration, i18n module (`runtime/i18n/`) with next-intl integration and RTL support, analytics/cookie-consent module (`runtime/analytics/`) with multi-provider support and GDPR/ePrivacy/152-FZ/PIPL/CCPA compliance mapping, auth/identity module (`runtime/auth/`) with Clerk/Auth0 Next.js App Router wrappers, CMS/data-query module (`runtime/cms_queries/`) with provider-agnostic Next.js App Router data-layer generation for `blog`/`portfolio`/`cases` across `local_markdown`, Notion, Contentful, Strapi, Prisma, Airtable, Google Sheets, and generic CMS APIs, accessibility/WCAG 2.1 module (`runtime/accessibility/`) with deterministic static audits for contrast, focus, ARIA, keyboard traps, heading hierarchy, alt text, and form labels, PWA/performance-budget module (`runtime/pwa/`) with deterministic manifest/service worker/offline-page generation, `srcset`/`sizes` image hints, font-subsetting guidance, JS/CSS/image/font/third-party budget diagnostics, and `next.config.js` patching, and design-token docs module (`runtime/design_token_docs/`) with deterministic `docs/DESIGN_TOKENS.md`, `docs/design_tokens.docs.json`, and optional `docs/design_tokens.html` generation from `design_tokens.json` and `component_registry.json`.

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

## Internal Agent / Framework Exposure Restriction

All agents, subagents, runtime modules, MCP servers, orchestrators, and any other internal component that lives inside this repository are **strictly internal tooling**. They must perform their agentic roles, but **they must never be served, opened, or exposed as a website** in the browser or via any local/remote server.

Internal artifacts that are forbidden from browser/server exposure include, but are not limited to:
- `.agent_loop/` agent specs and orchestrators (`main_loop.md`, `orchestrator/`, `safety-control/`, `mutual_check/`, `control/`, `tooll_subagents/`).
- Runtime engines and modules (`runtime/`, `figma-agent-core/`).
- MCP servers (`mcp_servers/`).
- Any dashboard, docs site, `website/dist`, TUI, or preview that represents the agent framework itself.

Browser automation, local hosting, preview, and deployment are permitted **only** for the actual website/application/project being built according to its `TECHNICAL_ASSIGNMENT.md`. Before opening any local URL, verify the served directory/process. If it is internal agent infrastructure, refuse to open it and ask the user to stop it and point to the deliverable project's output or dev server.

## Spec Approval Gate

No parallel or sequential sub-agent execution may start until the user has explicitly approved a written specification. The mandatory flow is:

1. `tooll_subagents/planning/task_scoping_agent.md` classifies the task as `trivial`, `medium`, or `large`.
2. For `medium` and `large` tasks, `tooll_subagents/planning/spec_approval_gate.md` conducts an interview, writes a spec, and requires explicit approval. Interview length is capped: trivial = 0 questions, medium ≤ 3 questions, large ≤ 8 questions.
3. `control/spec_lock.md` is a runtime hard gate: if `spec_status != approved`, execution is blocked and the pipeline returns to the spec approval gate.
4. During validation, `tooll_subagents/self_correction/spec_compliance_validator.md` verifies that produced artifacts match the approved spec and that no sub-agent ran before the spec was approved.
5. After completion, `tooll_subagents/observability/gotcha_extractor.md` captures reusable pitfalls and may propose a skill.

Trivial tasks (single concrete action, no ambiguity, no client brief) are exempt from the spec approval gate but are still logged.

### Approval markers

Explicit approval words: `да`, `ok`, `yes`, `продолжай`, `собирай`, `согласен`, `давай`, `+`. Anything else — including silence, "сделай как лучше", "на твоё усмотрение", "выглядит ок", "вроде норм", "давай попробуем", or out-of-context "ок" — is NOT approval.

### Stop-phrase

If the user says "стоп, сначала спека", "стоп, спека", "сначала спека", "не запускай агентов", "stop, spec first", or equivalent, immediately halt any sub-agent dispatch and return to the spec drafting/approval step.

### Human zones

The following stay in the human loop and are never auto-executed: payment, sending money, data deletion, database migrations, bulk emails, deploy/publish, `git push --force`, `rm -rf`, production API keys/secrets, production webhooks. When in doubt, treat the action as irreversible and ask the user.

### Verify-before-handoff rule

Before claiming a result is ready, describe the verification plan and run it — tests, linter, browser, or script. Hand off only after verified output, except for human-zone items.

### Token-limit honesty

Sub-agents consume the same shared token budget as normal chat. Interview → spec → parallel saves tokens by removing guesswork and rework, but does not make the budget infinite. If full parallel is unavailable or hits the rate/window limit, proceed sequentially against the same approved spec.
