from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from mcp_servers.notification_server import NotificationMCPServer

pytestmark = [pytest.mark.mcp]


def test_dispatch_notification_disabled_channels():
    server = NotificationMCPServer(".")
    result = asyncio.run(
        server.call_tool(
            "dispatch_notification", {"project_id": "p1", "status": "completed"}
        )
    )
    assert not result.is_error
    text = result.content[0]["text"]
    assert "dispatched" in text
