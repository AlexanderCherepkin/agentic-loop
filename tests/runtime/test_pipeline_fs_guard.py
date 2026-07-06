"""Integration tests for FileSystemGuard wired into PipelineRunner MCP execution."""

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


def test_mcp_write_file_blocked_for_dot_env(tmp_path):
    runner = _make_runner(tmp_path)
    assert runner._mcp_gateway is not None
    runner._mcp_gateway.execute = AsyncMock(return_value={"is_error": False})

    async def _run():
        return await runner.execute_mcp_tool("write_file", {"path": str(tmp_path / ".env"), "content": "SECRET=1"})

    result = asyncio.run(_run())
    assert result.get("guard_blocked") is True
    assert result.get("is_error") is True
    assert ".env" in result["error"]
    runner._mcp_gateway.execute.assert_not_awaited()


def test_mcp_read_file_blocked_for_etc_passwd(tmp_path):
    runner = _make_runner(tmp_path)
    assert runner._mcp_gateway is not None
    runner._mcp_gateway.execute = AsyncMock(return_value={"is_error": False})

    async def _run():
        return await runner.execute_mcp_tool("read_file", {"path": "/etc/passwd"})

    result = asyncio.run(_run())
    assert result.get("guard_blocked") is True
    assert "/etc/" in result["error"]
    runner._mcp_gateway.execute.assert_not_awaited()


def test_mcp_write_file_allowed_in_workspace(tmp_path):
    runner = _make_runner(tmp_path)
    assert runner._mcp_gateway is not None
    runner._mcp_gateway.execute = AsyncMock(return_value={"is_error": False, "written": True})

    async def _run():
        return await runner.execute_mcp_tool("write_file", {"path": "allowed.txt", "content": "ok"})

    result = asyncio.run(_run())
    assert result.get("guard_blocked") is None
    assert result.get("mcp_executed") is True
    runner._mcp_gateway.execute.assert_awaited_once()


def test_mcp_apply_edit_blocked_for_dot_ssh(tmp_path):
    runner = _make_runner(tmp_path)
    assert runner._mcp_gateway is not None
    runner._mcp_gateway.execute = AsyncMock(return_value={"is_error": False})

    async def _run():
        return await runner.execute_mcp_tool(
            "apply_edit",
            {"path": str(tmp_path / ".ssh" / "config"), "old_string": "x", "new_string": "y"},
        )

    result = asyncio.run(_run())
    assert result.get("guard_blocked") is True
    assert ".ssh" in result["error"]
    runner._mcp_gateway.execute.assert_not_awaited()


def test_mcp_search_allowed_in_workspace(tmp_path):
    runner = _make_runner(tmp_path)
    assert runner._mcp_gateway is not None
    runner._mcp_gateway.execute = AsyncMock(return_value={"is_error": False, "results": []})

    async def _run():
        return await runner.execute_mcp_tool("regex_search", {"query": "def", "path": "."})

    result = asyncio.run(_run())
    assert result.get("guard_blocked") is None
    assert result.get("mcp_executed") is True
    runner._mcp_gateway.execute.assert_awaited_once()


def test_mcp_non_filesystem_tool_skips_guard(tmp_path):
    runner = _make_runner(tmp_path)
    assert runner._mcp_gateway is not None
    runner._mcp_gateway.execute = AsyncMock(return_value={"is_error": False})

    async def _run():
        return await runner.execute_mcp_tool("format_output", {"content": "hello"})

    result = asyncio.run(_run())
    assert result.get("guard_blocked") is None
    assert result.get("mcp_executed") is True
