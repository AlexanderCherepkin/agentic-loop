# Project Rules — Agentic Loop

## Scope

This repository implements a multi-agent AI system with hierarchical safety-first architecture.
It contains 166 agents across 6 layers, plus runtime code and MCP servers that expose those agents over JSON-RPC.
Any change must preserve the three-circuit safety model (`safety-control → mutual_check → control`) and the ReAct cycle decomposition.

## Conventions

- **Agent specs** live under `.agent_loop/` and follow the Algorithmic template: `Role`, `Contract` (`Receives` / `Returns` / `Side effects`), `Decision Flow`, `Failure Modes`.
- **Filenames** are `snake_case.md`.
- **Directory quirks** are preserved intentionally: `tooll_subagents` (double "l") and `tools_manangr` (typo in "manager").
- **No comments** unless the WHY is non-obvious.
- **No new files** unless the architecture requires them — prefer editing existing agents.
- **Safety first** — any change to execution, control, or safety layers must respect the three-circuit flow.

## Tooling Preferences

- **Read / search** first: use `tools_read` and `tools_search` before mutating anything.
- **Edit** via `tools_replace/replace_in_file` using exact pattern replacement, not whole-file rewrites.
- **Run commands** via `tools_runcom/run_command` with sandboxed execution; dangerous commands require explicit scope and human approval.
- **Tests** via `tools_runtest/run_tests` after any code change.
- **External web calls** via `tools_web/web_request` for static/REST content.
- **Headless browser automation** via `tools_browser/headless_automation` (Playwright) for dynamic pages, screenshots, and DOM extraction; falls back to `tools_web` if Playwright is unavailable.
- **MCP servers** are loaded lazily: only construct and expose a server category when a tool from that category is actually invoked.
- **Validators** (`validate_cross_references.js`, `validate_consistency.js`) must pass with zero errors before any work is considered complete.

## Safety Defaults

- Default to read-only or sandboxed operations.
- Network egress is denied unless `control/network_guard.md` explicitly allows the destination and purpose.
- Filesystem writes are restricted to the workspace and explicit output directories; `.ssh`, `.aws`, browser profiles, and system paths are blocked by `control/file_system_guard.md`.
- Browser sessions run in ephemeral Playwright contexts; screenshots and downloads are written only to `<workspace>/.tmp/browser/`.
- External URLs for browser navigation require allow-list approval by `control/network_guard.md`; auth tokens, cookies, and localStorage secrets are redacted by `safety-control/data_leak_preventer.md` before any output leaves the system.
- Destructive commands (`rm -rf`, `mkfs`, `dd`, `> /dev/sda`, privilege escalation) are blocked by `safety-control/command_guard.md`.
- Token/PII leaks are scanned by `safety-control/data_leak_preventer.md` before output reaches the user.

## Review & Deployment Approval Gates

This project is configured as an autonomous bot. Only the following two human-approval gates remain; everything else is auto-approved and must not interrupt execution:

1. **Gate 1 — Interview confirmation**
   - When a structured interview is explicitly required, Claude asks once: **"Interview complete. Proceed with development?"**
   - If the user has already issued a development directive, this gate is considered satisfied; do not ask again.

2. **Gate 2 — Pre-preview / pre-deployment / local-hosting confirmation**
   - Before any preview, build, publish, deploy, or exposure to the internet/local hosting used for visualization, Claude must stop and ask: **"Project is ready for preview/deployment. Proceed?"**
   - No deployment, `git push`, hosting publish, public URL generation, or CI/CD trigger may run until this confirmation is received.

All other operations — file reads, searches, edits, command execution, test runs, code generation, agent creation, documentation updates, and internal planning — are auto-approved between these gates.

## Figma Agent Bot — Pre-authorized Bash Patterns

The following command patterns, used routinely by the Figma Agent Bot workflow inside `D:/My_head_folders/My-desktop/Test_Figma/`, are pre-authorized and must not trigger confirmation prompts:

1. **Masked env inspection** — `cd "D:/My_head_folders/My-desktop/Test_Figma/figma-agent-core" && cat .env 2>/dev/null | sed 's/=.*/=***/' | head -20`.
2. **Local LLM agent runs** — `cd "D:/My_head_folders/My-desktop/Test_Figma/figma-agent-core" && LLM_MODEL=<model> LLM_API_URL=http://localhost:11434/v1/chat/completions python agent.py --file figma_node.json --node-id <id> --output-name <name> --skip-assets --task "..."`.
3. **Artifact handoff copies** — `cd "D:/My_head_folders/My-desktop/Test_Figma" && mkdir -p handoffs/<id> && cp figma-agent-core/*.json figma-agent-core/*.md figma-agent-core/*.tsx handoffs/<id>/ && ls -la handoffs/<id>/`.
4. **Plan/spec reads** — `cd "D:/My_head_folders/My-desktop/Test_Figma" && cat <name>_plan.md 2>/dev/null | head -80`.
5. **Next.js site scaffolding** — `mkdir -p site/src/app/... site/src/components/... site/src/lib site/prisma`.
6. **Dependency checks** — `cd "D:/My_head_folders/My-desktop/Test_Figma/site" && ls -la node_modules 2>/dev/null | head -3`.
7. **SQLite DB init** — `cd "D:/My_head_folders/My-desktop/Test_Figma/site" && cp .env.example .env && npx prisma db push --skip-generate`.
8. **Local dev server start** — `cd "D:/My_head_folders/My-desktop/Test_Figma/site" && PORT=3100 npm run dev`.
9. **Server readiness polling** — `for i in 1 2 ...; do curl -s -o /dev/null -w "%{http_code}" http://localhost:3100/<path>; sleep 1; done`.
10. **Next.js project init** — `mkdir -p frontend && cd frontend && npx create-next-app@latest . --typescript --tailwind --eslint --app --src-dir --import-alias "@/*" --no-turbopack --use-npm --yes`.
11. **Prisma config cleanup** — `cd frontend && rm prisma.config.ts .env`.
12. **Prisma client regeneration** — `cd frontend && rm -rf node_modules/.prisma node_modules/@prisma/client && npx prisma generate`.

Scope restriction: pre-approval applies only when all paths stay inside `D:/My_head_folders/My-desktop/Test_Figma/`. Commands that leave this tree, target system paths, deploy/push, or are destructive without backup still require explicit approval.

## Human-in-the-Loop Triggers

The following actions still require explicit human approval:

- Deployment, push, or publication to production/external systems.
- Exposure of the project on local hosting or any network for visualization.
- Updates to this `project_rules.md` file when the change is not directly ordered by the user.

All other actions — including destructive filesystem operations within the workspace, network egress to configured allow-list destinations, browser automation on trusted domains, CAPTCHA handling, and privilege changes requested by the autonomous bot — are auto-approved inside the autonomous run.
- Any operation explicitly flagged as critical by `control/human_oversight.md`.
