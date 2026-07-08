# Agent Loop Architecture

## Overview
Multi-agent AI system with hierarchical safety-first architecture. Central LLM agent orchestrates specialized sub-agents working through API, with strong emphasis on safety and verification at every step.

## Directory Tree

```
.agent_loop/
├── main_loop.md                          # Entry point — ReAct head agent
│
├── orchestrator/                         # API routing layer (6 agents)
│   ├── router.md                         #   Route calls between layers
│   ├── dispatcher.md                     #   Dispatch tasks to tool sub-agents
│   ├── pipeline_coordinator.md           #   Coordinate full pipeline execution
│   ├── state_manager.md                  #   Manage agent state across iterations
│   ├── api_gateway.md                    #   API gateway for external calls
│   └── message_bus.md                    #   Internal message bus
│
├── safety-control/                       # Safety input layer (9 agents)
│   ├── input_sanitizer.md                #   Sanitize user input
│   ├── permission_checker.md             #   Check action permissions
│   ├── command_guard.md                  #   Guard dangerous commands
│   ├── threat_detector.md                #   Detect security threats
│   ├── data_leak_preventer.md            #   Prevent data leaks
│   ├── output_reviewer.md                #   Review agent outputs
│   ├── bias_detector.md                  #   Detect bias in outputs
│   ├── safety_assessor.md                #   Assess action safety
│   ├── content_checker.md                #   Check content compliance
│   └── mutual_check/                     #   Cross-validation layer (10 agents)
│       ├── audit_logger.md               #     Log all actions
│       ├── action_verifier.md            #     Verify action correctness
│       ├── consistency_checker.md        #     Check data consistency
│       ├── result_validator.md           #     Validate results
│       ├── performance_monitor.md        #     Monitor performance
│       ├── quota_manager.md              #     Manage resource quotas
│       ├── anomaly_detector.md           #     Detect anomalies
│       ├── quality_assessor.md           #     Assess output quality
│       ├── feedback_aggregator.md        #     Aggregate feedback
│       └── compliance_checker.md         #     Check regulatory compliance
│
├── control/                              # Runtime control layer (7 agents)
│   ├── file_system_guard.md              #   Guard file system access
│   ├── network_guard.md                  #   Guard network access
│   ├── resource_monitor.md               #   Monitor resource usage
│   ├── human_oversight.md                #   Strategic human oversight
│   ├── policy_enforcer.md                #   Enforce runtime policies
│   ├── scope_manager.md                  #   Manage operation boundaries
│   └── input_aggregation.md              #   Aggregate control inputs
│
├── tooll_subagents/                      # ReAct cycle decomposition
│   ├── user/                             #   Input layer (4 agents)
│   │   ├── request.md                    #     User request
│   │   ├── context.md                    #     Execution context
│   │   ├── limitations.md                #     Known limitations
│   │   └── design_intake.md              #     Detect design-project inputs and emit a design_descriptor
│   ├── planning/                         #   Planning layer (41 agents)
│   │   ├── task_decomposition.md         #     Break down tasks
│   │   ├── cost_risk_assessment.md       #     Assess costs and risks
│   │   ├── tool_plan_selection.md        #     Select tools and plan
│   │   ├── internal_monologue.md         #     Internal reasoning
│   │   ├── figma_design_analyst.md       #     Run Figma pipeline and produce a design_blueprint
│   │   ├── figma_precise_mode_auditor.md #     Builder.io-style readiness audit before Figma-to-code generation
│   │   ├── design_to_code_planner.md     #     Decide technical_assignment vs full_code handoff
│   │   ├── backend_spec_bridge.md        #     Map backend specs to UI and generate backend layer
│   │   ├── responsive_composer.md        #     Generate breakpoint variants and constraint classes for Tailwind AST
│   │   ├── component_registry.md         #     Build Figma Component Registry and generate src/components/ui/*.tsx
│   │   ├── component_mapper.md           #     Map Figma Component Sets to React components and write mapper files
│   │   ├── asset_agent.md                #     Discover, classify and schedule Figma asset downloads
│   │   ├── image_enrichment_agent.md     #     Search/download fallback images for card/hero placeholders
│   │   ├── ponytail_injector.md          #     Inject Ponytail protocol into code-generation system prompts
│   │   ├── ponytail_audit.md             #     Repository-wide over-engineering audit (read-only)
│   │   ├── headroom_injector.md          #     Decide where Headroom context compression should be applied
│   │   ├── i18n_requirements_analyst.md  #     Extract i18n requirements from request/design brief
│   │   ├── i18n_language_detector.md     #     Detect language of Figma text nodes via LLM + heuristics
│   │   ├── i18n_key_extractor.md         #     Convert Figma text nodes to stable namespaced i18n keys
│   │   ├── i18n_dictionary_generator.md  #     Generate translated dictionaries for target locales
│   │   ├── i18n_routing_planner.md       #     Plan Next.js App Router i18n routing strategy
│   │   ├── i18n_component_rewriter.md    #     Manifest to replace literal strings with t() calls
│   │   ├── i18n_optimizer.md             #     Choose SSG/dynamic/lazy-namespace loading strategy
│   │   ├── analytics_requirements_analyst.md # Extract analytics/tracking requirements
│   │   ├── analytics_provider_selector.md    # Select and normalize analytics providers
│   │   ├── analytics_event_mapper.md         # Convert Figma interactions to analytics events
│   │   ├── analytics_script_injector.md      # Plan safe script injection with CSP and consent gating
│   │   ├── analytics_optimizer.md            # Minimize analytics bundle/performance impact
│   │   ├── cookie_consent_jurisdiction_mapper.md # Map locales/jurisdictions to consent rules
│   │   ├── cookie_consent_policy_generator.md    # Generate localized cookie consent policy text
│   │   ├── cookie_consent_banner_planner.md      # Design consent banner UI and categories
│   │   ├── auth_requirements_analyst.md          # Extract identity/auth requirements
│   │   ├── auth_provider_selector.md             # Select Clerk/Auth0 provider and config
│   │   ├── cms_requirements_analyst.md           # Extract dynamic-section CMS requirements
│   │   ├── cms_source_selector.md                # Select CMS source and normalize config
│   │   ├── accessibility_requirements_analyst.md # Extract WCAG 2.1 accessibility requirements
│   │   ├── accessibility_checker_planner.md      # Plan static and browser accessibility checks
│   │   ├── pwa_requirements_analyst.md           # Extract PWA and performance-budget requirements
│   │   ├── pwa_optimizer.md                      # Select manifest/service-worker/offline strategy and resource optimizations
│   │   ├── design_token_docs_requirements_analyst.md # Extract design-token documentation requirements for client/team handoff
│   │   └── design_token_docs_format_selector.md      # Select docs formats (markdown/json/html) and output plan
│   ├── execution/                        #   Execution layer (13 agents)
│   │   ├── tool_invocation.md            #     Invoke selected tool
│   │   ├── safety_guardrails.md          #     Apply safety guardrails
│   │   ├── human_approval.md             #     Tactical human approval gate
│   │   ├── action_logging.md             #     Log execution actions
│   │   ├── i18n_runtime_integrator.md    #     Materialize next-intl config/middleware/messages
│   │   ├── i18n_fallback_resolver.md     #     Resolve missing translations via fallback chain
│   │   ├── analytics_runtime_integrator.md #   Materialize analytics config/consent banner/provider modules
│   │   ├── cookie_consent_blocker.md     #     Block analytics scripts until consent granted
│   │   ├── auth_runtime_integrator.md    #     Materialize Clerk/Auth0 wrappers, sign-in page, env example, middleware
│   │   ├── cms_runtime_integrator.md     #     Materialize CMS data layer, listing/detail pages, card components
│   │   ├── accessibility_runtime_integrator.md # Run static WCAG audit via runtime/accessibility/AccessibilityEngine
│   │   ├── pwa_runtime_integrator.md     #     Materialize PWA manifest/service worker/offline page and performance-budget diagnostics via runtime/pwa/PwaEngine
│   │   └── design_token_docs_runtime_integrator.md # Generate markdown/json/html design-token handoff docs via runtime/design_token_docs/DesignTokenDocsEngine
│   ├── observability/                    #   Observation layer (19 agents)
│   │   ├── environment_result.md         #     Capture environment state
│   │   ├── runtime_output.md             #     Capture runtime output
│   │   ├── file_context.md               #     Capture file changes
│   │   ├── memory_enrichment.md          #     Enrich with memory context
│   │   ├── headroom_compressor.md        #     Compress large artifacts via Headroom CCR
│   │   ├── headroom_retriever.md         #     Restore original content by Headroom hash
│   │   ├── memanto_remember.md           #     Persist durable facts to Memanto semantic memory
│   │   ├── memanto_recall.md             #     Retrieve relevant prior context from Memanto
│   │   ├── memanto_answer.md             #     Synthesize grounded answers from Memanto memory
│   │   ├── mem0_remember.md              #     Persist durable conversation turns/facts to Mem0
│   │   ├── mem0_recall.md                #     Retrieve relevant prior context from Mem0
│   │   ├── mem0_list.md                  #     List all memories stored in Mem0
│   │   ├── i18n_audit_agent.md           #     Audit i18n coverage/compliance/quality
│   │   ├── analytics_audit_agent.md      #     Audit analytics/consent implementation
│   │   ├── auth_audit_agent.md           #     Audit auth/identity implementation
│   │   ├── cms_audit_agent.md            #     Audit CMS/data-query implementation
│   │   ├── accessibility_audit_agent.md  #     Audit accessibility/WCAG 2.1 implementation
│   │   ├── pwa_audit_agent.md            #     Audit PWA manifest, service worker, offline UX, and performance budgets
│   │   └── design_token_docs_audit_agent.md # Audit design-token documentation completeness and audience fit
│   ├── self_correction/                  #   Self-correction layer (14 agents)
│   │   ├── result_validation.md          #     Validate results
│   │   ├── plan_adjustment.md            #     Adjust plan if needed
│   │   ├── recursion_or_termination.md   #     Decide: loop or finish
│   │   ├── assistance_request.md         #     Request human help
│   │   ├── goal_evaluator.md             #     Evaluate progress against a stated goal (/goal fast-critic)
│   │   ├── ponytail_review.md            #     Over-engineering review for generated/refactored code
│   │   ├── i18n_rtl_validator.md         #     Verify RTL layout support
│   │   ├── i18n_missing_key_guard.md     #     Ensure all keys exist in every locale dictionary
│   │   ├── analytics_privacy_validator.md #  Verify analytics privacy/compliance
│   │   ├── auth_validator.md             #     Verify auth/identity wrapper completeness and safety
│   │   ├── cms_validator.md              #     Verify CMS integration completeness and secret safety
│   │   ├── accessibility_validator.md    #     Verify WCAG audit results and emit refinement actions
│   │   ├── pwa_validator.md              #     Verify PWA/performance-budget audit results and emit refinement actions
│   │   └── design_token_docs_validator.md # Verify design-token docs completeness and emit refinement actions
│   └── result/                           #   Output layer (4 agents)
│       ├── solution.md                   #     Final solution
│       ├── modified_files.md             #     List modified files
│       ├── action_report.md              #     Report actions taken
│       └── summary_recommendations.md    #     Summary and recommendations
│
└── tools_*/                              # Tool sub-agents (123 agents across 12 categories)
    ├── tools_read/read_file/             #   File reading — linear pipeline (10 agents + read_optimizer)
    ├── tools_search/search_code/         #   Code search — diamond pipeline (10 agents + search_optimizer)
    ├── tools_replace/replace_in_file/    #   File editing — safety-gated pipeline (10 agents + edit_optimizer)
    ├── tools_runcom/run_command/         #   Command execution — sandboxed pipeline (10 agents + command_optimizer)
    ├── tools_runtest/run_tests/          #   Test running — framework-dispatch pipeline (10 agents + test_optimizer)
    ├── tools_terminal/terminal_io/       #   Terminal I/O — session-stateful pipeline (10 agents + terminal_optimizer)
    ├── tools_manangr/project_manager/    #   Project management — analysis-planning pipeline (10 agents + project_optimizer)
    ├── tools_database/database_query/    #   Database queries — query-lifecycle pipeline (10 agents + db_optimizer)
    ├── tools_web/web_request/            #   Web requests — request-lifecycle pipeline (10 agents + web_optimizer)
    ├── tools_memory/memory_store/        #   Memory storage — store-lifecycle pipeline (10 agents + memory_optimizer)
    ├── tools_browser/headless_automation/  #   Headless browser — automation pipeline (12 agents + browser_optimizer)
    │   ├── session_manager.md            #     Launch/dispose Playwright contexts
    │   ├── navigation_engine.md          #     Load URLs and wait for dynamic content
    │   ├── screenshot_agent.md           #     Capture viewport/full-page/element screenshots
    │   ├── dom_extractor.md              #     Extract dynamic DOM content after JS execution
    │   ├── selector_resolver.md          #     Resolve CSS/XPath selectors with retries
    │   ├── interaction_agent.md          #     Safe clicks, typing, scroll, form submission
    │   ├── network_interceptor.md        #     Capture and filter network traffic
    │   ├── cookie_storage_agent.md       #     Manage cookies/local/session storage
    │   ├── captcha_challenge_agent.md    #     Detect CAPTCHA/login walls and escalate
    │   ├── error_handler.md              #     Classify browser failures and trigger cleanup
    │   ├── visual_qa_agent.md            #     Playwright screenshot + DOM assertions + image diff
    │   └── browser_optimizer.md          #     Batch operations and reuse contexts
    └── tools_lighthouse/audit/           #   Lighthouse hard-gate pipeline (11 agents + lighthouse_optimizer)
        ├── session_manager.md            #     Launch/dispose Playwright contexts for audits
        ├── navigation_engine.md          #     Stabilize page before audit
        ├── audit_runner.md               #     Run Lighthouse via Playwright
        ├── report_parser.md              #     Filter 500 KB report down to failed audits
        ├── metric_guard_performance.md   #     Enforce Performance = 100%
        ├── metric_guard_a11y.md          #     Enforce Accessibility = 100%
        ├── metric_guard_best_practices.md #     Enforce Best Practices = 100%
        ├── metric_guard_seo.md           #     Enforce SEO = 100%
        ├── correction_prompt_builder.md  #     Build compact correction prompt
        ├── loop_terminator.md            #     Convergence guard (8 iterations max)
        └── lighthouse_optimizer.md       #     Pipeline strategist and log rotation
```

## Flow

```
User Request
  → main_loop.md
    → orchestrator/router.md
      → safety-control/ (input sanitization, permission check, threat detection)
        → safety-control/mutual_check/ (cross-validation)
          → control/ (scope, policy, resource enforcement)
            → orchestrator/dispatcher.md
              → tooll_subagents/user/ (user context + project_rules.md + design_intake)
              → tooll_subagents/planning/ (task decomposition + figma_design_analyst [orchestrates figma_precise_mode_auditor, asset_agent, image_enrichment_agent, i18n_language_detector, i18n_key_extractor, i18n_dictionary_generator, i18n_optimizer, analytics_event_mapper] + design_to_code_planner [orchestrates i18n_requirements_analyst, i18n_routing_planner, i18n_component_rewriter, analytics_requirements_analyst, analytics_provider_selector, cookie_consent_jurisdiction_mapper, cookie_consent_policy_generator, analytics_script_injector, cookie_consent_banner_planner, analytics_optimizer, auth_requirements_analyst, auth_provider_selector, cms_requirements_analyst, cms_source_selector, accessibility_requirements_analyst, accessibility_checker_planner, pwa_requirements_analyst, pwa_optimizer, design_token_docs_requirements_analyst, design_token_docs_format_selector] + memanto_recall)
              → tooll_subagents/execution/ (tool invocation [i18n_runtime_integrator, i18n_fallback_resolver, analytics_runtime_integrator, cookie_consent_blocker, auth_runtime_integrator, cms_runtime_integrator, accessibility_runtime_integrator, pwa_runtime_integrator, design_token_docs_runtime_integrator])
                → tools_*/ (specialized tool agents)
                → tools_browser/headless_automation (Playwright dynamic pages + visual_qa_agent)
                → tools_lighthouse/audit (Lighthouse hard-gate audit + report parsing + correction prompts)
                → runtime/accessibility/AccessibilityEngine (static WCAG 2.1 contrast/focus/ARIA/keyboard/heading/alt/form-label checks)
                → runtime/pwa/PwaEngine (manifest/service worker/offline page + srcset/font-subsetting + JS/CSS/image/font/third-party budget diagnostics)
                → runtime/design_token_docs/DesignTokenDocsEngine (markdown/json/html design-token handoff documentation from component_registry/design_tokens.json)
                → mcp_servers/gateway.py (lazy MCP dispatch)
                → mcp_servers/figma_server.py (Figma-to-code pipeline)
                → mcp_servers/headroom_server.py (optional Headroom context-compression CCR tools)
                → mcp_servers/memanto_server.py (optional Memanto semantic-memory tools)
                → mcp_servers/mem0_server.py (optional Mem0 long-term memory tools)
              → tooll_subagents/observability/ (result capture + memanto_remember + mem0_remember + i18n_audit_agent + analytics_audit_agent + auth_audit_agent + cms_audit_agent + accessibility_audit_agent + pwa_audit_agent, design_token_docs_audit_agent)
              → tooll_subagents/self_correction/ (validate [result_validation + goal_evaluator + visual_qa_agent + i18n_rtl_validator + i18n_missing_key_guard + analytics_privacy_validator + auth_validator + cms_validator + accessibility_validator + pwa_validator, design_token_docs_validator] → adjust → loop or finish)
                → PhaseTransitionManager (runtime conditional phase routing)
              → tooll_subagents/result/ (final output + memanto_answer + mem0_recall + action_report with audit summaries)
  → User Response
```

## Agent Counts

| Layer | Count |
|---|---|
| main_loop | 1 |
| orchestrator | 6 |
| safety-control | 9 |
| safety-control/mutual_check | 10 |
| control | 7 |
| tooll_subagents | 95 |
| tools_* | 123 |
| **Total** | **253** |

## Naming Convention
- snake_case filenames
- Each agent follows the **Algorithmic template**: `# Agent Name`, `## Role`, `## Contract` (Receives/Returns/Side effects), `## Decision Flow` (numbered steps), `## Failure Modes` (Condition→Response table)
- Directory spelling: `tooll_subagents` (double "l"), `tools_manangr` (typo preserved)

## Key Decisions
1. Three-circuit safety: safety-control → mutual_check → control
2. ReAct cycle decomposed into atomic sub-steps per folder
3. Tools as microservices: 12 categories × 10+ agents with optimizer per category
4. Self-correction loop closes the cycle (validate → adjust → loop/terminate)
5. Human-in-the-loop split: strategic oversight (control) vs tactical approval (execution)
6. Double "l" in `tooll_subagents` and "manangr" typo preserved as-is in codebase
7. Lazy MCP gateway: `mcp_servers/gateway.py` exposes category metadata to the planner and materializes servers only when a tool is invoked, reducing planner token budget
8. `project_rules.md` in repo root is lightweight context loaded at session start and used as fallback policy source by `control/policy_enforcer.md`; updates require `human_approval.md`
9. Headless browser category: `tools_browser/headless_automation` adds Playwright-based dynamic page automation as the 11th tool category; runtime-only `mcp_servers/browser_server.py` keeps it optional and lazy
10. Lighthouse category: `tools_lighthouse/audit` adds a 12th tool category that runs Lighthouse via Playwright, parses reports, enforces 100% hard gate across Performance, Accessibility, Best Practices, and SEO, and feeds compact correction prompts back into the self-correction loop with a default convergence guard of 8 iterations
11. Conditional Edges: `runtime/engine/pipeline_runner.py` uses a `PhaseTransitionManager` to route between ReAct phases based on agent outputs instead of a hardcoded sequence
12. Ponytail protocol: `runtime/engine/ponytail_optimizer.py` injects the 7-step Ladder of Laziness into code-generation system prompts via `ponytail_injector.md`, while `ponytail_review.md` and `ponytail_audit.md` provide over-engineering review and audit capabilities
13. Headroom protocol: optional local LLM CCR layer exposed as MCP category `headroom` (`headroom_compress`, `headroom_retrieve`, `headroom_stats`) and as `runtime/engine/headroom_client.py`; integrated into ReAct planning, execution, observability, and `main_loop.md` context compaction; degrades to plaintext passthrough when `headroom-ai` is not installed
14. Memanto protocol: optional active semantic-memory agent exposed as MCP category `memanto` (`memanto_create_agent`, `memanto_remember`, `memanto_recall`, `memanto_answer`) and as `runtime/engine/memanto_client.py`; integrated into ReAct planning recall, observability remember, and end-of-session answer; degrades to in-memory fallback when the Memanto server is unreachable. Optional dependency: `runtime/requirements-memanto.txt`
15. Mem0 protocol: optional long-term memory layer exposed as MCP category `mem0` (`mem0_add`, `mem0_search`, `mem0_get_all`, `mem0_delete`) and as `runtime/engine/mem0_client.py`; integrated into ReAct planning recall, observability remember, and session cleanup; degrades to in-memory fallback when `mem0ai` is not installed or the API is unreachable. Optional dependency: `runtime/requirements-mem0.txt`
16. Runtime filesystem guard: `runtime/safety/file_system_guard.py` enforces deterministic filesystem boundaries inside `runtime/engine/pipeline_runner.py`; write/delete operations are blocked outside allowed directories and protected components such as `.ssh`, `.env`, and system paths are rejected before MCP tools execute
17. Runtime network guard: `runtime/safety/network_guard.py` enforces deterministic egress policy inside `runtime/engine/pipeline_runner.py`; only explicitly allowed domains/hosts may be reached, private/internal networks and metadata endpoints are blocked, and unknown egress is denied by default before web/browser MCP tools execute
18. Runtime resource monitor: `runtime/observability/resource_monitor.py` samples CPU, memory, and workspace disk usage at pipeline start and before each ReAct execution iteration; CRITICAL levels abort the run to prevent host exhaustion, while optional `psutil` falls back to `shutil.disk_usage` so disk watchdog remains operational on minimal installs
19. Audit logger: `runtime/safety/audit_logger.py` is mandatory, append-only, and tamper-evident. Every pipeline run receives an `audit_anchor` that is written into each audit entry; entries are persisted as a SHA-256 hash chain so deletion or modification of any line invalidates `verify_chain()`. PipelineRunner logs pipeline start/end, agent invocation/completion/failure, MCP tool execution, and safety-blocked events into `{workspace}/.audit/audit_YYYY-MM-DD.jsonl`
20. Full safety-control pre-check: `runtime/engine/pipeline_runner.py` `SAFETY_AGENTS` now invokes all 9 `safety-control` agents (`input_sanitizer`, `threat_detector`, `permission_checker`, `command_guard`, `data_leak_preventer`, `output_reviewer`, `bias_detector`, `content_checker`, `safety_assessor`) plus `control/scope_manager.md` and `control/policy_enforcer.md`. Blocked verdicts from heterogeneous agent outputs (`verdict=block`, `review_status=rejected`, `compliance_status=major_violation/blocked`, `execution_recommendation=block`, `recommendation=escalate`, `action=block`, `blocked=true`) uniformly abort the pipeline.
21. Full mutual-check validation: `runtime/engine/pipeline_runner.py` `MUTUAL_CHECK_AGENTS` now invokes all 10 `safety-control/mutual_check` agents (`consistency_checker`, `result_validator`, `quality_assessor`, `action_verifier`, `performance_monitor`, `quota_manager`, `anomaly_detector`, `feedback_aggregator`, `compliance_checker`, `audit_logger`) during the `mutual_check` phase. The shared context carries result text, session ID, iteration count, tools used, token consumption, and elapsed time.
22. i18n module: `runtime/i18n/` provides deterministic Next.js `next-intl` integration (`I18nIntegrationEngine`) with locale routing, RTL support, key extraction/namespace utilities, and dictionary generation. Planning agents in `tooll_subagents/planning/` extract requirements, detect Figma text languages, build key registries, and plan component rewrites. Self-correction agents (`i18n_rtl_validator.md`, `i18n_missing_key_guard.md`) and observability (`i18n_audit_agent.md`) enforce quality and compliance.
23. Analytics and cookie consent module: `runtime/analytics/` provides deterministic analytics provider integration and consent UI generation (`AnalyticsIntegrationEngine`) with GDPR/ePrivacy/152-FZ/PIPL/CCPA jurisdiction mapping, default-deny categories, CSP directives, and provider modules for GA4, Yandex, Plausible, PostHog, and Mixpanel. Planning agents select providers, map events, generate policies, and design banners. Execution agents (`analytics_runtime_integrator.md`, `cookie_consent_blocker.md`) materialize code; self-correction (`analytics_privacy_validator.md`) and observability (`analytics_audit_agent.md`) enforce privacy rules.
24. Auth/identity module: `runtime/auth/` provides deterministic Clerk/Auth0 integration (`AuthIntegrationEngine`) for SaaS landing pages and personal sites, generating `src/components/auth/AuthProvider.tsx`, `SignInButton.tsx`, `UserButton.tsx`, `ProtectedRoute.tsx`, `src/app/sign-in/page.tsx`, `.env.local.example`, and `middleware.ts` only when none exists. Planning agents (`auth_requirements_analyst.md`, `auth_provider_selector.md`) extract requirements and choose the provider; execution (`auth_runtime_integrator.md`) materializes wrappers; self-correction (`auth_validator.md`) and observability (`auth_audit_agent.md`) verify completeness and secret safety.
25. CMS/data queries module: `runtime/cms_queries/` provides provider-agnostic Next.js App Router data-layer generation (`CmsQueriesEngine`) for dynamic sections (`blog`, `portfolio`, `cases`). It supports `local_markdown` (working frontmatter loader), `notion`, `contentful`, `strapi`, `prisma`, `airtable`, `google_sheets`, and generic `cms_api` with static fallback and SDK dependency injection. Planning agents (`cms_requirements_analyst.md`, `cms_source_selector.md`) extract requirements and choose the source; execution (`cms_runtime_integrator.md`) materializes the typed wrappers, listing/detail pages, card components, and `.env.local.example`; self-correction (`cms_validator.md`) and observability (`cms_audit_agent.md`) verify completeness and secret safety.
26. Accessibility/WCAG 2.1 module: `runtime/accessibility/` provides deterministic static accessibility audits (`AccessibilityEngine`) for generated Next.js files. It supports `WCAG21_A`/`WCAG21_AA`/`WCAG21_AAA` levels and checks for contrast, focus visibility, focus order, ARIA roles/required attributes/unique IDs/valid references, keyboard traps, heading hierarchy, alt text, and form label associations. It parses `tailwind.config.ts` theme colors, `globals.css` CSS variables, and TSX className/inline styles to compute approximate contrast ratios without requiring Playwright. Planning agents (`accessibility_requirements_analyst.md`, `accessibility_checker_planner.md`) extract requirements and build the check plan; execution (`accessibility_runtime_integrator.md`) runs the engine; self-correction (`accessibility_validator.md`) translates violations into refinement actions; observability (`accessibility_audit_agent.md`) produces the final compliance report.
27. PWA + performance budget module: `runtime/pwa/` provides deterministic PWA artifact generation and performance-budget diagnostics (`PwaEngine`) for generated Next.js files. It emits `manifest.json`, `sw.js`, `offline.html`, `src/lib/pwa.ts`, `src/lib/pwa-meta.ts`, and `src/components/PwaRegister.tsx`; diagnoses JS/CSS/image/font/third-party budgets; suggests `srcset`/`sizes` for images and font subsetting; and patches `next.config.js` (`poweredByHeader: false`). Planning agents (`pwa_requirements_analyst.md`, `pwa_optimizer.md`) extract requirements and choose strategy; execution (`pwa_runtime_integrator.md`) materializes artifacts and diagnostics; self-correction (`pwa_validator.md`) translates budget violations into refinement actions; observability (`pwa_audit_agent.md`) produces the final PWA/performance compliance report.
28. Design token documentation module: `runtime/design_token_docs/` provides deterministic client/team handoff documentation (`DesignTokenDocsEngine`) from `component_registry/design_tokens.json`. It emits `docs/DESIGN_TOKENS.md`, `docs/design_tokens.docs.json`, and optionally `docs/design_tokens.html` with color tables, typography scales, component linkage, and Figma style/variable token mappings. Planning agents (`design_token_docs_requirements_analyst.md`, `design_token_docs_format_selector.md`) extract requirements and choose formats; execution (`design_token_docs_runtime_integrator.md`) materializes docs; self-correction (`design_token_docs_validator.md`) verifies completeness; observability (`design_token_docs_audit_agent.md`) checks audience fit.

## Implementation Status

All 253 agents/files are fully implemented following the Algorithmic template:
- `main_loop.md` (1) — ReAct head agent orchestrating the full cycle with conditional phase transitions, Lighthouse hard-gate integration, and Headroom context-compaction integration
- `orchestrator/` (6) — router, dispatcher, pipeline_coordinator, state_manager, api_gateway, message_bus
- `safety-control/` (9) — input_sanitizer, permission_checker, command_guard, threat_detector, data_leak_preventer, output_reviewer, bias_detector, safety_assessor, content_checker
- `safety-control/mutual_check/` (10) — audit_logger, action_verifier, consistency_checker, result_validator, performance_monitor, quota_manager, anomaly_detector, quality_assessor, feedback_aggregator, compliance_checker
- `control/` (7) — file_system_guard, network_guard, resource_monitor, human_oversight, policy_enforcer, scope_manager, input_aggregation
- `tooll_subagents/` (95) — Full ReAct cycle across 6 phases: user (4 with `design_intake.md`), planning (41 with `figma_design_analyst.md`, `figma_precise_mode_auditor.md`, `design_to_code_planner.md`, `backend_spec_bridge.md`, `responsive_composer.md`, `component_registry.md`, `component_mapper.md`, `asset_agent.md`, `image_enrichment_agent.md`, `ponytail_injector.md`, `ponytail_audit.md`, `headroom_injector.md`, `i18n_requirements_analyst.md`, `i18n_language_detector.md`, `i18n_key_extractor.md`, `i18n_dictionary_generator.md`, `i18n_routing_planner.md`, `i18n_component_rewriter.md`, `i18n_optimizer.md`, `analytics_requirements_analyst.md`, `analytics_provider_selector.md`, `analytics_event_mapper.md`, `analytics_script_injector.md`, `analytics_optimizer.md`, `cookie_consent_jurisdiction_mapper.md`, `cookie_consent_policy_generator.md`, `cookie_consent_banner_planner.md`, `auth_requirements_analyst.md`, `auth_provider_selector.md`, `cms_requirements_analyst.md`, `cms_source_selector.md`, `accessibility_requirements_analyst.md`, `accessibility_checker_planner.md`, `pwa_requirements_analyst.md`, `pwa_optimizer.md`, `design_token_docs_requirements_analyst.md`, and `design_token_docs_format_selector.md`), execution (13 with `i18n_runtime_integrator.md`, `i18n_fallback_resolver.md`, `analytics_runtime_integrator.md`, `cookie_consent_blocker.md`, `auth_runtime_integrator.md`, `cms_runtime_integrator.md`, `accessibility_runtime_integrator.md`, `pwa_runtime_integrator.md`, and `design_token_docs_runtime_integrator.md`), observability (19 with `headroom_compressor.md`, `headroom_retriever.md`, `memanto_remember.md`, `memanto_recall.md`, `memanto_answer.md`, `mem0_remember.md`, `mem0_recall.md`, `mem0_list.md`, `i18n_audit_agent.md`, `analytics_audit_agent.md`, `auth_audit_agent.md`, `cms_audit_agent.md`, `accessibility_audit_agent.md`, `pwa_audit_agent.md`, and `design_token_docs_audit_agent.md`), self_correction (14 with `goal_evaluator.md`, `ponytail_review.md`, `i18n_rtl_validator.md`, `i18n_missing_key_guard.md`, `analytics_privacy_validator.md`, `auth_validator.md`, `cms_validator.md`, `accessibility_validator.md`, `pwa_validator.md`, and `design_token_docs_validator.md`), result (4)
- `tools_*` (123) — 12 categories × 10+ agents each with cross-cutting optimizers, including `tools_browser/headless_automation` for Playwright-based dynamic web automation and `tools_lighthouse/audit` for Lighthouse 100% hard-gate audits
- `runtime/accessibility/` — deterministic static WCAG 2.1 audit engine (`AccessibilityEngine`) with `AccessibilityConfig`/`AccessibilityResult`, Tailwind/CSS color parsing, contrast calculation, focus/ARIA/keyboard/heading/alt/form-label checks, and optional async browser hook
- `runtime/pwa/` — deterministic PWA + performance-budget engine (`PwaEngine`) with `PwaConfig`/`PwaResult`, manifest/service worker/offline-page generation, `srcset`/`sizes` image hints, font-subsetting guidance, JS/CSS/image/font/third-party budget diagnostics, and `next.config.js` patching
- `runtime/design_token_docs/` — deterministic design-token documentation engine (`DesignTokenDocsEngine`) with `DesignTokenDocsConfig`/`DesignTokenDocsResult`; generates `docs/DESIGN_TOKENS.md`, `docs/design_tokens.docs.json`, and optional `docs/design_tokens.html` from `design_tokens.json` and `component_registry.json`
- `mcp_servers/figma_server.py` — lazy MCP wrapper around `figma-agent-core/` exposing the Figma-to-code pipeline, including design-token extraction (`figma_extract_tokens`), component registry (`figma_build_component_registry`), reusable component extraction (`figma_extract_components`), responsive breakpoint composition (`figma_responsive_compose`), and Playwright-based Visual QA with automatic Figma reference download and structural layout checks
- `mcp_servers/backend_server.py` — lazy MCP wrapper around the Backend Spec Bridge, exposing `backend_run_bridge` for fullstack UI+backend generation
- `mcp_servers/memanto_server.py` — lazy MCP wrapper around `runtime/engine/memanto_client.py` exposing `memanto_create_agent`, `memanto_remember`, `memanto_recall`, and `memanto_answer`; degrades to in-memory fallback when the Memanto server is unreachable
- `mcp_servers/mem0_server.py` — lazy MCP wrapper around `runtime/engine/mem0_client.py` exposing `mem0_add`, `mem0_search`, `mem0_get_all`, and `mem0_delete`; degrades to in-memory fallback when `mem0ai` is not installed or the API is unreachable

Zero remaining stubs. All 253 agent specs include Role, Contract, Decision Flow, and Failure Modes.

## Runtime / MCP

- `runtime/engine/pipeline_runner.py` — loads `project_rules.md` at session start and injects it into planning; creates `mcp_servers/gateway.py` with lazy server factories.
- `runtime/engine/llm_engine.py` — `LLMConfig.mcp_enabled` flag controls whether MCP categories are presented to the planner.
- `mcp_servers/registry.py` — supports eager and lazy server registration; lazy registration keeps category metadata without holding live server instances.
- `mcp_servers/bootstrap.py` — `--eager` flag for `--test`/`--serve`; default lazy mode constructs servers only on first tool call.
- `mcp_servers/gateway.py` — exposes `categories()`, `category_metadata()`, `tools_for_category()`, and `execute()` without loading unused servers.
- `mcp_servers/browser_server.py` — optional Playwright-based browser automation server; lazy-loaded and falls back gracefully if Playwright is unavailable.
- `mcp_servers/figma_server.py` — optional Figma-to-code pipeline server wrapping `figma-agent-core/`; lazy-loaded and reports degraded if `figma-agent-core/` is missing or `FIGMA_TOKEN`/`FIGMA_URL` are unset.
- `mcp_servers/backend_server.py` — optional Backend Spec Bridge server wrapping `figma-agent-core/backend_bridge.py`; lazy-loaded and reports degraded if `figma-agent-core/` is missing or no backend spec is provided.
- `runtime/requirements-browser.txt` — optional Playwright dependency file; core `runtime/requirements.txt` stays lightweight.
- `runtime/requirements-memanto.txt` — optional Memanto SDK/server dependency file.
- `runtime/requirements-mem0.txt` — optional Mem0 Python SDK dependency file.
- `runtime/engine/memanto_client.py` — singleton HTTP client for Memanto REST API with in-memory fallback when the server is unavailable.
- `runtime/engine/mem0_client.py` — singleton wrapper around the `mem0ai` `Memory`/`MemoryClient` classes with in-memory fallback when the SDK/API is unavailable.
- `runtime/engine/pipeline_runner.py` — also hosts `PhaseTransitionManager` for conditional ReAct phase routing.
- `runtime/i18n/engine.py` — deterministic `next-intl` integration engine; generates `middleware.ts`, `i18n/routing.ts`, `i18n/request.ts`, `messages/*.json`, `app/[locale]/layout.tsx`, and applies component rewrite manifests.
- `runtime/i18n/config.py` — `I18nConfig`, routing/locale/fallback/load-strategy enums, and validation.
- `runtime/i18n/key_namespace.py` — i18n key extraction, namespace normalization, deduplication, and nested dictionary generation.
- `runtime/i18n/rtl_config.py` — RTL locale detection (`ar`, `he`, `fa`, `ur`, etc.).
- `runtime/analytics/engine.py` — deterministic analytics/consent integration engine; generates `src/lib/analytics.ts`, `src/lib/consent-store.ts`, `src/components/CookieConsent.tsx`, provider modules, and CSP headers.
- `runtime/analytics/categories.py` — consent categories, jurisdiction default-deny rules, and provider-to-category mapping.
- `runtime/analytics/csp_helper.py` — CSP `script-src`/`connect-src`/`img-src` directive builder for enabled providers.
- `runtime/cms_queries/engine.py` — deterministic CMS/data-query integration engine for Next.js App Router; generates `src/lib/cms.ts`, `src/lib/cms/localMarkdown.ts`, `src/lib/cms/staticFallback.ts`, card components under `src/components/cms/`, listing and detail pages under `src/app/{blog,portfolio,cases}/`, `.env.local.example`, and injects SDK dependencies for external sources.
- `runtime/cms_queries/config.py` — `CmsSource`, `CmsSourceId`, and source validation.
- `runtime/cms_queries/__init__.py` — public exports for `CmsSource`, `CmsSourceId`, `CmsQueriesEngine`, and `CmsQueriesResult`.
- `runtime/auth/engine.py` — deterministic Clerk/Auth0 integration engine; generates `src/components/auth/AuthProvider.tsx`, `SignInButton.tsx`, `UserButton.tsx`, `ProtectedRoute.tsx`, `src/app/sign-in/page.tsx`, `.env.local.example`, and `middleware.ts` only when none exists.
- `runtime/auth/config.py` — `AuthProvider` dataclass with provider id, optional keys, public/protected path lists, and validation.
- `runtime/accessibility/engine.py` — deterministic static WCAG 2.1 audit engine; parses Tailwind theme colors and CSS variables, computes text/background contrast ratios, and audits generated Next.js files for focus visibility, focus order, ARIA labels, keyboard traps, heading hierarchy, alt text, and form label associations.
- `runtime/accessibility/config.py` — `AccessibilityConfig` with `WcagLevel` enum, configurable check list, and contrast thresholds.
- `runtime/accessibility/__init__.py` — public exports for `AccessibilityConfig`, `AccessibilityEngine`, `AccessibilityResult`, `WcagLevel`, `contrast_ratio`, and `hex_to_luminance`.
- `project_rules.md` — lightweight project-level context file in repo root (Scope, Conventions, Tooling Preferences, Safety Defaults, Human-in-the-Loop Triggers).

### MCP Servers

All 16 MCP servers are registered in `mcp_servers/bootstrap.py` and discovered through `mcp_servers/registry.py`. Default mode is **lazy**: `mcp_servers/gateway.py` exposes category metadata and materializes a server only when one of its tools is actually invoked. Use `python -m mcp_servers.bootstrap --test` to run self-tests on all 16 servers; the test accepts `degraded` status for optional servers when their external dependency is missing.

| Category | Server file | Exposed tools | Required / Optional | Dependencies / Env | Degraded behavior |
|---|---|---|---|---|---|
| `tools_read` | `mcp_servers/read_server.py` | 9 | Required | Core `runtime/requirements.txt` (stdlib + `anthropic`, `openai`, `rich`, `numpy`, `pytest`) | None — loaded eagerly in all runtime modes |
| `tools_search` | `mcp_servers/search_server.py` | 8 | Required | Core requirements | None |
| `tools_replace` | `mcp_servers/replace_server.py` | 10 | Required | Core requirements | None |
| `tools_runcom` | `mcp_servers/runcom_server.py` | 9 | Required | Core requirements | None |
| `tools_runtest` | `mcp_servers/runtest_server.py` | 8 | Required | Core requirements | None |
| `tools_terminal` | `mcp_servers/terminal_server.py` | 9 | Required | Core requirements | None |
| `tools_manangr` | `mcp_servers/manangr_server.py` | 8 | Required | Core requirements | None |
| `tools_database` | `mcp_servers/database_server.py` | 12 | Required | Core requirements (uses stdlib `sqlite3`) | None |
| `tools_web` | `mcp_servers/web_server.py` | 10 | Required | Core requirements | None |
| `tools_memory` | `mcp_servers/memory_server.py` | 11 | Required | Core requirements | None |
| `tools_browser` | `mcp_servers/browser_server.py` | 10 | Optional | `playwright>=1.40.0` + `playwright install` (`runtime/requirements-browser.txt`) | Reports `status: degraded`; planner falls back to `tools_web` for static content |
| `figma` | `mcp_servers/figma_server.py` | 12 | Optional | `figma-agent-core/` directory; env `FIGMA_TOKEN`, `FIGMA_URL`, optional `FIGMA_NODE_ID` | Reports `status: degraded`; requires install of `figma-agent-core` and setting token/url before live Figma calls |
| `backend` | `mcp_servers/backend_server.py` | 7 | Optional | `figma-agent-core/` directory; one of `openapi`, `prisma`, or `text_spec` arguments | Reports `status: degraded` if `figma-agent-core/` is missing; otherwise runs only when a backend spec is provided |
| `headroom` | `mcp_servers/headroom_server.py` | 3 | Optional | `headroom-ai>=0.1.0` (`runtime/requirements-headroom.txt`); env `HEADROOM_ENABLED`, `HEADROOM_MODEL`, `HEADROOM_SESSION_TTL` | Reports `status: degraded`; `runtime/engine/headroom_client.py` falls back to plaintext passthrough |
| `memanto` | `mcp_servers/memanto_server.py` | 4 | Optional | `memanto>=0.1.0`, `moorcheh-sdk>=1.3.7` (`runtime/requirements-memanto.txt`); running Memanto server; env `MEMANTO_ENABLED`, `MEMANTO_BASE_URL`, `MEMANTO_API_KEY`, `MEMANTO_AGENT_ID` | Reports `status: degraded`; `runtime/engine/memanto_client.py` falls back to in-memory store |
| `mem0` | `mcp_servers/mem0_server.py` | 4 | Optional | `mem0ai>=0.2.0`, `openai>=1.90.0`, `chromadb>=0.4.24` (or `qdrant-client`) (`runtime/requirements-mem0.txt`); env `MEM0_ENABLED`, `MEM0_API_KEY`, `MEM0_HOST`, `MEM0_VECTOR_STORE`, `MEM0_VECTOR_STORE_PATH`, optional `MEM0_USER_ID`/`MEM0_AGENT_ID`/`MEM0_APP_ID`/`MEM0_RUN_ID` | Reports `status: degraded`; `runtime/engine/mem0_client.py` falls back to in-memory store |

Optional servers still register their tools in lazy mode, so the planner sees them as available categories. When invoked, they return a structured `degraded` response rather than throwing, letting the ReAct loop fall back or continue without external dependencies. `tools_lighthouse/audit` is intentionally **not** an MCP server; it is a headless-browser agent pipeline invoked by `tooll_subagents/self_correction/result_validation.md` and consumes the same Playwright dependency as `tools_browser`.

## Validation

### Cross-Reference Integrity

All 253 agents are wired into a single reference graph. Every agent is reachable from at least one other agent, and no agent references a missing file.

**Test results (2026-07-08):**
- Broken links: 0 (6 known false positives filtered — `README.md`, `API.md`, `CHANGELOG.md`, `MEMORY.md`, `project_rules.md` are documentation targets, not agents)
- Isolated agents: 0 (previously 2; fixed by adding `i18n_audit_agent.md` and `analytics_audit_agent.md` references into `action_report.md` and `memory_enrichment.md`; auth agents wired through `design_to_code_planner.md` and `tool_plan_selection.md`)
- i18n and analytics/cookie-consent runtime tests pass after aligning `DecisionFlow`, engine paths, key namespace, and agent wording.
- CI `.github/workflows/ci.yml` runs pytest by tiers: `core` (~296 tests, <45 s), `mcp` (~180 tests, <5 s), and `tests/integration/` (mock pipeline, <12 s). Figma tier (`~385 tests`) is excluded from mandatory CI because it requires `FIGMA_TOKEN`/`FIGMA_URL` and live network access; it can be run manually or in a scheduled job.
- Script: `.agent_loop/scripts/validate_cross_references.js` — run with `node .agent_loop/scripts/validate_cross_references.js` to re-check after any edit

**Top referenced agents:**
- `audit_logger.md` — referenced by 23 agents (central logging backbone)
- `resource_monitor.md` — referenced by 18 agents (resource governance)
- `anomaly_detector.md` — referenced by 15 agents (behavioral forensics)
- `state_manager.md` — referenced by 14 agents (session persistence)
- `human_oversight.md` — referenced by 12 agents (strategic approval)
