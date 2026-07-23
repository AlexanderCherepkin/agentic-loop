"""pytest tests for the Search MCP server.

These tests verify tool registration, regex search, semantic ranking,
deduplication, and snippet generation using a temporary workspace.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

# Ensure project root is on PYTHONPATH
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import pytest

from mcp_servers.search_server import SearchMCPServer


@pytest.fixture
def search_server(tmp_path: Path) -> SearchMCPServer:
    return SearchMCPServer(str(tmp_path))


@pytest.fixture
def code_file(tmp_path: Path) -> Path:
    p = tmp_path / "code.py"
    p.write_text("def foo():\n    return 1\n\ndef bar():\n    return 2\n", encoding="utf-8")
    return p


def test_search_server_initializes(search_server: SearchMCPServer) -> None:
    assert search_server.name == "tools_search"
    tools = search_server.get_tools_list()
    assert len(tools) == 8
    names = {t["name"] for t in tools}
    expected = {
        "regex_search", "semantic_search", "define_scope", "rank_relevance",
        "deduplicate", "generate_snippet", "find_symbol", "diff_search",
    }
    assert names == expected


def test_search_server_ping(search_server: SearchMCPServer) -> None:
    assert asyncio.run(search_server.ping()) is True


def test_search_tool_schemas(search_server: SearchMCPServer) -> None:
    for tool in search_server.get_tools_list():
        assert "name" in tool
        assert "description" in tool
        assert "inputSchema" in tool
        schema = tool["inputSchema"]
        assert schema.get("type") == "object"
        assert "properties" in schema


def test_regex_search(search_server: SearchMCPServer, code_file: Path) -> None:
    result = asyncio.run(search_server.regex_search(query="def ", path=".", max_results=10))
    assert result["count"] == 2
    assert result["files_scanned"] == 1


def test_find_symbol(search_server: SearchMCPServer, code_file: Path) -> None:
    result = asyncio.run(search_server.find_symbol(symbol="foo", path="."))
    assert result["count"] == 1
    assert "foo" in result["results"][0]["match"]


def test_define_scope(search_server: SearchMCPServer, code_file: Path) -> None:
    result = asyncio.run(search_server.define_scope(path="."))
    assert result["type"] == "directory"
    assert result["estimated_files"] >= 1


def test_rank_relevance(search_server: SearchMCPServer) -> None:
    results = [
        {"match": "foo bar", "file": "a.py"},
        {"match": "baz qux", "file": "b.py"},
    ]
    result = asyncio.run(search_server.rank_relevance(query="foo", results=results))
    assert result["results"][0]["file"] == "a.py"


def test_deduplicate(search_server: SearchMCPServer) -> None:
    results = [
        {"file": "a.py", "line": 1},
        {"file": "a.py", "line": 1},
        {"file": "b.py", "line": 2},
    ]
    result = asyncio.run(search_server.deduplicate(results=results))
    assert result["unique_count"] == 2


def test_generate_snippet(search_server: SearchMCPServer, code_file: Path) -> None:
    result = asyncio.run(search_server.generate_snippet(file_path="code.py", line_number=2, context_lines=1))
    assert result["target_line"] == 2
    assert "return 1" in result["snippet"]


def test_diff_search(search_server: SearchMCPServer) -> None:
    result = asyncio.run(search_server.diff_search(a="x\ny", b="x\nz"))
    assert result["count"] == 1
    assert result["differences"][0]["added"] == "z"


def test_search_partial_traversal_blocked(search_server: SearchMCPServer, tmp_path: Path) -> None:
    sibling = tmp_path.parent / (tmp_path.name + "_evil") / "secret.py"
    sibling.parent.mkdir(parents=True, exist_ok=True)
    sibling.write_text("SECRET = 1\n", encoding="utf-8")
    with pytest.raises(PermissionError):
        asyncio.run(search_server.regex_search(query="SECRET", path=str(sibling)))
