# Plan — Client Onboarding / Brief Agent

## Problem

Audit row 26: the bot cannot yet act as a Project Manager when accepting a client order. For client-side development (design projects, landing pages, dashboards, SaaS MVPs) the system needs a structured intake that captures:
- business goals
- target audience
- CTAs / conversion points
- visual references (URLs, files, mood boards)
- technical stack constraints
- timeline / budget / policy limitations

Today `tooll_subagents/user/design_intake.md` only recognizes Figma URLs, local JSON, and brief keywords. It does not interview the user to fill missing fields, and it does not produce a structured `client_brief` artifact that downstream agents can consume.

## Goal

Add a first-class client onboarding / brief agent that:
1. Detects when a request is a client order or design project.
2. Conducts a structured PM-style interview, asking only for missing fields.
3. Produces a validated `client_brief` object.
4. Feeds the brief into the existing `design_descriptor` / `design_blueprint` / Figma-to-code pipeline without breaking existing flows.
5. Persists the brief to long-term memory so future sessions remember client preferences and constraints.

## Proposed implementation

### 1. New agent spec: `tooll_subagents/user/client_brief_agent.md`

Algorithmic template agent with:
- **Role**: PM-style intake agent that transforms a vague client request into a structured brief.
- **Receives**: `raw_request`, `assembled_context`, `project_rules`, `session_id`, `prior_brief` (optional, from memory), `source_channel`.
- **Returns**: `client_brief` object:
  - `business_goal`: string
  - `target_audience`: `{ personas: list[str], demographics: str, pain_points: list[str] }`
  - `key_messages`: list[str]
  - `ctas`: list[{ label, action, priority, target_url? }]
  - `references`: list[{ type: "url"|"file"|"mood_board", value, notes }]
  - `visual_style`: { tone, colors, typography, motion_level, accessibility_notes }
  - `technical_stack`: { preferred_framework, hosting, integrations, constraints }
  - `content`: { existing_assets, needed_copy, languages, seo_keywords }
  - `limits`: { budget, deadline, must_have, must_avoid, approval_process }
  - `design_source`: enum (`figma_url`, `design_brief`, `reference_only`)
  - `source_value`: string
  - `output_mode`: enum (`technical_assignment`, `full_code`, `both`)
  - `brief_confidence`: float
  - `missing_fields`: list[str]
  - `next_action`: enum (`proceed`, `ask_user`, `escalate_human`)
- **Decision Flow**:
  1. Classify request as `client_order` if it contains business/audience/goal language or references a product/site/page.
  2. Extract any already-provided brief fields from `raw_request` and `assembled_context`.
  3. Merge with `prior_brief` from memory if available.
  4. Identify `missing_fields` ranked by business criticality.
  5. If critical fields are missing and `source_channel` supports interaction, set `next_action=ask_user` with 1–3 focused questions.
  6. If enough fields are present or channel is non-interactive (`batch`/`api`), set `next_action=proceed`.
  7. Map the brief to a `design_descriptor` compatible with `design_intake.md` and `figma_design_analyst.md`.
  8. Return `client_brief`, `design_descriptor`, `next_action`, and `questions`.
- **Failure Modes**: empty request, unsupported channel, contradictions in brief, missing mandatory fields with no channel to ask.

### 2. Integrate into `main_loop.md` and `runtime/engine/pipeline_runner.py`

- Add `client_brief_agent.md` to the user-intake phase right after `design_intake.md`.
- If `request_type` is `design_project` or `client_order`:
  - Run `client_brief_agent.md`.
  - If `next_action=ask_user`, short-circuit the pipeline and return the questions to the user (termination_status=success with a clarifying response, no code generation yet).
  - If `next_action=proceed`, merge `client_brief` into the `design_descriptor` and continue to planning/execution as today.
- Update `PipelineRunner._run_design_intake` to also invoke `client_brief_agent.md` when the request looks like a client order.
- Add a new helper `_run_client_brief_interview` that loops at most 3 times, stopping when `missing_fields` is empty or the user signals "that's enough".

### 3. Memory persistence

- After a finalized `client_brief` is produced, persist it via `memanto_remember.md` and `mem0_remember.md` under type `client_brief` with tags `["client", "brief", session_id]`.
- On session resume or new client request, recall prior briefs via `memanto_recall.md` / `mem0_recall.md` and pass them as `prior_brief`.

### 4. Update `tooll_subagents/user/design_intake.md`

- Add `client_order` as a new `request_type` value.
- When `client_order` is detected, set `design_source=design_brief` and emit a placeholder `design_descriptor`.
- The real brief enrichment happens in `client_brief_agent.md`.

### 5. Update `tooll_subagents/planning/tool_plan_selection.md`

- When `client_brief` is present, the planner must include the brief fields in the planning context.
- If `references` contain Figma URLs, route to `figma` MCP category.
- If only references/mood boards, route to `figma_design_analyst.md` for manual implementation plan and warn that no Figma source exists.

### 6. Runtime wiring

- Add `client_brief` flag handling in `runtime/engine/agent_invocation_map.py` (regenerate after adding the agent).
- Add `needs_client_brief` to `PLANNING_FLAG_GROUPS`.
- Add tests in `tests/runtime/` that mock the brief agent and verify the interview loop and proceed path.

### 7. Update `ARCHITECTURE.md`

- Document the new `client_brief_agent.md` in the user layer and the main flow.
- Update agent count from 253 to 254.

### 8. Validation and commit

- Run `python .agent_loop/scripts/generate_agent_invocation_map.py`.
- Run validators, health check, pytest.
- Update graphify.
- Commit and push (Gate 2 as needed).

## Risks and mitigations

| Risk | Mitigation |
|------|------------|
| Interview loop could feel annoying | Ask only 1–3 missing critical questions per turn; respect `source_channel` and non-interactive modes. |
| Brief schema too rigid | Allow optional fields; default to empty strings/lists; downstream agents degrade gracefully. |
| Breaks existing Figma fast path | Brief agent is additive; if Figma URL is present, it enriches the descriptor rather than replacing it. |
| Memory leak of client data | Only persist post-safety, non-sensitive brief fields; rely on `data_leak_preventer.md`. |

## Acceptance criteria

1. `client_brief_agent.md` exists and follows the Algorithmic template.
2. `PipelineRunner` invokes it for client/design requests and handles `ask_user` short-circuit.
3. Health check and full pytest suite pass.
4. `validate_runtime_coverage.py` reports 0 unreachable agents after regeneration.
5. `ARCHITECTURE.md` and graphify reflect the new agent.

## Next step

Implement the plan after approval.
