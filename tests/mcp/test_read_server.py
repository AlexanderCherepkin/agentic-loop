"""pytest tests for the Read MCP server.

These tests verify tool registration, workspace path resolution, file reading,
chunking, cache behavior, and integrity checks using a temporary workspace.
"""

from __future__ import annotations

import asyncio
import hashlib
import sys
from pathlib import Path

# Ensure project root is on PYTHONPATH
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import pytest

from mcp_servers.read_server import ReadMCPServer


@pytest.fixture
def read_server(tmp_path: Path) -> ReadMCPServer:
    return ReadMCPServer(str(tmp_path))


@pytest.fixture
def sample_file(tmp_path: Path) -> Path:
    p = tmp_path / "sample.txt"
    p.write_text("line1\nline2\nline3\n", encoding="utf-8")
    return p


def test_read_server_initializes(read_server: ReadMCPServer) -> None:
    assert read_server.name == "tools_read"
    tools = read_server.get_tools_list()
    assert len(tools) == 9
    names = {t["name"] for t in tools}
    expected = {
        "read_file", "detect_encoding", "get_file_info", "read_chunk",
        "read_extract_content", "validate_integrity", "format_output",
        "list_directory", "clear_cache",
    }
    assert names == expected


def test_read_server_ping(read_server: ReadMCPServer) -> None:
    assert asyncio.run(read_server.ping()) is True


def test_read_tool_schemas(read_server: ReadMCPServer) -> None:
    for tool in read_server.get_tools_list():
        assert "name" in tool
        assert "description" in tool
        assert "inputSchema" in tool
        schema = tool["inputSchema"]
        assert schema.get("type") == "object"
        assert "properties" in schema


def test_read_file_returns_content(read_server: ReadMCPServer, sample_file: Path) -> None:
    result = asyncio.run(read_server.read_file(path="sample.txt"))
    assert result["content"] == "line1\nline2\nline3\n"
    assert result["path"] == str(sample_file)
    assert result["total_lines"] == 4


def test_read_file_chunk(read_server: ReadMCPServer, sample_file: Path) -> None:
    result = asyncio.run(read_server.read_file(path="sample.txt", start_line=2, end_line=3))
    assert result["content"] == "line2\nline3"


def test_read_file_outside_workspace_blocked(read_server: ReadMCPServer, tmp_path: Path) -> None:
    outside = tmp_path.parent / "outside.txt"
    outside.write_text("secret", encoding="utf-8")
    with pytest.raises(PermissionError):
        asyncio.run(read_server.read_file(path=str(outside)))


def test_get_file_info(read_server: ReadMCPServer, sample_file: Path) -> None:
    result = asyncio.run(read_server.get_file_info(path="sample.txt"))
    assert result["path"] == str(sample_file)
    assert result["size_bytes"] == sample_file.stat().st_size
    assert result["line_count"] == 4
    assert result["extension"] == ".txt"


def test_list_directory(read_server: ReadMCPServer, tmp_path: Path) -> None:
    (tmp_path / "a.txt").write_text("a", encoding="utf-8")
    (tmp_path / "b").mkdir()
    result = asyncio.run(read_server.list_directory(path="."))
    assert result["count"] == 2
    names = {e["name"] for e in result["entries"]}
    assert names == {"a.txt", "b"}


def test_validate_integrity(read_server: ReadMCPServer, sample_file: Path) -> None:
    expected = hashlib.sha256(sample_file.read_bytes()).hexdigest()
    result = asyncio.run(read_server.validate_integrity(path="sample.txt", expected_hash=expected))
    assert result["match"] is True


def test_extract_content(read_server: ReadMCPServer, sample_file: Path) -> None:
    result = asyncio.run(read_server.extract_content(path="sample.txt", pattern=r"line\d"))
    assert result["count"] == 3


def test_format_output(read_server: ReadMCPServer) -> None:
    result = asyncio.run(read_server.format_output(content="a\nb\nc", max_lines=2, show_line_numbers=True))
    assert result["truncated"] is True
    assert "1  a" in result["formatted"]


def test_clear_cache(read_server: ReadMCPServer, sample_file: Path) -> None:
    asyncio.run(read_server.read_file(path="sample.txt"))
    result = asyncio.run(read_server.clear_cache())
    assert result["cleared"] == 1
