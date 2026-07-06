"""pytest tests for the Runcom MCP server.

These tests verify tool registration, command building, sandbox checks,
command execution, error analysis, and history tracking using a temporary workspace.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

# Ensure project root is on PYTHONPATH
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import pytest

from mcp_servers.runcom_server import RuncomMCPServer


@pytest.fixture
def runcom_server(tmp_path: Path) -> RuncomMCPServer:
    return RuncomMCPServer(str(tmp_path))


def test_runcom_server_initializes(runcom_server: RuncomMCPServer) -> None:
    assert runcom_server.name == "tools_runcom"
    tools = runcom_server.get_tools_list()
    assert len(tools) == 9
    names = {t["name"] for t in tools}
    expected = {
        "build_command", "optimize_command", "setup_environment",
        "execute_command", "sandbox_check", "capture_output", "handle_timeout",
        "analyze_error", "get_history",
    }
    assert names == expected


def test_runcom_server_ping(runcom_server: RuncomMCPServer) -> None:
    assert asyncio.run(runcom_server.ping()) is True


def test_runcom_tool_schemas(runcom_server: RuncomMCPServer) -> None:
    for tool in runcom_server.get_tools_list():
        assert "name" in tool
        assert "description" in tool
        assert "inputSchema" in tool
        schema = tool["inputSchema"]
        assert schema.get("type") == "object"
        assert "properties" in schema


def test_build_command(runcom_server: RuncomMCPServer) -> None:
    result = asyncio.run(runcom_server.build_command(executable="python", arguments=["-m", "pytest"]))
    assert result["command"] == "python -m pytest"
    assert result["arg_count"] == 2


def test_optimize_command(runcom_server: RuncomMCPServer) -> None:
    result = asyncio.run(runcom_server.optimize_command(command="a && b | c", optimize_for="speed"))
    assert len(result["optimizations"]) >= 2


def test_sandbox_check_blocks_forbidden(runcom_server: RuncomMCPServer) -> None:
    result = asyncio.run(runcom_server.sandbox_check(command="rm -rf /"))
    assert result["blocked"] is True


def test_sandbox_check_allows_safe(runcom_server: RuncomMCPServer) -> None:
    result = asyncio.run(runcom_server.sandbox_check(command="python -m pytest"))
    assert result["safe"] is True
    assert result["blocked"] is False


def test_execute_command_echo(runcom_server: RuncomMCPServer) -> None:
    result = asyncio.run(runcom_server.execute_command(command="echo hello", shell=True))
    assert result["exit_code"] == 0
    assert "hello" in result["stdout"]
    assert not result.get("timed_out")


def test_execute_command_blocked(runcom_server: RuncomMCPServer) -> None:
    result = asyncio.run(runcom_server.execute_command(command="rm -rf /"))
    assert result.get("blocked") is True


def test_analyze_error(runcom_server: RuncomMCPServer) -> None:
    result = asyncio.run(runcom_server.analyze_error(
        command="python x.py", stderr="command not found", exit_code=127
    ))
    assert result["count"] == 1
    assert result["issues"][0]["type"] == "missing_executable"


def test_get_history(runcom_server: RuncomMCPServer) -> None:
    asyncio.run(runcom_server.execute_command(command="echo a", shell=True))
    asyncio.run(runcom_server.execute_command(command="echo b", shell=True))
    result = asyncio.run(runcom_server.get_history(limit=10))
    assert result["total"] == 2
