---
name: skill-and-wiki
description: Entry point for /skill, /learn, and /lint commands plus LLM Wiki operations (ingest, query, lint). Routes to the correct internal agent and requires explicit approval before writing SKILL.md or wiki pages.
---

# /skill-and-wiki

> Internal entry point for the Agentic Loop bot's skill and wiki system.
> Handles `/skill`, `/learn`, `/lint`, `/wiki-ingest`, `/wiki-query` commands
> by routing them to the appropriate internal agents and the `skill_cli.py` script.

## Когда срабатывать

- User says `/skill <name>`, `/learn <source>`, `/lint`.
- User says `/wiki-ingest ...`, `/wiki-query ...`, `/wiki-lint`.
- User asks in plain language: "сохрани этот чат как навык", "научи навыку ...", "почисти вики".

## Decision Flow

1. Detect which command is requested (`skill`, `learn`, `lint`, `wiki-*`).
2. Extract the source/target if provided.
3. Route to the correct internal agent:
   - `skill_request_router.md` → `skill_packager.md` or `skill_integrator.md`
   - `wiki_ingest_planner.md` → `skill_integrator.md`
   - `wiki_lint_planner.md` → `skill_integrator.md`
4. For `/learn` and `/wiki-ingest`, propose new `memory/wiki/*.md` pages.
5. For `/skill`, propose a new `.claude/skills/<name>/SKILL.md` file.
6. Always show the proposed content and ask for explicit approval before writing.
7. Store the pending proposal in `StateManager` under `session:{sid}:pending_skill_operation`.
8. On the next user message with an explicit approval marker (`да` / `ok` / `yes` / `+`), call `runtime/skill_integration/SkillIntegrationEngine` to write files.
9. On rejection marker (`нет` / `no` / `cancel`), clear the pending proposal and report cancellation.
10. The CLI entry point `.agent_loop/scripts/skill_cli.py` can also build proposals and apply them via `apply --operation <op> --approval approved --proposal <json>`.

## Гарды

- Never create or overwrite `SKILL.md` without explicit "да" / "ok" / "yes".
- Never overwrite existing `memory/wiki/*.md` without per-page approval.
- Check for duplicate skills and duplicate wiki pages before creation.
- All writes go through `SkillIntegrationEngine`, which runs `safe_write_file`, blocks paths outside `.claude/skills/` and `memory/wiki/`, and logs every write/rejection to the audit logger.
- Keep `MEMORY.md` thin; do not dump wiki content into it.
