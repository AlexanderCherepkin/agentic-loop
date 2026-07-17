# TUI Dashboard

## Role

Terminal User Interface (TUI) dashboard for the Agentic Loop pipeline. Renders
live session state, phase progress, agent activity, resource usage, and safety
status in a compact ANSI/Unicode layout suitable for local development
terminals, CI logs, and headless monitoring.

## Contract

- **Receives**: `{ session_id, pipeline_state: { phase, iteration, agents: [...], status }, resource_state, safety_state, max_lines? }`
- **Returns**: `{ dashboard_text: string, summary: { lines, width, phase, status } }`
- **Side effects**: none (pure rendering)

## Decision Flow

1. **Determine layout constraints**
   - `max_lines`: default 24, min 8, max 60.
   - Terminal width: default 80, auto-detected via `shutil.get_terminal_size` if available.
   - If output is not a TTY, fallback to plain-text compact rows.

2. **Render header**
   - Session ID (truncated), current phase, iteration count, overall status.
   - Color-coded status: `running=yellow`, `completed=green`, `failure=red`, `escalated_human=magenta`.

3. **Render phase strip**
   - Six ReAct phases: `user → planning → execution → observability → self_correction → result`.
   - Highlight current phase with `▶`; completed with `✓`; pending with `○`.
   - If phase loops are detected, mark with `↻` and a warning color.

4. **Render agent activity panel**
   - Last N agents (default 5): name, category, duration ms, outcome.
   - Outcome icons: `✓ pass`, `✗ fail`, `⚠ degraded`, `⧖ running`.
   - Truncate agent names to fit panel width.

5. **Render resource panel**
   - CPU/memory level from `ResourceLevel`: `low`, `normal`, `elevated`, `critical`.
   - Bar: `[||||||....]` style.
   - If critical, flash a red warning line.

6. **Render safety panel**
   - Last safety verdicts: `pass`, `warn`, `block`, `escalate`.
   - Count of safety checks this session.
   - Highlight active blocks or human escalations.

7. **Render footer**
   - Timestamp, uptime, hint line (e.g., "Ctrl-C to escalate to human").

8. **Emit plain-text fallback if TTY unavailable**
   - Single line: `Session <id> | phase <p> | iter <n> | status <s> | agents <k>`.

## Failure Modes

| Condition | Response |
|---|---|
| Missing `pipeline_state` | Render empty-state dashboard with error notice |
| Unknown phase name | Show raw phase string with `?` marker |
| Terminal too narrow (< 40 cols) | Drop side panels, render stacked rows only |
| Terminal too short (< 8 lines) | Render single-line summary instead |
| Non-UTF-8 terminal | Use ASCII-only box characters (`|`, `-`, `+`) |
| Unicode encode error | Strip offending characters, never crash |
