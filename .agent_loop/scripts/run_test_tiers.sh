#!/usr/bin/env bash
set -euo pipefail

TIER="${1:-ci}"

case "$TIER" in
  core)
    echo "=== core unit tests (runtime + memory + observability + backend + integration) ==="
    python -m pytest -m core
    ;;
  mcp)
    echo "=== MCP smoke tests (registry + gateway + tool ping) ==="
    python -m pytest -m mcp
    ;;
  figma)
    echo "=== figma integration tests (requires FIGMA_TOKEN / FIGMA_URL) ==="
    python -m pytest -m figma
    ;;
  ci|fast)
    echo "=== CI fast track: core + mcp ==="
    python -m pytest -m "core or mcp"
    ;;
  all)
    echo "=== full suite: core + mcp + figma ==="
    python -m pytest
    ;;
  *)
    echo "Usage: $0 {core|mcp|figma|ci|all}"
    echo ""
    echo "  core  — fast unit tests (runtime phase transitions, memory, observability, backend, integration)"
    echo "  mcp   — MCP server smoke tests (registry, gateway, server init, tool ping)"
    echo "  figma — Figma integration tests (requires FIGMA_TOKEN and FIGMA_URL)"
    echo "  ci    — core + mcp, default CI gate (< 30 s combined)"
    echo "  all   — full pytest suite including figma"
    exit 1
    ;;
esac
