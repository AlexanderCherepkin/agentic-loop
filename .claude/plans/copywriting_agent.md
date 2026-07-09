# Plan — Copywriting Agent

## Problem

Audit row #27: the bot can already capture a client brief, but it cannot yet generate persuasive landing-page copy from that brief. We need a dedicated agent that produces:
- headline / sub-headline
- hero text
- CTA labels and microcopy
- alt texts for images
- meta title / meta description / OG tags

This content should flow into generated pages, dictionaries, and SEO metadata.

## Goal

Add a first-class copywriting agent that consumes the `client_brief` and emits a structured `copy_package`. The package feeds both:
1. The runtime planning layer (i18n key extraction, dictionary generation, analytics event mapping, design-token docs).
2. The Figma-to-code pipeline (hero/headline substitutions, alt texts, meta tags).

## Proposed implementation

### 1. New agent spec: `tooll_subagents/planning/copywriting_agent.md`

Algorithmic template agent:
- **Role**: Generate landing-page copy from the client brief and any available structure context.
- **Receives**:
  - `client_brief`: from `tooll_subagents/user/client_brief_agent.md`
  - `design_blueprint`: optional from `figma_design_analyst.md` (sections, text nodes, asset placeholders)
  - `i18n_requirements`: optional from `i18n_requirements_analyst.md`
  - `project_rules`
- **Returns**: `copy_package`:
  - `headline`: str
  - `sub_headline`: str
  - `hero_text`: str
  - `cta_primary`: { `label`, `aria_label`, `microcopy` }
  - `cta_secondary`: { `label`, `aria_label`, `microcopy` } | None
  - `value_propositions`: list[str]
  - `section_headlines`: list[{ `section_id`, `section_name`, `headline`, `body` }]
  - `alt_texts`: list[{ `asset_id` | `figma_node_id`, `alt` }]
  - `meta`: { `title`, `description`, `og_title`, `og_description`, `keywords` }
  - `tonality`: { `tone`, `voice`, `language` }
  - `confidence`: float
  - `missing_inputs`: list[str]
  - `next_phase_hint`: enum (`planning`, `execution`, `result`)
- **Decision Flow**:
  1. Validate `client_brief` minimum fields: `business_goal`, `target_audience`, `key_messages` or `ctas`.
  2. Derive tone/voice from `client_brief.visual_style.tone`, `target_audience`, and `project_rules.brand_voice` if present.
  3. Generate headline using the primary business goal + audience pain point; keep under 60–80 chars when possible.
  4. Generate sub-headline and hero text expanding the headline with value proposition.
  5. Map `client_brief.ctas` to `cta_primary`/`cta_secondary`; add `aria_label` and action microcopy.
  6. If `design_blueprint.structure_map` is present, generate per-section headline/body pairs for hero, features, pricing, CTA, footer.
  7. If `design_blueprint.assets` or Figma node placeholders exist, generate alt texts using the image context and surrounding text.
  8. Build `meta` block with title ≤ 60 chars, description ≤ 160 chars, OG variants, and keywords from `client_brief.content.seo_keywords`.
  9. If `i18n_requirements.translation_scope` is `full` or `ui_only`, set `next_phase_hint=planning` so the copy flows into i18n key extraction and dictionary generation.
  10. Otherwise set `next_phase_hint=execution`.
- **Failure Modes**:
  - Missing critical brief fields → return low-confidence package with `missing_inputs` and `next_phase_hint=planning`.
  - Illegal/safety-blocked content → escalate to `control/human_oversight.md`.
  - No i18n requirements and no design blueprint → degrade to generic landing copy.

### 2. Integrate into `design_to_code_planner.md`

- After `design_blueprint` is available and before i18n key extraction, invoke `copywriting_agent.md`.
- Inject `copy_package` into `design_blueprint.metadata.copy_package`.
- Pass `copy_package` into `i18n_key_extractor.md` so text strings get stable keys.
- Pass headline/hero/CTA section mappings into `figma_generate_component` / page composer context when Figma text nodes are present.

### 3. Integrate into `figma_design_analyst.md`

- Add a step (13j) after i18n/analytics/design-token docs planning: **Copywriting pass** — invoke `copywriting_agent.md` when a `client_brief` is present.
- If `design_source=design_brief` (no Figma), the copy package becomes the primary content spec; downstream `page_composer.py` can render a landing page from the brief + copy.

### 4. Runtime wiring

- Add `copywriting_agent.md` to `PHASE_AGENTS["planning_copywriting"]` in `runtime/engine/agent_invocation_map.py`.
- Add `needs_copywriting` to `PLANNING_FLAG_GROUPS` mapping to `planning_copywriting`.
- Update `runtime/engine/pipeline_runner.py`:
  - When `client_brief` exists in `design_descriptor.metadata`, set `needs_copywriting=true` in the planning context before `_run_planning`.
  - When the brief is complete and `output_mode` is `full_code`/`both`, the copywriting agent must run before the design pipeline or inside the planning phase.
- Update mock LLM engine with deterministic `copywriting_agent.md` response for tests.

### 5. Figma-to-code consumer

- Update `figma-agent-core/page_composer.py` to accept an optional `copy_package` argument:
  - Replace literal Figma hero text with `copy_package.headline` when the node is the first/hero text and the brief indicates landing-page context.
  - Use `copy_package.alt_texts` for image `alt` attributes.
  - Emit `<head>` metadata using `copy_package.meta` if page-level generation is supported.
- If no Figma source exists, `conductor.py` should be able to fall back to a text-to-landing path that uses `copy_package` + `client_brief` + a simple layout skeleton.

### 6. i18n dictionary generation

- Update `i18n_dictionary_generator.md` to include `copy_package` strings in the source dictionary for the default locale.
- If `translation_scope=full`, request translations of the copy package for other locales in the same pass.

### 7. Tests and validation

- Add test in `tests/runtime/test_pipeline_figma.py` that verifies a client order triggers copywriting planning and produces `copy_package`.
- Run `generate_agent_invocation_map.py`, `validate_runtime_coverage.py`, health check, full pytest, graphify update.

### 8. Documentation

- Update `ARCHITECTURE.md`: planning layer +1 agent (42), `tooll_subagents` 97, total 253.
- Update `TECHNICAL_ASSIGNMENT.md` planning agent list to include `copywriting_agent.md`.
- Add memory note.

## Risks and mitigations

| Risk | Mitigation |
|------|------------|
| Generated copy is too generic | Agent receives full brief + audience + tone; project rules can enforce brand voice. |
| Copy overwrites Figma text | Only selected nodes (hero headline, empty alt, meta) are replaced; Figma text is preserved for body content. |
| i18n keys drift | Copy flows through the same `i18n_key_extractor.md` path as Figma text, so keys are stable and namespaced. |
| Safety issues in generated copy | Output passes through `output_reviewer.md` and `content_checker.md` post-check. |

## Acceptance criteria

1. `copywriting_agent.md` exists and follows the Algorithmic template.
2. `PipelineRunner` invokes it for client orders and feeds `copy_package` into the planning context.
3. `design_to_code_planner.md` and `figma_design_analyst.md` reference the copy package.
4. Health check and full pytest suite pass.
5. `validate_runtime_coverage.py` reports 0 unreachable agents after count update.
6. `ARCHITECTURE.md` and graphify reflect the new agent.
