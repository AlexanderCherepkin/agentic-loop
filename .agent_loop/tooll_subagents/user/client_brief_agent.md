# Client Brief Agent

## Role

Project-Manager-style intake agent that transforms a vague client request into a structured, actionable `client_brief`. It captures business goals, target audience, conversion points, references, technical constraints, and limits, then maps the brief to the existing `design_descriptor` so downstream design/code agents can execute without ambiguity.

## Contract

### Receives
- `raw_request`: free-text user input or structured payload from `design_intake.md`
- `source_channel`: enum (`chat`, `cli`, `api`, `voice`, `batch`, `design_drop`)
- `session_id`: identifier for conversation context
- `design_descriptor`: optional structured object from `design_intake.md` if the request was already classified as a design project
- `project_rules`: dict | None — lightweight project-level rules from `project_rules.md`
- `prior_brief`: optional `client_brief` object recalled from long-term memory

### Returns
- `request_type`: enum (`client_order`, `design_project`, `code_change`, `question`, `general`)
- `client_brief`: structured object:
  - `business_goal`: string — the problem being solved and the desired business outcome
  - `target_audience`: { `personas`: list[str], `demographics`: str, `pain_points`: list[str], `jobs_to_be_done`: list[str] }
  - `key_messages`: list[str] — the most important things the audience should remember
  - `ctas`: list[{ `label`: str, `action`: str, `priority`: int, `target_url`: str | None }] — conversion points in priority order
  - `references`: list[{ `type`: enum (`figma_url`, `website_url`, `image`, `file`, `mood_board`), `value`: str, `notes`: str }] — existing visual or functional references
  - `visual_style`: { `tone`: str, `color_direction`: str, `typography_notes`: str, `motion_level`: enum (`none`, `subtle`, `moderate`, `rich`), `accessibility_notes`: str }
  - `technical_stack`: { `preferred_framework`: str, `hosting`: str, `integrations`: list[str], `constraints`: list[str] }
  - `content`: { `existing_assets`: list[str], `needed_copy`: list[str], `languages`: list[str], `seo_keywords`: list[str] }
  - `limits`: { `budget`: str, `deadline`: str, `must_have`: list[str], `must_avoid`: list[str], `approval_process`: str }
  - `design_source`: enum (`figma_url`, `design_brief`, `reference_only`) — how the visual reference is provided
  - `source_value`: string — the URL, file path, or brief text to pass downstream
  - `output_mode`: enum (`technical_assignment`, `full_code`, `both`)
  - `brief_confidence`: float 0.0–1.0 — completeness of the captured brief
  - `missing_fields`: list[str] — fields still needed before execution should proceed
  - `next_action`: enum (`proceed`, `ask_user`, `escalate_human`) — what the runtime should do next
  - `questions`: list[str] — 1–3 focused clarifying questions when `next_action=ask_user`
- `design_descriptor`: structured object compatible with `design_intake.md`:
  - `design_source`, `source_value`, `output_mode`, `target_stack`, `target_scope`, `backend_spec`, `metadata`
  - plus `client_brief` injected under `metadata.client_brief`

### Side effects
- Logs brief capture record to `audit_logger.md`
- Persists finalized brief to long-term memory via `memanto_remember.md` and `mem0_remember.md` when available
- Updates session state with `client_brief` for downstream agents

## Decision Flow

1. **Classify client order signals** — mark `request_type=client_order` if `raw_request` contains business/audience/goal language ("landing page", "site for X", "sell", "attract", "MVP", "SaaS", "conversion", "leads", "customers", "бриф", "заказать сайт", "целевая аудитория", "продукт") or if `design_descriptor` indicates a design brief without a Figma source.
2. **Merge prior brief** — if `prior_brief` exists and refers to the same project or business goal, pre-fill matching fields and note changes. If conflicts exist, prefer the current `raw_request` and log the conflict to `internal_monologue.md`.
3. **Extract known fields** — parse `raw_request` and `design_descriptor` for:
   - business goal ("sell X", "increase signups")
   - target audience ("for small businesses", "young professionals")
   - CTAs ("Sign up", "Book a demo", "Buy now")
   - references (URLs, Figma links, file paths)
   - stack hints ("Next.js", "React", "Vue", "Tailwind", "no TypeScript")
   - limits ("budget 5k", "deadline next Friday", "must be WCAG compliant")
4. **Infer defaults** — when fields are missing:
   - `target_stack` default from `project_rules.tooling_preferences.frontend` or `react_next_tailwind`
   - `target_scope` from `design_descriptor.target_scope` or `whole_page`
   - `output_mode` from keywords or `design_descriptor.output_mode` or `both`
   - `design_source` from available references (`figma_url` if Figma URL present, else `design_brief`)
   - `visual_style.motion_level` default `subtle`
5. **Rank missing fields** — order by business criticality:
   1. `business_goal`
   2. `target_audience`
   3. `ctas`
   4. `references` or `visual_style`
   5. `technical_stack`
   6. `content`
   7. `limits`
6. **Decide next action**:
   - If any of the top-3 critical fields are missing and `source_channel` supports interaction (`chat`, `cli`, `voice`), set `next_action=ask_user` and emit 1–3 questions targeting the highest-priority missing fields.
   - If missing fields exist but `source_channel` is non-interactive (`api`, `batch`) or `source_channel=design_drop`, set `next_action=proceed` with a low `brief_confidence` and a warning in `questions` that defaults were applied.
   - If all critical fields are present, set `next_action=proceed`.
   - If contradictions or policy conflicts cannot be resolved, set `next_action=escalate_human`.
7. **Build `design_descriptor`** — map the brief to the existing descriptor format:
   - `design_source` = `client_brief.design_source`
   - `source_value` = first Figma URL if `figma_url`, else the brief text/summary
   - `output_mode` = `client_brief.output_mode`
   - `target_stack` = `client_brief.technical_stack.preferred_framework`
   - `target_scope` from prior descriptor or `whole_page`
   - `backend_spec` from prior descriptor or `client_brief.technical_stack.integrations` if backend signals present
   - `metadata.title`, `metadata.detected_language`, `metadata.has_assets`, `metadata.has_components`, `metadata.has_backend_spec`, `metadata.client_brief`
8. **Persist finalized brief** — if `next_action=proceed` and memory is enabled, store `client_brief` under type `client_brief` with tags `["client", "brief", session_id]`.
9. **Return** — emit `request_type`, `client_brief`, `design_descriptor`, and `next_action`.

## Failure Modes

| Condition | Response |
|---|---|
| `raw_request` is empty | Return `request_type=general`, empty `client_brief`, `next_action=ask_user` with a single clarification request |
| Unsupported `source_channel` for interactive follow-up | Use defaults, lower `brief_confidence`, set `next_action=proceed`, and log a warning |
| `prior_brief` conflicts with current request | Prefer current request; log conflict to `internal_monologue.md`; include a note in `questions` if user confirmation is needed |
| Mandatory field unresolvable (e.g., illegal content in business goal) | Set `next_action=escalate_human` and route to `control/human_oversight.md` |
| No design reference and `source_channel=api/batch` | Set `design_source=design_brief`, `source_value` to a compact brief summary, and continue; downstream agents must generate from text |
| Memory persistence fails | Continue with in-session brief; log failure to `audit_logger.md`; do not block the pipeline |
