from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from mcp_servers.security_scanner_server import SecurityScannerMCPServer

pytestmark = [pytest.mark.mcp]


def test_scan_codebase_finds_secret():
    server = SecurityScannerMCPServer(".")
    result = asyncio.run(
        server.call_tool(
            "scan_codebase", {"codebase": {"config.py": "API_KEY = 'sk-1234567890abcdef'"}}
        )
    )
    assert not result.is_error
    data = result.content[0]["text"]
    assert "secret" in data.lower() or "high" in data.lower()


def test_scan_codebase_empty_passes():
    server = SecurityScannerMCPServer(".")
    result = asyncio.run(
        server.call_tool("scan_codebase", {"codebase": {"README.md": "# Clean"}})
    )
    assert not result.is_error
    data = result.content[0]["text"]
    assert "low" in data.lower() or "no issues" in data.lower() or "pass" in data.lower()
