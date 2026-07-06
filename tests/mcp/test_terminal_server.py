"""pytest tests for the Terminal MCP server.

These tests verify session lifecycle, ANSI parsing, output filtering,
error detection, and tool registration.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

# Ensure project root is on PYTHONPATH
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import pytest

from mcp_servers.terminal_server import TerminalMCPServer


@pytest.fixture
def terminal_server(tmp_path: Path) -> TerminalMCPServer:
    return TerminalMCPServer(str(tmp_path))


def test_terminal_server_initializes(terminal_server: TerminalMCPServer) -> None:
    assert terminal_server.name == "tools_terminal"
    tools = terminal_server.get_tools_list()
    assert len(tools) == 9
    names = {t["name"] for t in tools}
    expected = {
        "create_session", "get_state", "add_to_history", "parse_ansi",
        "filter_output", "detect_error", "get_session_history",
        "list_sessions", "close_session",
    }
    assert names == expected


def test_terminal_server_ping(terminal_server: TerminalMCPServer) -> None:
    assert asyncio.run(terminal_server.ping()) is True


def test_terminal_tool_schemas(terminal_server: TerminalMCPServer) -> None:
    for tool in terminal_server.get_tools_list():
        assert "name" in tool
        assert "description" in tool
        assert "inputSchema" in tool
        schema = tool["inputSchema"]
        assert schema.get("type") == "object"
        assert "properties" in schema


def test_create_and_get_session(terminal_server: TerminalMCPServer) -> None:
    created = asyncio.run(terminal_server.create_session(session_id="s1"))
    assert created["id"] == "s1"
    state = asyncio.run(terminal_server.get_state(session_id="s1"))
    assert state["session_id"] == "s1"
    assert state["state"] == "active"


def test_add_to_history(terminal_server: TerminalMCPServer) -> None:
    asyncio.run(terminal_server.create_session(session_id="s1"))
    result = asyncio.run(terminal_server.add_to_history(session_id="s1", command="ls", output="file.txt"))
    assert result["entry_added"] is True
    assert result["history_size"] == 1


def test_get_session_history(terminal_server: TerminalMCPServer) -> None:
    asyncio.run(terminal_server.create_session(session_id="s1"))
    asyncio.run(terminal_server.add_to_history(session_id="s1", command="ls"))
    result = asyncio.run(terminal_server.get_session_history(session_id="s1"))
    assert result["total"] == 1


def test_close_session(terminal_server: TerminalMCPServer) -> None:
    asyncio.run(terminal_server.create_session(session_id="s1"))
    result = asyncio.run(terminal_server.close_session(session_id="s1"))
    assert result["closed"] is True
    assert asyncio.run(terminal_server.get_state(session_id="s1")).get("error") is not None


def test_parse_ansi(terminal_server: TerminalMCPServer) -> None:
    result = asyncio.run(terminal_server.parse_ansi(text="\x1b[31mred\x1b[0m text"))
    assert result["code_count"] == 2
    assert "red" in result["colors_detected"]
    assert "red text" in result["clean_text"]


def test_filter_output_grep(terminal_server: TerminalMCPServer) -> None:
    result = asyncio.run(terminal_server.filter_output(text="foo\nbar\nbaz", pattern="ba", filter_type="grep"))
    assert result["filtered_lines"] == 2


def test_detect_error(terminal_server: TerminalMCPServer) -> None:
    result = asyncio.run(terminal_server.detect_error(text="Traceback (most recent call last):\nError: fail"))
    assert result["has_errors"] is True
    assert result["error_count"] >= 1


def test_list_sessions(terminal_server: TerminalMCPServer) -> None:
    asyncio.run(terminal_server.create_session(session_id="s1"))
    asyncio.run(terminal_server.create_session(session_id="s2"))
    result = asyncio.run(terminal_server.list_sessions())
    assert result["count"] == 2
