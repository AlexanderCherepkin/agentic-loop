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

## Human-in-the-Loop Triggers

The following actions still require explicit human approval:

- Deployment, push, or publication to production/external systems.
- Exposure of the project on local hosting or any network for visualization.
- Updates to this `project_rules.md` file when the change is not directly ordered by the user.

All other actions — including destructive filesystem operations within the workspace, network egress to configured allow-list destinations, browser automation on trusted domains, CAPTCHA handling, and privilege changes requested by the autonomous bot — are auto-approved inside the autonomous run.
- Any operation explicitly flagged as critical by `control/human_oversight.md`.
