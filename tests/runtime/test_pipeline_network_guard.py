"""Integration tests for NetworkGuard wired into PipelineRunner MCP execution."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from unittest.mock import AsyncMock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import pytest

from runtime.engine.agent_loader import AgentLoader
from runtime.engine.llm_engine import LLMConfig, LLMEngine, LLMProvider
from runtime.engine.message_bus import MessageBus
from runtime.engine.pipeline_runner import PipelineRunner
from runtime.engine.state_manager import StateManager


def _make_runner(workspace_root: Path, mcp_enabled: bool = True) -> PipelineRunner:
    config = LLMConfig(provider=LLMProvider.MOCK, mcp_enabled=mcp_enabled)
    llm = LLMEngine(config=config)
    return PipelineRunner(
        loader=AgentLoader(".agent_loop"),
        llm=llm,
        bus=MessageBus(),
        state=StateManager(),
        workspace_root=str(workspace_root),
    )


def test_mcp_send_request_blocked_for_localhost(tmp_path):
    runner = _make_runner(tmp_path)
    assert runner._mcp_gateway is not None
    runner._mcp_gateway.execute = AsyncMock(return_value={"is_error": False})

    async def _run():
        return await runner.execute_mcp_tool("send_request", {"method": "GET", "url": "http://localhost:8080/admin"})

    result = asyncio.run(_run())
    assert result.get("guard_blocked") is True
    assert result.get("is_error") is True
    assert "localhost" in result["error"].lower()
    runner._mcp_gateway.execute.assert_not_awaited()


def test_mcp_browser_navigate_blocked_for_private_ip(tmp_path):
    runner = _make_runner(tmp_path)
    assert runner._mcp_gateway is not None
    runner._mcp_gateway.execute = AsyncMock(return_value={"is_error": False})

    async def _run():
        return await runner.execute_mcp_tool("browser_navigate", {"session_id": "s1", "url": "http://192.168.1.1/"})

    result = asyncio.run(_run())
    assert result.get("guard_blocked") is True
    assert "private" in result["error"].lower()
    runner._mcp_gateway.execute.assert_not_awaited()


def test_mcp_send_request_allowed_for_figma(tmp_path):
    runner = _make_runner(tmp_path)
    assert runner._mcp_gateway is not None
    runner._mcp_gateway.execute = AsyncMock(return_value={"is_error": False, "status_code": 200})

    async def _run():
        return await runner.execute_mcp_tool("send_request", {"method": "GET", "url": "https://api.figma.com/v1/files/abc"})

    result = asyncio.run(_run())
    assert result.get("guard_blocked") is None
    assert result.get("mcp_executed") is True
    runner._mcp_gateway.execute.assert_awaited_once()


def test_mcp_send_request_blocked_for_unknown_domain(tmp_path):
    runner = _make_runner(tmp_path)
    assert runner._mcp_gateway is not None
    runner._mcp_gateway.execute = AsyncMock(return_value={"is_error": False})

    async def _run():
        return await runner.execute_mcp_tool("send_request", {"method": "GET", "url": "https://attacker.example.com/"})

    result = asyncio.run(_run())
    assert result.get("guard_blocked") is True
    assert "not in the allow-list" in result["error"].lower()
    runner._mcp_gateway.execute.assert_not_awaited()


def test_mcp_non_network_tool_skips_guard(tmp_path):
    runner = _make_runner(tmp_path)
    assert runner._mcp_gateway is not None
    runner._mcp_gateway.execute = AsyncMock(return_value={"is_error": False})

    async def _run():
        return await runner.execute_mcp_tool("check_rate_limit", {"domain": "example.com"})

    result = asyncio.run(_run())
    assert result.get("guard_blocked") is None
    assert result.get("mcp_executed") is True
