# Automatic Cleanup Setup for Windows

This directory contains the Windows automation for the `cleanup_artifacts.py` rotation script.

## What it does

Every 20 days Windows Task Scheduler runs `cleanup_artifacts.ps1`, which executes:

```powershell
python .agent_loop/scripts/cleanup_artifacts.py --retention-days 20
```

The script removes operational artifacts older than 20 days:

- `.audit/audit_YYYY-MM-DD.jsonl` logs
- `graphify-out/YYYY-MM-DD/` snapshots
- old rows from `data/cost_tracking.db` (then VACUUM)
- `htmlcov/`, `__pycache__/`, `.pytest_cache/`, `.ruff_cache/`
- 450-byte mock spec files in `.agent_loop/specs/`

It does **not** delete source code, agents, runtime modules, or git history.

## Files

| File | Purpose |
|---|---|
| `cleanup_artifacts.ps1` | PowerShell wrapper that runs the Python script and logs output |
| `cleanup_artifacts_task.xml` | Task Scheduler task definition (import once) |
| `CLEANUP_SETUP.md` | This setup guide |

## One-time installation

Open **PowerShell as Administrator** and run:

```powershell
schtasks /create /tn "Agentic Loop Cleanup" /xml "D:\My_head_folders\My-desktop\Agentic_Loop_Graph\scripts\cleanup_artifacts_task.xml"
```

You should see:

```
SUCCESS: The scheduled task "Agentic Loop Cleanup" has successfully been created.
```

The task will run for the first time at **03:00 on 2026-07-26**, then every 20 days after that.

## Verify the task

```powershell
schtasks /query /tn "Agentic Loop Cleanup" /v
```

## Run manually

```powershell
& "D:\My_head_folders\My-desktop\Agentic_Loop_Graph\scripts\cleanup_artifacts.ps1"
```

## Logs

Each run appends a timestamped summary to:

```
.logs\cleanup\YYYYMMDD_cleanup.log
```

## Disable or remove

Disable (keep the task but stop automatic runs):

```powershell
schtasks /change /tn "Agentic Loop Cleanup" /disable
```

Remove completely:

```powershell
schtasks /delete /tn "Agentic Loop Cleanup" /f
```

## Changing the interval

Edit `cleanup_artifacts_task.xml` and change:

```xml
<DaysInterval>20</DaysInterval>
```

Then re-import:

```powershell
schtasks /delete /tn "Agentic Loop Cleanup" /f
schtasks /create /tn "Agentic Loop Cleanup" /xml "D:\My_head_folders\My-desktop\Agentic_Loop_Graph\scripts\cleanup_artifacts_task.xml"
```
