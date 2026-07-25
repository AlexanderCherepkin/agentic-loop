# Plan — Agentic Loop Structure Audit & Decisive Cleanup

## Current state snapshot

- **Total workspace**: ~5.0 GB
- **Git-tracked source files**: 1 329 files
- **Real source files** (`.py`, `.md`, `.ts/.tsx`, `.js`, `.json`, excluding caches/venv/node_modules/audit/graphify): ~2 446 files
- **Total files in tree** (including caches): ~24 892 files

### Directory size breakdown

| Directory | Size | Role | Verdict |
|---|---|---|---|
| `.audit/` | **4.1 GB** | Append-only SHA-256 audit logs (`audit_YYYY-MM-DD.jsonl`) | **Bloat — needs rotation/cleanup** |
| `node_modules/` | 419 MB | Node dependencies for CLI/TUI | Optional but reasonable |
| `.venv/` | 247 MB | Python virtual environment | Reasonable for Python runtime |
| `.git/` | 29 MB | Git history | Reasonable |
| `figma-agent-core/` | 11 MB | Figma-to-code pipeline | Reasonable for its role |
| `data/` | 20 MB | `cost_tracking.db` (20 MB) + small `memory.db` | **Bloat — cost DB needs rotation** |
| `runtime/` | 4.6 MB | 36 runtime modules | Dense but legitimate |
| `.agent_loop/` | 2.1 MB | 316 agents + scripts + specs | Legitimate core |
| `.claude/` | 31 MB | Skills, plans, worktrees, memory | Mostly legitimate; memory dir outside repo |
| `mcp_servers/` | 1.3 MB | MCP server wrappers | Legitimate |
| `templates/` | 274 KB | Web project starter presets | Legitimate |
| `memory/` | 166 KB | Wiki + memory notes | Legitimate |
| `graphify-out/` | ~155 MB total | Multiple dated graph snapshots | **Redundant historical snapshots** |
| `htmlcov/` | unknown (coverage HTML) | Coverage report | **Generated artifact — can be deleted** |

### Key findings

1. **The 5 GB is not source bloat — it is operational data.**
   - `.audit/` alone = 4.1 GB (82 % of the workspace).
   - Largest single file: `.audit/audit_2026-07-22.jsonl` = 1.24 GB.
   - `data/cost_tracking.db` = 20 MB and growing.
   - `graphify-out/2026-*/` historical snapshots = 155 MB.

2. **Agent count is high but not the weight problem.**
   - 316 agents/files, ~2.1 MB in `.agent_loop/`.
   - 65 planning agents, 22 execution, 30 observability, 26 self-correction, 5 user, 4 result.
   - Source text is tiny compared to logs.

3. **There are real structural redundancies in the *system design*, not just disk:**
   - Three separate memory systems: Memanto, Mem0, Hermes/temporal_memory, plus `runtime/memory/`, `runtime/wiki/`, `runtime/skill_integration/`.
   - Two competing premium-design entry points: `runtime/premium_design/` + `anti-slop` skill, and `figma-agent-core/` design tokens / refinement loop.
   - Two project-classification/development paths: `runtime/web_project_agents/` and the Figma-based `design_to_code_planner.md` pipeline.
   - Two TUI/dashboard attempts: `runtime/tui/` + `runtime/tui.py`, and `tools_terminal/tui_dashboard.py`.
   - Multiple analytics/auth/i18n/CMS/PWA/design-token docs modules — each valuable, but each adds an agent triplet (planning + execution + validator) and a runtime engine.
   - `src/` and `public/` contain only 3 stray files — leftover from an early generated site, not part of the bot framework.

4. **Generated artifacts are not being cleaned up.**
   - `.audit/*.jsonl` are append-only but never rotated.
   - `data/cost_tracking.db` records every LLM call estimate.
   - `graphify-out/2026-*/` snapshots are never pruned.
   - `.agent_loop/specs/` contains 27 mock 450-byte spec files (auto-generated during tests) plus 6 real specs.
   - `htmlcov/` is a generated coverage report.
   - `__pycache__/` directories are scattered.

## Decisive recommendations

### Tier 1 — Immediate disk cleanup (no code changes, 4 GB+ recovered)

1. **Rotate `.audit/` logs.** Keep last 7–14 days locally; archive or delete older files. This alone frees ~3.5 GB.
2. **Vacuum/rotate `data/cost_tracking.db`.** If historical cost rows are not needed, trim them; otherwise cap DB size.
3. **Delete `htmlcov/`** (regenerated on demand by pytest).
4. **Delete `graphify-out/2026-*/` historical snapshots** older than the most recent 2–3 runs. Keep `graph.json`, `GRAPH_REPORT.md`, `manifest.json`, and latest `wiki/`.
5. **Purge `__pycache__/` and `.pytest_cache/`** across the tree.
6. **Delete stray generated site files** in `src/` and `public/` unless they are intentionally part of a deliverable project.

### Tier 2 — Structural simplification (requires code/policy changes)

7. **Consolidate memory layers.** Pick a primary long-term memory:
   - If Mem0 + Chroma works locally, keep Mem0 as primary and demote Memanto/Hermes to optional.
   - If Memanto server is the preferred local stack, keep Memanto and deprecate Mem0 client.
   - `runtime/temporal_memory/` and `runtime/memory/` overlap with the above — merge or remove.
   - **Decision**: keep Mem0 (hybrid semantic + keyword, local embedded) as primary; make Memanto and Hermes optional/deprecated in docs. This removes the need to maintain three memory client paths in `main_loop.md` and `tool_plan_selection.md`.

8. **Remove one TUI/dashboard entry point.**
   - `runtime/tui.py` and `runtime/tui/` are internal framework dashboards, which the Internal Agent Exposure Restriction forbids from being served anyway.
   - `tools_terminal/tui_dashboard.py` duplicates the effort.
   - **Decision**: delete `runtime/tui/`, `runtime/tui.py`, and `tools_terminal/tui_dashboard.py`. The bot is CLI-first; dashboards violate the internal-exposure rule.

9. **Delete `src/` and `public/` stray files** or move them to a deliverable project directory outside the framework repo.

10. **Clean `.agent_loop/specs/` mock files.**
    - The 27 × 450-byte `*_spec.md` files are test/session artifacts.
    - **Decision**: delete all 450-byte mock specs; keep only the 6 real approved specs (`memory_architecture_upgrade_spec.md`, `anti-slop-rule-set_spec.md`, `loop_engine_spec.md`, `aedafddc-…_spec.md`, `2026-07-25-multi-agent-profiles-moa_spec.md`, `2026-07-25-model-economy_spec.md`).
    - Update `.gitignore` to ignore `*_spec.md` except the real ones, or move specs to a session-scoped `.tmp/` location.

11. **Consolidate duplicate completion reports.**
    - 7 `*_COMPLETION_REPORT.md` files in the repo root. They are historical milestone reports.
    - **Decision**: move them to `memory/wiki/project/` or archive in `.tmp/`; keep only `README.md` and `ARCHITECTURE.md` as live docs in root.

### Tier 3 — Strategic architectural decisions (biggest impact)

12. **Choose one primary design-to-code pipeline.**
    - The Figma pipeline (`figma-agent-core/` + `figma_design_analyst.md` + `design_to_code_planner.md`) is mature and has Visual QA V2.
    - The text-brief pipeline (`runtime/web_project_agents/` + `project_classifier.md` + `project_architect.md` + `project_developer.md`) is newer and covers non-Figma projects.
    - **Decision**: keep **both** but clarify ownership:
      - Figma pipeline owns "I have a Figma file → generate Next.js".
      - Web Project Agents own "I have a text brief → generate fullstack project".
      - Do not add a third pipeline.

13. **Make `runtime/sandbox/` and Docker integration truly optional.**
    - `runtime/sandbox/` adds a large optional surface. If not actively used, demote to an external plugin and remove from core runtime tests/imports.

14. **Review the explosion of per-domain agent triplets.**
    - i18n, analytics, auth, CMS, accessibility, PWA, design-token docs each have 3–6 agents.
    - They are correct but create maintenance load. **Decision**: keep them, but do **not** add new per-domain triplets until existing ones are proven stable. The architecture is complete; further work should be polish and removal, not expansion.

15. **Stop tracking generated artifacts in git.**
    - `.audit/`, `data/*.db`, `graphify-out/cache/`, `graphify-out/2026-*/`, `figma-agent-core/conductor_report.json`, `figma_component_*.json`, `layout_ast.json`, `content_model.json` should all be generated at runtime, not committed.
    - Most are already in `.gitignore`, but they exist in the working tree because they were created locally and never cleaned. **Decision**: physically delete them, then rely on `.gitignore`.

## Implementation plan

### Phase A — Safe cleanup (auto-approved)

1. Delete `htmlcov/`.
2. Delete `__pycache__/` recursively.
3. Delete `graphify-out/2026-*/` except the latest 2–3 snapshots.
4. Delete `.agent_loop/specs/*_spec.md` mock files (27 files).
5. Delete stray `src/` and `public/` files (unless user says they belong to a deliverable).
6. Rotate `.audit/` logs older than 14 days.
7. Vacuum/trim `data/cost_tracking.db`.

### Phase B — Structural removal (requires user approval)

8. Remove `runtime/tui/`, `runtime/tui.py`, `tools_terminal/tui_dashboard.py`.
9. Consolidate memory: deprecate Memanto/Hermes/temporal_memory as primary, keep Mem0 + wiki as canonical.
10. Move completion reports to `memory/wiki/project/`.
11. Make sandbox/Docker optional plugin.

### Phase C — Policy changes

12. Add `.agent_loop/specs/*_spec.md` to `.gitignore` and create a whitelist for approved real specs.
13. Add a cleanup policy to `audit_logger.md` / `runtime/safety/audit_logger.py` so logs auto-rotate.
14. Add a retention policy to `cost_tracking.db`.

## Expected impact

- Disk: **4.0–4.2 GB recovered** immediately from Phase A.
- Complexity: remove 3 competing dashboards/memory systems + 27 mock specs + stray site files.
- Clarity: one canonical memory layer, one CLI-only interface, clear pipeline ownership.
- Risk: low for Phase A; medium for Phase B because it removes code paths. Phase B must include test updates.

## Risks and mitigations

| Risk | Mitigation |
|---|---|
| Deleting `.audit/` logs loses audit history | Rotate, not delete; archive to cold storage if compliance requires. |
| Removing TUI breaks `runtime/tui.py` imports | Search imports first; update `main.py` / `cli.py`. |
| Mem0 vs Memanto choice is wrong | Deprecate, do not delete immediately; add env flag to re-enable deprecated path. |
| Phase A deletes user-generated site in `src/` | Ask before deleting `src/` and `public/`. |

## Acceptance criteria

1. Workspace size drops below 1.5 GB after Phase A.
2. `health_check.py` and `validate_cross_references.js` still pass after removals.
3. No mock `*_spec.md` files remain in `.agent_loop/specs/`.
4. `src/` and `public/` are either empty (reserved for deliverables) or removed.
5. `runtime/tui/`, `runtime/tui.py`, `tools_terminal/tui_dashboard.py` removed after user approval.
6. Memory consolidation decision documented in `memory/wiki/`.
