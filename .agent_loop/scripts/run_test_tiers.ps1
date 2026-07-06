param(
    [Parameter()]
    [ValidateSet("core", "mcp", "figma", "ci", "all")]
    [string]$Tier = "ci"
)

switch ($Tier) {
    "core" {
        Write-Host "=== core unit tests (runtime + memory + observability + backend + integration) ==="
        python -m pytest -m core
    }
    "mcp" {
        Write-Host "=== MCP smoke tests (registry + gateway + tool ping) ==="
        python -m pytest -m mcp
    }
    "figma" {
        Write-Host "=== figma integration tests (requires FIGMA_TOKEN / FIGMA_URL) ==="
        python -m pytest -m figma
    }
    "ci" {
        Write-Host "=== CI fast track: core + mcp ==="
        python -m pytest -m "core or mcp"
    }
    "all" {
        Write-Host "=== full suite: core + mcp + figma ==="
        python -m pytest
    }
}
