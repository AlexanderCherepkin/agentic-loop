from __future__ import annotations

import os
import pytest

from mcp_servers.hermes_memory_server import HermesMemoryMCPServer


@pytest.fixture
def server(tmp_path, monkeypatch):
    # Point Hermes memory to a temp dir so the test does not depend on ~/.hermes.
    memory_dir = tmp_path / ".hermes" / "memory"
    memory_dir.mkdir(parents=True)
    monkeypatch.setenv("HERMES_DIR", str(tmp_path / ".hermes"))
    monkeypatch.setenv("HERMES_MEMORY_ENABLED", "true")
    return HermesMemoryMCPServer(str(tmp_path))


@pytest.mark.asyncio
async def test_hermes_memory_server_ping(server):
    assert await server.ping()


@pytest.mark.asyncio
async def test_hermes_memory_write_and_read(server):
    write_result = await server.call_tool(
        "hermes_memory_write",
        {"name": "test_note", "content": "hello hermes", "append": False},
    )
    assert not write_result.is_error
    payload = write_result.content[0]["text"]
    assert '"written": true' in payload

    read_result = await server.call_tool("hermes_memory_read", {"name": "test_note"})
    assert not read_result.is_error
    assert "hello hermes" in read_result.content[0]["text"]


@pytest.mark.asyncio
async def test_hermes_memory_search(server):
    await server.call_tool(
        "hermes_memory_write",
        {"name": "alpha", "content": "alpha keyword", "append": False},
    )
    await server.call_tool(
        "hermes_memory_write",
        {"name": "beta", "content": "beta other", "append": False},
    )
    result = await server.call_tool("hermes_memory_search", {"query": "alpha", "limit": 5})
    assert not result.is_error
    text = result.content[0]["text"]
    assert "alpha" in text
    assert "total_found" in text


@pytest.mark.asyncio
async def test_hermes_memory_list(server):
    await server.call_tool(
        "hermes_memory_write",
        {"name": "list_me", "content": "content", "append": False},
    )
    result = await server.call_tool("hermes_memory_list", {"limit": 10})
    assert not result.is_error
    assert "list_me" in result.content[0]["text"]
