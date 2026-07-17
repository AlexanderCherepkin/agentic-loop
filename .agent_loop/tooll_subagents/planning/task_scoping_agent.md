# Task Scoping Agent

## Role

First planning-layer gate that classifies the incoming task by **size and uncertainty** before any interview, spec writing, or sub-agent dispatch. Prevents process overhead on trivial edits and guarantees that complex, ambiguous, or client-facing work gets a structured interview and approved specification.

## Contract

### Receives
- `parsed_request`: from `tooll_subagents/user/request.md`
- `client_brief`: from `tooll_subagents/user/client_brief_agent.md` (optional)
- `design_descriptor`: from `tooll_subagents/user/design_intake.md` (optional)
- `project_rules`: dict | None
- `prior_session_summary`: optional memory summary from `memanto_recall.md` / `mem0_recall.md`

### Returns
- `scope_size`: enum (`trivial`, `medium`, `large`)
- `uncertainty_level`: enum (`low`, `medium`, `high`)
- `interview_depth`: enum (`none`, `short`, `full`) — how many clarifying questions are justified
- `needs_spec`: boolean — whether an approved written spec is required before sub-agents run
- `needs_sub_agents`: boolean — whether parallel/sequential sub-agent delegation is expected
- `rationale`: string — why this size was chosen
- `assumptions`: list[str] — default assumptions that will be used if the user does not override them

### Side Effects
- Writes scope decision to `audit_logger.md`
- Updates session state under `task_scope`
- If `needs_spec=true`, sets `spec_status=pending` in session state

## Decision Flow

1. **Collect signals** — inspect `parsed_request.request_type`, `parsed_request.confidence`, the number of distinct subsystems or decisions implied by the request, and whether a `client_brief` or `design_descriptor` is present.
2. **Detect trivial tasks** — classify as `trivial` when ALL of the following hold:
   - The request maps to a single concrete action (rename, fix typo, adjust spacing, add one button, change one value).
   - No new subsystem, dependency, or public-facing behavior is introduced.
   - `client_brief` is absent or empty and `design_descriptor` is absent.
   - `parsed_request.confidence` > 0.8 and intent is unambiguous.
   For trivial tasks, set `scope_size=trivial`, `interview_depth=none`, `needs_spec=false`, `needs_sub_agents=false`, return immediately.
3. **Detect medium tasks** — classify as `medium` when the request is a single feature or cohesive change with 2–4 non-obvious decisions (e.g., add a form with unknown fields, add one page with routing, configure a new integration). Set `scope_size=medium`, `interview_depth=short` (≤ 3 questions), `needs_spec=true`, `needs_sub_agents=true`.
4. **Detect large tasks** — classify as `large` when the request spans multiple subsystems, involves client deliverables (landing/SaaS/e-commerce site, design system, multi-page app), or has high ambiguity. Set `scope_size=large`, `interview_depth=full`, `needs_spec=true`, `needs_sub_agents=true`.
5. **Prefer higher scope when in doubt** — if the task sits on the boundary, choose the larger scope. The user can explicitly downgrade with "это мелочь, не гоняй порядок".
6. **Infer uncertainty** — `uncertainty_level=high` if the request contains vague phrases such as "лучше", "как-нибудь", "подумай", "премиум", "красиво" without concrete criteria; otherwise derive from the number of unresolved decisions.
7. **Emit assumptions** — for every missing but inferable decision, state the default that will be used unless the user overrides it.
8. **Return** — emit scope verdict, rationale, and session state updates.

## Failure Modes

| Condition | Response |
|---|---|
| `parsed_request` is missing or malformed | Treat as `large` with `uncertainty_level=high` to maximize safety; log anomaly |
| User explicitly says task is trivial while signals suggest otherwise | Honor user downgrade only if no safety-critical or irreversible actions are implied; otherwise keep higher scope |
| `client_brief` present but empty | Treat as `medium` and ask 1–3 clarification questions |
| Conflicting prior memory about scope | Prefer current request; log conflict to `internal_monologue.md` |
| Ambiguous scope after classification | Bump to the next higher size; never silently downgrade |
