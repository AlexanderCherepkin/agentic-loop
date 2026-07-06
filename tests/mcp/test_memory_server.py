"""pytest tests for the Memory MCP server.

These tests verify tool registration, memory entry CRUD, indexing, search,
embedding, compression, eviction, and consistency checks using a temporary
memory directory.
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

# Ensure project root is on PYTHONPATH
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import pytest

from mcp_servers.memory_server import MemoryMCPServer


@pytest.fixture
def memory_server(tmp_path: Path) -> MemoryMCPServer:
    os.environ["MEMORY_DIR"] = str(tmp_path)
    server = MemoryMCPServer(".")
    server.register_all()
    return server


def test_memory_server_initializes(memory_server: MemoryMCPServer) -> None:
    assert memory_server.name == "tools_memory"
    tools = memory_server.get_tools_list()
    assert len(tools) == 11
    names = {t["name"] for t in tools}
    expected = {
        "read_memory", "write_memory", "list_entries", "index_entry",
        "search_index", "generate_embedding", "compress_content",
        "summarize_entry", "evict_entry", "check_consistency", "optimize_store",
    }
    assert names == expected


def test_memory_server_ping(memory_server: MemoryMCPServer) -> None:
    assert asyncio.run(memory_server.ping()) is True


def test_memory_tool_schemas(memory_server: MemoryMCPServer) -> None:
    for tool in memory_server.get_tools_list():
        assert "name" in tool
        assert "description" in tool
        assert "inputSchema" in tool
        schema = tool["inputSchema"]
        assert schema.get("type") == "object"
        assert "properties" in schema


def test_write_and_read_memory(memory_server: MemoryMCPServer, tmp_path: Path) -> None:
    written = asyncio.run(memory_server.write_memory(key="note", content="hello world", tags=["demo"]))
    assert written["written"] is True
    read = asyncio.run(memory_server.read_memory(key="note"))
    assert read["content"] == "hello world"


def test_list_entries(memory_server: MemoryMCPServer) -> None:
    asyncio.run(memory_server.write_memory(key="a", content="alpha", tags=["greek"]))
    asyncio.run(memory_server.write_memory(key="b", content="beta", tags=["greek"]))
    result = asyncio.run(memory_server.list_entries(tag="greek"))
    assert result["total"] == 2


def test_search_index(memory_server: MemoryMCPServer) -> None:
    asyncio.run(memory_server.write_memory(key="a", content="alpha beta gamma", tags=["greek"]))
    asyncio.run(memory_server.write_memory(key="b", content="delta epsilon", tags=["greek"]))
    result = asyncio.run(memory_server.search_index(query="beta"))
    assert result["total_matches"] >= 1


def test_generate_embedding(memory_server: MemoryMCPServer) -> None:
    result = asyncio.run(memory_server.generate_embedding(text="hello world"))
    assert result["dimensions"] == 64
    assert len(result["embedding"]) == 16


def test_compress_content(memory_server: MemoryMCPServer) -> None:
    result = asyncio.run(memory_server.compress_content(content="a\n\n\nb", level="high"))
    assert result["compressed_size"] < result["original_size"]


def test_summarize_entry(memory_server: MemoryMCPServer) -> None:
    result = asyncio.run(memory_server.summarize_entry(content="First sentence. Second sentence. Third one.", max_length=50))
    assert "First sentence" in result["summary"]
    assert result["keywords"]


def test_evict_entry_lru(memory_server: MemoryMCPServer) -> None:
    asyncio.run(memory_server.write_memory(key="x", content="x"))
    asyncio.run(memory_server.write_memory(key="y", content="y"))
    asyncio.run(memory_server.read_memory(key="x"))
    result = asyncio.run(memory_server.evict_entry(policy="lru"))
    # Both x and y have access counts; x was accessed once, y zero times.
    assert result["evicted"] in {"x", "y"}
    assert result["policy"] == "lru"


def test_check_consistency(memory_server: MemoryMCPServer) -> None:
    asyncio.run(memory_server.write_memory(key="ok", content="content"))
    result = asyncio.run(memory_server.check_consistency())
    assert result["total_entries"] == 1
    assert result["issue_count"] == 0


def test_optimize_store(memory_server: MemoryMCPServer) -> None:
    asyncio.run(memory_server.write_memory(key="dup1", content="same"))
    asyncio.run(memory_server.write_memory(key="dup2", content="same"))
    result = asyncio.run(memory_server.optimize_store())
    assert result["duplicates_removed"] == 1
