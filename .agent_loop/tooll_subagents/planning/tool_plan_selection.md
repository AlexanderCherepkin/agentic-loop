# Tool Plan Selection

## Role
Dispatch-planning agent that selects the optimal sequence of tool categories and specific tool agents for each sub-task in the task graph. Resolves ambiguities from `task_decomposition.md` and ensures tool compatibility across the pipeline.

## Contract

### Receives
- `task_graph`: from `task_decomposition.md`
- `cost_risk_assessment`: from `cost_risk_assessment.md`
- `available_tools`: current inventory of functional tool agents with status and capability metadata
- `project_rules`: from `user/context.md` — lightweight project-level rules
- `mcp_categories`: list of available MCP category names (lazy metadata, no full tool descriptions)
- `execution_policy`: enum (`speed_priority`, `accuracy_priority`, `cost_priority`, `safety_priority`)

### Returns
- `tool_plan`: ordered list of tool invocations with parameters, expected outputs, fallback tools, `model_tier`, and `volume_cap`
- `pipeline_compatibility`: boolean — whether all selected tools can chain without format mismatch
- `contingency_plan`: list of tool substitutions if primary tool fails
- `estimated_end_to_end_latency`: milliseconds or relative time units
- `model_tier_plan`: map of tool/agent → recommended model tier (`fast`, `balanced`, `strong`)
- `volume_caps`: map of batched/parallel tool → cap value (`MAX`, `CHUNK`, `MAX_CHUNKS`)

### Side Effects
- Updates tool selection telemetry for future optimization
- Logs plan to `audit_logger.md`

## Decision Flow

1. **Iterate sub-tasks** — for each node in `task_graph` critical path and parallel groups.
2. **Map to tool categories** — use capability matrix: read → `tools_read`, search → `tools_search`, write → `tools_replace`, execute → `tools_runcom`, test → `tools_runtest`, terminal → `tools_terminal`, browse/render/screenshot/dynamic_page → `tools_browser`, mcp → `mcp_servers/gateway.py`, design_project/Figma ingestion → `figma` MCP category (`figma_bootstrap`, `figma_analyze`, `figma_generate_spec`, `figma_extract_tokens`, `figma_responsive_compose`, `figma_build_component_registry`, `figma_extract_components`, `figma_map_interactions`, `figma_generate_component`, `figma_download_assets`, `figma_run_pipeline`) and `tooll_subagents/planning/responsive_composer.md` for breakpoint variant planning, `tooll_subagents/planning/component_registry.md` for Component Set/Variant planning, and `tooll_subagents/planning/asset_agent.md` for asset-download planning (batching, 429 backoff, skip-existing, optimization). backend specification mapping → `backend` MCP category (`backend_analyze_spec`, `backend_map_ui`, `backend_generate_routes`, `backend_generate_actions`, `backend_sync_schema`, `backend_run_bridge`), etc. If `project_rules.tooling_preferences` is present, boost rank of preferred tools and demote discouraged/disallowed ones; if a required tool is discouraged, escalate to `control/policy_enforcer.md`. Only include MCP categories listed in `mcp_categories` to avoid loading servers for unused capabilities; when a `design_blueprint` is present, `mcp_categories` must include `figma`; when a `backend_spec` is present, `mcp_categories` must include `backend`.
   - **Auth/identity mapping** — sign-in, protected dashboards, user profiles, or account pages → `tooll_subagents/planning/auth_requirements_analyst.md` and `tooll_subagents/planning/auth_provider_selector.md`; materialization → `tooll_subagents/execution/auth_runtime_integrator.md`; validation → `tooll_subagents/self_correction/auth_validator.md`; audit → `tooll_subagents/observability/auth_audit_agent.md`. Degrade to no identity wrappers when no provider is supported or `project_rules` blocks identity services.
   - **CMS/data-query mapping** — dynamic sections (`blog`, `portfolio`, `cases`, `news`, `works`) or editable content listings → `tooll_subagents/planning/cms_requirements_analyst.md` and `tooll_subagents/planning/cms_source_selector.md`; materialization → `tooll_subagents/execution/cms_runtime_integrator.md`; validation → `tooll_subagents/self_correction/cms_validator.md`; audit → `tooll_subagents/observability/cms_audit_agent.md`. Degrade to `local_markdown` fallback when no external source is supported or `project_rules` blocks external CMS APIs.
   - **Accessibility mapping** — WCAG 2.1 / a11y requirements, generated front-end files, or explicit accessible design brief → `tooll_subagents/planning/accessibility_requirements_analyst.md` and `tooll_subagents/planning/accessibility_checker_planner.md`; materialization → `tooll_subagents/execution/accessibility_runtime_integrator.md`; validation → `tooll_subagents/self_correction/accessibility_validator.md`; audit → `tooll_subagents/observability/accessibility_audit_agent.md`. Degrade to no accessibility checks when no front-end artifact is present or `project_rules` disables audits.
   - **PWA / performance mapping** — requirements for installable PWA, offline support, performance budget, responsive images (`srcSet`), or font subsetting → `tooll_subagents/planning/pwa_requirements_analyst.md` and `tooll_subagents/planning/pwa_optimizer.md`; materialization → `tooll_subagents/execution/pwa_runtime_integrator.md`; validation → `tooll_subagents/self_correction/pwa_validator.md`; audit → `tooll_subagents/observability/pwa_audit_agent.md`. Degrade to manifest-only mode when `project_rules` disables service workers or offline support.
   - **Design token docs mapping** — requirements for design-token handoff, client/team documentation, styleguide, or token docs → `tooll_subagents/planning/design_token_docs_requirements_analyst.md` and `tooll_subagents/planning/design_token_docs_format_selector.md`; materialization → `tooll_subagents/execution/design_token_docs_runtime_integrator.md`; validation → `tooll_subagents/self_correction/design_token_docs_validator.md`; audit → `tooll_subagents/observability/design_token_docs_audit_agent.md`. Degrade to markdown-only when no JSON source is available or `project_rules` disables docs generation.
   - **Premium design injection** — if the task mentions landing pages, conversion pages, design systems, `DESIGN.md`, `design_tokens.json`, visual direction, brand references, or any of the premium direction keywords (`editorial`, `swiss_minimal`, `minimal_tech`, `brutalist`, `retro_futuristic`), set `needs_premium_design=true` and insert `tooll_subagents/planning/premium_design_analyst.md` as the first planning step. If a competitor/brand reference URL or `DESIGN.md` path is provided, also insert `tooll_subagents/planning/design_reference_extractor.md` before the analyst. The analyst emits a confirmed direction and font system; `tooll_subagents/planning/premium_design_system_generator.md` then produces `DESIGN.md` + `design_tokens.json`. Anti-slop validation is handled by `tooll_subagents/self_correction/anti_slop_validator.md`. Only load the `premium-design-anti-slop` Anthropic skill when this flag is set; otherwise keep it lazy-loaded.
   - **Ponytail injection** — before any code-generation or refactoring step, insert `ponytail_injector.md` to prepend the Ponytail protocol to the target agent's system prompt when the effective mode is not `off` and the task is coding-related. If the user invokes `/ponytail-audit`, insert `ponytail_audit.md` as a standalone read-only planning step.
   - **Headroom injection** — if `headroom_enabled=true` (resolved from input, env `HEADROOM_ENABLED`, or default `true`) and the `headroom` MCP category is available, insert `headroom_injector.md` as a planning step after `tool_plan_selection` produces the initial plan. The injector scans the plan for heavy context producers (large tool outputs, logs, RAG chunks, multi-agent handoffs) and appends `headroom_compressor.md` / `headroom_retriever.md` observation steps where compression will materially reduce context usage without blocking critical detail. If Headroom is unavailable or disabled, skip this step with a single log line.
   - **Memanto injection** — if `memanto_enabled=true` (resolved from input, env `MEMANTO_ENABLED`, or default `true`) and the `memanto` MCP category is available, insert `memanto_recall.md` as the first planning step with `query` derived from the user's goal and `tags=["project_rules", "constraints", "preferences"]`. After task decomposition, insert `memanto_remember.md` to persist the approved plan, constraints, and user preferences as typed memories. If Memanto is unavailable or disabled, skip these steps with a single log line.
   - **Mem0 injection** — if `mem0_enabled=true` (resolved from input, env `MEM0_ENABLED`, or default `true`) and the `mem0` MCP category is available, insert `mem0_recall.md` as the first planning step with `query` derived from the user's goal. After task decomposition, insert `mem0_remember.md` to persist the approved plan, constraints, and user preferences. If Mem0 is unavailable or disabled, skip these steps with a single log line.
3. **Rank candidates** — within category, score tools by alignment with `execution_policy` (speed, accuracy, cost, safety weights).
3a. **Assign model tiers** — for each tool/agent in the plan, pick a model tier using `LLMConfig.select_model(task_complexity)`: fast/cheap for bulk read/search/web/memory extraction and scoring; balanced for planning, analysis, and synthesis; strong for architecture, final review, and complex self-correction. Store the tier in the tool invocation metadata so the dispatcher can route to the right model.
3b. **Enforce volume caps** — for batched, chunked, or parallel agents, set explicit `MAX`, `CHUNK`, or `MAX_CHUNKS` caps. If a tool cannot bound its output (e.g., unbounded web crawl), cap the plan at `LLMConfig.max_parallel_agents` and `LLMConfig.max_chunks_per_agent` and log the truncation.
4. **Check compatibility** — verify output format of tool N matches input expectations of tool N+1; flag mismatches.
5. **Resolve conflicts** — if two sub-tasks claim the same mutable resource (file, database row), serialize or partition access.
6. **Build contingency** — for each primary tool, select fallback from same or adjacent category with lower capability but higher reliability.
7. **Optimize pipeline** — reorder where possible to reduce context switching (group all reads, then all writes, then tests).
8. **Estimate latency** — sum tool latencies plus orchestration overhead; add parallel-group savings.
9. **Validate policy** — ensure no selected tool is currently prohibited by active policy or safety hold.
10. **Validate volume caps** — for every batched/parallel tool, confirm a cap is set; if a cap is missing, apply `LLMConfig.max_parallel_agents`/`max_chunks_per_agent` defaults and log truncation.
11. **Return** — emit tool plan, compatibility flag, contingency plan, latency estimate, `model_tier_plan`, and `volume_caps`.

## Failure Modes

| Condition | Response |
|---|---|
| No tool available for required sub-task | Flag `pipeline_compatibility=false`; include `contingency_plan=["ASSISTANCE_REQUEST"]`; halt planning |
| Selected tool marked degraded by `performance_monitor.md` | Auto-select contingency as primary; log degradation impact |
| Policy prohibits selected tool for this request context | Replace with next-ranked permitted tool; if none, `recommendation=escalate` to `control/policy_enforcer.md` |
| Format mismatch between chained tools | Insert adapter sub-task or select alternative tool; if unresolvable, `pipeline_compatibility=false` |
| `project_rules` conflict with `execution_policy` | Escalate to `control/policy_enforcer.md` with `conflict_resolution_mode=most_restrictive` |
| Required tool discouraged by `project_rules` | Select fallback; if no viable fallback, `pipeline_compatibility=false` and escalate |
| Tool plan exceeds token budget for prompt assembly | Prune non-critical tool parameters; use compressed parameter schema |
| Model tier unknown for a tool | Default to `balanced`; log to `audit_logger.md` |
| Volume cap missing for a batched/parallel tool | Insert a cap using `LLMConfig.max_parallel_agents` and `max_chunks_per_agent`; log the truncation |
| Coding task plan missing `ponytail_injector.md` | Insert it before code-generation steps; log to `audit_logger.md` |
| `/ponytail-audit` requested but `ponytail_audit.md` unavailable | Skip audit step; report unavailable tool; continue with main plan |
| Premium-design task missing `needs_premium_design=true` | Set flag if any design keywords present; route to `premium_design_analyst.md` |
| Forbidden font requested in premium-design task | Refuse via `premium_design_analyst.md`; propose allowed alternative |

