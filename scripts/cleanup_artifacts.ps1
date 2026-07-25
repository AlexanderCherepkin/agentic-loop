# Agentic Loop — automatic operational artifact cleanup (Windows wrapper)
# Runs .agent_loop/scripts/cleanup_artifacts.py with a 20-day retention window
# and appends a timestamped summary to .logs/cleanup/YYYYMMDD_cleanup.log
#
# Intended to be invoked by Windows Task Scheduler every 20 days.

$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path -Parent $PSScriptRoot
$ScriptPath = Join-Path $RepoRoot ".agent_loop" "scripts" "cleanup_artifacts.py"
$LogDir = Join-Path $RepoRoot ".logs" "cleanup"
$LogFile = Join-Path $LogDir "$(Get-Date -Format 'yyyyMMdd')_cleanup.log"

if (-not (Test-Path $ScriptPath)) {
    throw "cleanup_artifacts.py not found at: $ScriptPath"
}

New-Item -ItemType Directory -Force -Path $LogDir | Out-Null

$Timestamp = Get-Date -Format "yyyy-MM-ddTHH:mm:ss"
Add-Content -Path $LogFile -Value "[$Timestamp] Starting Agentic Loop artifact cleanup"

try {
    $Output = & python "$ScriptPath" --retention-days 20 2>&1
    Add-Content -Path $LogFile -Value $Output
    Add-Content -Path $LogFile -Value "[$Timestamp] Cleanup completed successfully"
    exit 0
} catch {
    Add-Content -Path $LogFile -Value "[$Timestamp] ERROR: $_"
    exit 1
}
