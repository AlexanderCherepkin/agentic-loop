"""Integration tests for real MCP execution of all tools_* categories.

These tests verify that any registered MCP tool (not only figma_*) is
routed through PipelineRunner.execute_mcp_tool and actually invokes the
MCP gateway, while filesystem and network guards block dangerous inputs.
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch

# Ensure project root is on PYTHONPATH
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


def test_is_registered_mcp_tool_true_for_read_tool() -> None:
    runner = _make_runner(Path.cwd())
    assert runner.mcp_enabled is True
    assert runner._is_registered_mcp_tool("read_file") is True


def test_is_registered_mcp_tool_false_for_unknown() -> None:
    runner = _make_runner(Path.cwd())
    assert runner._is_registered_mcp_tool("nonexistent_tool") is False


def test_is_registered_mcp_tool_false_when_mcp_disabled() -> None:
    runner = _make_runner(Path.cwd(), mcp_enabled=False)
    # When MCP is disabled the gateway property is falsy even if HAS_MCP is true.
    assert runner.mcp_enabled is False
    assert runner._is_registered_mcp_tool("read_file") is False


def test_execute_mcp_read_file_tool() -> None:
    runner = _make_runner(Path.cwd())

    async def _run():
        return await runner.execute_mcp_tool("read_file", {"path": "README.md"})

    result = asyncio.run(_run())
    assert result.get("mcp_executed") is True
    assert result["tool"] == "read_file"
    inner = result.get("result", {})
    assert inner.get("is_error") is False
    assert "content" in inner


def test_execute_mcp_web_build_request() -> None:
    runner = _make_runner(Path.cwd())

    async def _run():
        return await runner.execute_mcp_tool("build_request", {"method": "GET", "url": "https://docs.python.org/3/"})

    result = asyncio.run(_run())
    assert result.get("mcp_executed") is True
    assert result["tool"] == "build_request"


def test_execute_mcp_runcom_sandbox_check() -> None:
    runner = _make_runner(Path.cwd())

    async def _run():
        return await runner.execute_mcp_tool("sandbox_check", {"command": "echo ok"})

    result = asyncio.run(_run())
    assert result.get("mcp_executed") is True
    assert result["tool"] == "sandbox_check"


def test_execute_mcp_database_in_memory() -> None:
    runner = _make_runner(Path.cwd())

    async def _run():
        await runner.execute_mcp_tool("open_connection", {"connection_string": ":memory:", "connection_id": "test"})
        return await runner.execute_mcp_tool("analyze_schema", {"connection_id": "test"})

    result = asyncio.run(_run())
    assert result.get("mcp_executed") is True
    assert result["tool"] == "analyze_schema"


def test_run_execution_routes_non_figma_mcp_tool() -> None:
    runner = _make_runner(Path.cwd())

    async def _run():
        with patch.object(runner, "execute_mcp_tool", new=AsyncMock(return_value={
            "tool": "read_file",
            "result": {"is_error": False, "result": "file content"},
            "mcp_executed": True,
        })) as mock_mcp:
            state = {
                "user_input": "прочитай файл README.md",
                "iteration": 1,
                "session_id": "test",
                "plan": {"steps": []},
            }
            await runner._run_execution(state, [], None)
            assert mock_mcp.awaited
            args = mock_mcp.await_args[0]
            assert args[0] == "read_file"
            assert args[1] == {"path": "README.md"}

    asyncio.run(_run())


def test_fs_guard_blocks_read_file_outside_workspace() -> None:
    runner = _make_runner(Path.cwd())

    async def _run():
        return await runner.execute_mcp_tool("read_file", {"path": "C:/Windows/System32/drivers/etc/hosts"})

    result = asyncio.run(_run())
    assert result.get("guard_blocked") is True
    assert "blocked" in result.get("error", "").lower()


def test_network_guard_blocks_disallowed_url() -> None:
    runner = _make_runner(Path.cwd())

    async def _run():
        return await runner.execute_mcp_tool("build_request", {"method": "GET", "url": "https://evil.example.com"})

    result = asyncio.run(_run())
    assert result.get("guard_blocked") is True
