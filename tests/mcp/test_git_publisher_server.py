from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from mcp_servers.git_publisher_server import GitPublisherMCPServer

pytestmark = [pytest.mark.mcp]


def test_check_configured_without_token():
    server = GitPublisherMCPServer(".")
    result = asyncio.run(server.call_tool("check_configured", {"provider": "github"}))
    assert not result.is_error
    text = result.content[0]["text"]
    assert "configured" in text.lower()


def test_publish_repository_without_token_fails():
    server = GitPublisherMCPServer(".")
    result = asyncio.run(
        server.call_tool(
            "publish_repository",
            {"project_id": "demo", "codebase": {"README.md": "# Demo"}, "provider": "github"},
        )
    )
    assert not result.is_error
    text = result.content[0]["text"]
    assert "failed" in text.lower() or "error" in text.lower() or "token" in text.lower()
