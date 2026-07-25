# Plan — SystemArchitect Master Protocol

## Problem

The user provided a comprehensive "Elite Digital Agency" master prompt and asked to make it the single highest-priority rule for the agent bot whenever it builds any website, application, frontend, backend, or related development. Today the bot already has strong premium-design and anti-slop guards, but they focus on visual output. There is no top-level protocol that forces every product build through a consistent discovery → architecture → UI concept → iterative development workflow and enforces the premium engineering principles (Premium First, Bulletproof Architecture, Clean Code) from the first user turn.

## Goal

Install the SystemArchitect protocol as the default orchestration layer for all product-building requests. It must sit above existing anti-slop/premium-design guards and must not duplicate them — it owns the workflow and mindset, anti-slop owns the visual hard gate.

## Proposed implementation

### 1. New skill: `.claude/skills/system-architect/SKILL.md`

Algorithmic-style skill:
- **Trigger**: automatic on any website/app/frontend/backend/build request, plus explicit `/system-architect`.
- **Role**: Senior System Architect & Premium UI/UX Director.
- **Core principles**: Premium First, Bulletproof Architecture, Clean Code.
- **Workflow**: 4 locked phases the bot must not skip without user approval:
  1. Discovery — up to 5 brief questions (business goal, audience, stack preferences, references).
  2. UX Logic & Architecture — DB schema proposal, stack recommendation, user flow, text wireframes.
  3. UI Concept — visual direction, design system, motion system, optional Midjourney prompts.
  4. Iterative Development — environment setup → frontend components → API/backend → integration notes.
- **Output format rules**: concise answers, file-path code blocks, architectural rationale with pros/cons.
- **Integration**: after this skill fires, route into the existing `anti-slop` skill and `premium_design_analyst.md` for direction confirmation, then `project_architect.md` / `project_developer.md` for execution.

### 2. Update `.claude/CLAUDE.md`

Add a new active-skill entry at the top of the skill list (so it outranks anti-slop/goal for product requests):
- `/system-architect` — automatic on any product build request.
- Trigger keywords: website, landing page, web app, SaaS, frontend, backend, full-stack, приложение, сайт, лендинг.
- Note: restart Claude Code after skill changes before relying on it.

### 3. Update `project_rules.md`

Add a new top-level section **"SystemArchitect Protocol"** before the Ponytail/Headroom/Memanto sections:
- Declares that all frontend/backend/product builds must follow the 4-phase workflow.
- References the skill file.
- States that anti-slop/premium-design gates remain mandatory and run inside phase 3/4.
- Keeps human-in-the-loop triggers (deploy/push/rm/etc.) untouched.

### 4. Update `.agent_loop/main_loop.md`

In the Decision Flow, after step 3 (safety pre-check) and before the design-intake branch, add a conditional step:
- If `request_type` indicates website/app/frontend/backend/product build, load the SystemArchitect protocol from `project_rules.md` / skill and prepend it to the session context.
- This makes the protocol available to `task_scoping_agent.md`, `spec_approval_gate.md`, and all downstream planning agents.
- No behavioral override of safety or spec gates; the protocol only shapes how the bot interviews and plans.

### 5. Documentation & memory

- Create `memory/wiki/tool/system-architect.md` with the condensed protocol and link to `anti-slop-rule-set` and `loop-engine`.
- Add or update `memory/2026-07-25-system-architect-protocol.md` project note.
- Update `MEMORY.md` index with one line.

### 6. Validation

- Run `.agent_loop/scripts/validate_cross_references.js` to ensure no broken agent references.
- Run `python .agent_loop/scripts/health_check.py` to verify agent counts and script health.
- Do not run full pytest unless the user asks, because this change is documentation/skill/policy only (no runtime code changes).

## Risks and mitigations

| Risk | Mitigation |
|---|---|
| Skill is too long and overflows context | Keep the skill file concise; full user-provided prompt is stored in the wiki memory and referenced by link. |
| Conflicts with anti-slop skill order | CLAUDE.md will list `system-architect` first, but its instructions explicitly defer visual direction to anti-slop/premium-design. |
| Duplicates existing spec-approval interview | SystemArchitect's phase 1 is folded into `spec_approval_gate.md`; no extra interview round — the protocol informs the questions. |
| User did not ask to modify main_loop.md | It is the minimal change needed to make the protocol truly "the main rule"; only injects context, does not bypass gates. |

## Acceptance criteria

1. `.claude/skills/system-architect/SKILL.md` exists and follows the skill frontmatter + structured body pattern.
2. `.claude/CLAUDE.md` contains the automatic + `/system-architect` trigger.
3. `project_rules.md` contains a "SystemArchitect Protocol" section.
4. `.agent_loop/main_loop.md` loads the protocol for product-build requests.
5. `memory/wiki/tool/system-architect.md` and `MEMORY.md` index are updated.
6. `validate_cross_references.js` and `health_check.py` pass.
