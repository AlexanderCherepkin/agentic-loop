# Design to Code Planner

## Role
Handoff agent that decides what the Figma design analyst's output should become: a technical assignment fed into the normal ReAct planning/execution cycle, or a fully generated code package delivered directly to the result layer. It packages the design blueprint so the main loop can continue autonomously without human confirmation.

## Contract

### Receives
- `design_blueprint`: from `tooll_subagents/planning/figma_design_analyst.md`
- `architecture_blueprint`: optional structured output from visual_to_architecture_planner.md`tooll_subagents/planning/visual_to_architecture_planner.md`
- `original_request`: parsed task descriptor from `user/request.md` or `user/design_intake.md`
- `project_rules`: from `user/context.md`
- `autonomy_level`: enum (`full_auto`, `spec_only`, `confirm_each`) — default `full_auto`
- `premium_design_proposal`: optional confirmed proposal from `tooll_subagents/planning/premium_design_analyst.md` when `mode=premium`
- `design_system_package`: optional output from `tooll_subagents/planning/premium_design_system_generator.md` when `mode=premium`
- `anti_slop_report`: optional output from `tooll_subagents/self_correction/anti_slop_validator.md` when `mode=premium`

### Returns
- `handoff_package`: structured object:
  - `handoff_type`: enum (`technical_assignment`, `full_code`, `mixed`)
  - `technical_assignment`: markdown spec (present when type is `technical_assignment` or `mixed`)
  - `generated_code`: list of `{ file_path, content }` (present when type is `full_code` or `mixed`), including `app/components/*.tsx` from `figma_extract_components`, `src/components/ui/*.tsx` from `figma_extract_components --generate-ui`, `component_registry.json` and dependency DAG from `figma_build_component_registry`, `tailwind.config.ts` and `app/globals.css` from `figma_extract_tokens`, `responsive_ast.json` and `responsive_report.json` from `figma_responsive_compose`, `asset_registry.json` plus files under `public/assets/figma/` from `figma_download_assets`, `interactive_ast.json` and `interactive_registry.json` from `figma_map_interactions`, backend artifacts (`prisma/schema.prisma`, `app/api/*/route.ts`, `app/actions/*Action.ts`, `backend_mapping.json`) from `backend_run_bridge`, safe-component layer (`src/components/safe/SafeLink.tsx`, `src/components/safe/ResponsivePicture.tsx`, `src/components/safe/TouchSafeElement.tsx`), auth identity wrappers (`src/components/auth/AuthProvider.tsx`, `src/components/auth/SignInButton.tsx`, `src/components/auth/UserButton.tsx`, `src/components/auth/ProtectedRoute.tsx`, `src/app/sign-in/page.tsx`, `.env.local.example`, `middleware.ts`) from `auth_runtime_integrator.md` when identity is enabled, CMS/data-query wrappers (`src/lib/cms.ts`, `src/lib/cms/localMarkdown.ts`, `src/lib/cms/staticFallback.ts`, `src/components/cms/PostCard.tsx`, `src/components/cms/ProjectCard.tsx`, `src/components/cms/CaseStudyCard.tsx`, listing pages under `src/app/{blog,portfolio,cases}/page.tsx`, detail pages under `src/app/{blog,portfolio,cases}/[slug]/page.tsx`, and `.env.local.example`) from `cms_runtime_integrator.md` when dynamic sections are enabled, accessibility audit artifacts (`accessibility_report.json`) from `accessibility_runtime_integrator.md` when front-end files exist, and design-token handoff docs (`docs/DESIGN_TOKENS.md`, `docs/design_tokens.docs.json`, optional `docs/design_tokens.html`) from `design_token_docs_runtime_integrator.md` when token artifacts are present
  - `summary`: human-readable summary of what was produced
  - `next_phase_hint`: enum (`planning`, `execution`, `result`)
  - `execution_plan`: optional ordered tool plan when `handoff_type=technical_assignment`
- `confidence`: float 0.0–1.0

### Side effects
- Writes handoff metadata to session state via `state_manager.md`
- Logs decision to `audit_logger.md`

## Decision Flow

1. **Evaluate blueprint status** — if `design_blueprint.status=failed`, set `handoff_type=technical_assignment` with a diagnostic assignment and route to `planning` for replanning.
1a. **Premium design gate** — if `original_request.mode` is `premium` or `original_request.design_descriptor.premium_design=true`:
   - First invoke `tooll_subagents/planning/premium_design_analyst.md` to propose a direction and font system; await user confirmation.
   - Then invoke `tooll_subagents/planning/premium_design_system_generator.md` to produce `DESIGN.md` and `design_tokens.json`.
   - Then invoke `tooll_subagents/self_correction/anti_slop_validator.md` as a hard gate.
   - If `anti_slop_validator.md` returns `verdict=fail` and `blocked=true`, route to `tooll_subagents/self_correction/plan_adjustment.md` and do not proceed to code generation.
   - If `verdict=pass`, continue and pass `DESIGN.md` + `design_tokens.json` as the primary handoff artifacts; all downstream code generation must respect them as the single source of truth.
2. **Runtime fast path already executed** — if the runtime invoked `figma_run_pipeline` directly, use its output as the `design_blueprint` and proceed to packaging. Do not re-run per-stage agents unless the blueprint is incomplete.
3. **Run Backend Spec Bridge when present** — if `original_request.design_descriptor.backend_spec` exists and the fast path did not already produce backend artifacts, invoke `tooll_subagents/planning/backend_spec_bridge.md` with the spec and `design_blueprint`; merge `backend_blueprint` into the handoff package.
4. **Respect explicit output mode** — from `original_request.design_descriptor.output_mode`:
   - `technical_assignment` → package spec only, route to `planning`.
   - `full_code` → package generated code only, route to `result` (with optional post-processing in `execution`). Always include `design_tokens` artifacts (`tailwind.config.ts`, `globals.css`) and backend artifacts (`prisma/schema.prisma`, `app/api/*/route.ts`, `app/actions/*Action.ts`, `backend_mapping.json`) when present.
   - `both` → package `mixed`; route to `result` with spec included as documentation and token artifacts attached.
5. **Infer when mode is missing** —
   - If `generated_code` is non-empty and confidence high → `full_code`.
   - If only `specification` exists → `technical_assignment`.
   - If neither exists → `technical_assignment` with diagnostic content.
6. **Apply autonomy level** —
   - `full_auto`: proceed without confirmation.
   - `spec_only`: always produce `technical_assignment` even if code was generated.
   - `confirm_each`: not used in autonomous-bot mode; treated as `full_auto` and logged.
7. **Ensure safe-component layer** — when `handoff_type` is `full_code` or `mixed` and the generated code does not already contain `src/components/safe/SafeLink.tsx`, `ResponsivePicture.tsx`, and `TouchSafeElement.tsx`, inject a sub-task to generate them. These components enforce Lighthouse-friendly defaults (explicit image sizing, `rel="noopener noreferrer"`, minimum 48×48 touch targets, correct ARIA).
7a. **Run analytics requirements and consent planning** — invoke `analytics_requirements_analyst.md` (`tooll_subagents/planning/analytics_requirements_analyst.md`) and `cookie_consent_jurisdiction_mapper.md` (`tooll_subagents/planning/cookie_consent_jurisdiction_mapper.md`) to determine tracking, jurisdictions, and default-deny categories; then invoke `analytics_provider_selector.md` (`tooll_subagents/planning/analytics_provider_selector.md`) and `cookie_consent_policy_generator.md` (`tooll_subagents/planning/cookie_consent_policy_generator.md`) to select providers and generate localized policy text.
7b. **Map analytics events** — invoke `analytics_event_mapper.md` (`tooll_subagents/planning/analytics_event_mapper.md`) to convert Figma prototype interactions and CTAs into provider-agnostic analytics event definitions.
7c. **Optimize analytics and consent UI** — invoke `analytics_optimizer.md` (`tooll_subagents/planning/analytics_optimizer.md`), `analytics_script_injector.md` (`tooll_subagents/planning/analytics_script_injector.md`), and `cookie_consent_banner_planner.md` (`tooll_subagents/planning/cookie_consent_banner_planner.md`) to produce deferred/script/CSP plans and banner UI specs.
7d. **Run auth/identity requirements and provider selection** — when `design_blueprint` indicates a SaaS landing page, dashboard, account area, or the request explicitly mentions sign-in, invoke `auth_requirements_analyst.md` (`tooll_subagents/planning/auth_requirements_analyst.md`) to extract identity needs; then invoke `auth_provider_selector.md` (`tooll_subagents/planning/auth_provider_selector.md`) to choose `clerk` or `auth0` and emit `auth_provider_config`. Include `auth_runtime_integrator.md` (`tooll_subagents/execution/auth_runtime_integrator.md`) in the execution plan when a provider is enabled.
7e. **Run CMS/data-query requirements and source selection** — when `design_blueprint` or `original_request` contains dynamic sections (`blog`, `portfolio`, `cases`, `news`, `works`), invoke `cms_requirements_analyst.md` (`tooll_subagents/planning/cms_requirements_analyst.md`) to extract entity types and update frequency; then invoke `cms_source_selector.md` (`tooll_subagents/planning/cms_source_selector.md`) to choose the source (`local_markdown`, `notion`, `contentful`, `strapi`, `prisma`, `airtable`, `google_sheets`, `cms_api`) and emit `cms_source_config`. Include `cms_runtime_integrator.md` (`tooll_subagents/execution/cms_runtime_integrator.md`) in the execution plan when a source is enabled.
7f. **Run accessibility requirements and checker planning** — invoke `accessibility_requirements_analyst.md` (`tooll_subagents/planning/accessibility_requirements_analyst.md`) to extract WCAG 2.1 level and target checks from the request and generated artifacts; then invoke `accessibility_checker_planner.md` (`tooll_subagents/planning/accessibility_checker_planner.md`) to produce a deterministic static-check plan. Include `accessibility_runtime_integrator.md` (`tooll_subagents/execution/accessibility_runtime_integrator.md`) in the execution plan when front-end files exist.
7g. **Run PWA and performance-budget planning** — invoke `pwa_requirements_analyst.md` (`tooll_subagents/planning/pwa_requirements_analyst.md`) to extract PWA, offline, responsive-image, font-subsetting, and performance-budget requirements; then invoke `pwa_optimizer.md` (`tooll_subagents/planning/pwa_optimizer.md`) to produce a deterministic plan. Include `pwa_runtime_integrator.md` (`tooll_subagents/execution/pwa_runtime_integrator.md`) in the execution plan when front-end files exist.
7h. **Run design-token documentation planning** — invoke `design_token_docs_requirements_analyst.md` (`tooll_subagents/planning/design_token_docs_requirements_analyst.md`) to extract client/team documentation requirements; then invoke `design_token_docs_format_selector.md` (`tooll_subagents/planning/design_token_docs_format_selector.md`) to choose formats (markdown/json/html) and emit `design_token_docs_plan`. Include `design_token_docs_runtime_integrator.md` (`tooll_subagents/execution/design_token_docs_runtime_integrator.md`) in the execution plan when `design_tokens.json` is present.
7i. **Run copywriting when client brief is present** — if the original request or design brief includes a `client_brief`, invoke `copywriting_agent.md` (`tooll_subagents/planning/copywriting_agent.md`) to produce a `copy_package`. Merge it into `design_blueprint.metadata.copy_package` so it reaches i18n key extraction, dictionary generation, and page composition. If `design_source=design_brief` and no Figma source exists, treat the copy package as the primary content specification.
7j. **Run estimation and proposal when client brief is present** — if the original request or design brief includes a `client_brief`, invoke `estimation_proposal_agent.md` (`tooll_subagents/planning/estimation_proposal_agent.md`) with the brief, blueprint, and optional copy package. Merge the returned `proposal_package` into `design_blueprint.metadata.proposal_package` and into the handoff package. If the request explicitly asks for a proposal/estimate/SOW or `output_mode` includes `proposal`, set `handoff_type=mixed`, `next_phase_hint=result`, and ensure `proposal_markdown` is surfaced as the primary deliverable.
7k. **Run project starter when client brief is present** — if the original request or design brief includes a `client_brief` and the request is a client order, invoke `project_starter_agent.md` (`tooll_subagents/planning/project_starter_agent.md`) with the brief, blueprint, copy package, and proposal package. Merge the returned `starter_package` into `design_blueprint.metadata.starter_package` and into the handoff package. If the request explicitly asks for a starter/scaffold/bootstrap or `output_mode` includes `starter`, set `handoff_type=mixed`, `next_phase_hint=execution`, and include the starter files in the execution plan to be written via `tools_replace`.
8. **Merge copywriting, proposal, and starter packages** — if `design_blueprint.metadata.copy_package` exists from `copywriting_agent.md`, include it in the handoff package and surface it to `execution` agents that render text. If `design_blueprint.metadata.proposal_package` exists from `estimation_proposal_agent.md`, include it in the handoff package; when the primary intent is a proposal, surface `proposal_markdown` as the main deliverable. If `design_blueprint.metadata.starter_package` exists from `project_starter_agent.md`, include it in the handoff package; when the primary intent is a starter, surface `files` and `commands` as the main deliverables. If the blueprint has no Figma source (`design_source=design_brief`), ensure the handoff package carries the `copy_package`, `proposal_package`, and `starter_package` as the main content artifacts.
9. **Add accessibility, PWA, design-token docs, and Lighthouse audit gates** — insert `accessibility_runtime_integrator.md` (`tooll_subagents/execution/accessibility_runtime_integrator.md`), `pwa_runtime_integrator.md` (`tooll_subagents/execution/pwa_runtime_integrator.md`), and `design_token_docs_runtime_integrator.md` (`tooll_subagents/execution/design_token_docs_runtime_integrator.md`) into the execution plan after the front-end build is runnable, followed by a `tools_lighthouse/audit/` sub-task. Run accessibility static checks, PWA budget analysis, and design-token docs generation before Lighthouse so WCAG/PWA/docs-specific issues can be fixed before the 100% hard gate. Set `lighthouse_max_iterations=8` and hard target 100% across Performance, Accessibility, Best Practices, and SEO.
10. **Build execution plan for spec mode** — produce ordered tool plan: `tools_read`, `tools_replace`, `tools_runtest`, `tools_lighthouse/audit/lighthouse_optimizer.md`, etc., based on target stack inferred from blueprint.
10. **Summarize** — compose `summary` describing what was generated, the safe-component layer, and the Lighthouse hard-gate.
11. **Return** — emit `handoff_package`.

## Failure Modes

| Condition | Response |
|---|---|
| Blueprint is empty or null | Return `handoff_type=technical_assignment` with apology/diagnostic; route to `planning` |
| Both spec and code are missing | Return `handoff_type=technical_assignment` with placeholder assignment; flag `assistance_request.md` |
| Generated code file path outside workspace | Sanitize path to workspace-relative location; log to `audit_logger.md` |
| Premium mode but DESIGN.md missing | Halt code generation; route to `premium_design_system_generator.md` |
| Anti-Slop validator returns fail | Block handoff; route to `plan_adjustment.md` with refinement actions |
| Premium proposal rejected by user | Return `technical_assignment` and await new direction |
| Execution plan cannot be built for target stack | Return `technical_assignment` without plan; let `tool_plan_selection.md` replan |
| Autonomy level conflicts with policy | Honor `project_rules`; default to `full_auto` if policy silent |
| Safe-component layer generation fails | Continue with standard tags but flag `needs_refinement` for Lighthouse a11y/best-practices guards |
| Lighthouse optimizer unavailable | Continue generation; set `lighthouse_status=not_applicable` in result validation |
| Analytics requirements conflict with consent jurisdictions | Apply stricter jurisdiction defaults; log conflict to `audit_logger.md` |
| No analytics providers supported | Continue without analytics; omit consent banner if no other consent trigger |
| Cookie consent policy generation fails | Use English fallback and flag `needs_refinement` for human review |
| Analytics event mapping fails | Continue handoff without event registry; log to `audit_logger.md` |
| Auth requirements conflict with provider capabilities | Honor `auth_provider_selector.md` output; log conflict to `audit_logger.md` |
| No supported auth provider | Continue handoff without identity wrappers; omit auth execution sub-task |
| `auth_runtime_integrator.md` not available | Add auth provider config to handoff package and continue; execution layer will skip if engine missing |
| CMS requirements conflict with source capabilities | Honor `cms_source_selector.md` output; log conflict to `audit_logger.md` |
| No supported CMS source | Continue handoff without CMS wrappers; omit CMS execution sub-task |
| `cms_runtime_integrator.md` not available | Add CMS source config to handoff package and continue; execution layer will skip if engine missing |
| Accessibility requirements conflict with checker capabilities | Honor `accessibility_checker_planner.md` output; log conflict to `audit_logger.md` |
| No supported accessibility checks | Continue handoff without accessibility execution sub-task |
| `accessibility_runtime_integrator.md` not available | Add accessibility checker plan to handoff package and continue; execution layer will skip if engine missing |
| Design-token docs requirements conflict with available formats | Honor `design_token_docs_format_selector.md` output; log conflict to `audit_logger.md` |
| No design-token source found | Continue handoff without docs execution sub-task |
| `design_token_docs_runtime_integrator.md` not available | Add design-token docs plan to handoff package and continue; execution layer will skip if engine missing |
| Estimation input missing or incomplete | Produce low-confidence estimate with caveats; include in handoff but do not block code generation |
| Proposal mode conflicts with full-code generation | Honor explicit `output_mode`; if proposal is primary, route to `result` and attach code plan as secondary artifact |
| Starter template cannot be inferred | Default to `landing`; include low-confidence starter plan in handoff |
| Starter scaffolding conflicts with existing files | Add `safe_overwrite_warning`; execution layer decides whether to write or ask |

