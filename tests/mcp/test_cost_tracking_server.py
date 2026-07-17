from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from mcp_servers.cost_tracking_server import CostTrackingMCPServer

pytestmark = [pytest.mark.mcp]


def test_estimate_cost_known_model():
    server = CostTrackingMCPServer(".")
    result = asyncio.run(
        server.call_tool(
            "estimate_cost", {"model": "gpt-4o", "input": "hello", "output": "hi"}
        )
    )
    assert not result.is_error
    text = result.content[0]["text"]
    assert "total_cost" in text


def test_check_budget_without_limit():
    server = CostTrackingMCPServer(".")
    result = asyncio.run(server.call_tool("check_budget", {"scope": "default"}))
    assert not result.is_error
    text = result.content[0]["text"]
    assert "allowed" in text
