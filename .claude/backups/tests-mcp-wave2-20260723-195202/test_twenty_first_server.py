"""pytest tests for the 21st.dev MCP server.

Covers tool registration, search, details, install planning, and stack
compatibility. Uses monkeypatch to avoid live network calls.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import pytest

from mcp_servers.twenty_first_server import TwentyFirstMCPServer


@pytest.fixture
def server() -> TwentyFirstMCPServer:
    return TwentyFirstMCPServer()


def test_server_initializes(server: TwentyFirstMCPServer) -> None:
    assert server.name == "21st_components"
    assert server._initialized is True
    tools = server.get_tools_list()
    assert len(tools) == 4
    names = {t["name"] for t in tools}
    assert names == {
        "search_components",
        "get_component_details",
        "plan_install",
        "check_stack_compatibility",
    }


def test_tool_schemas(server: TwentyFirstMCPServer) -> None:
    for tool in server.get_tools_list():
        assert "name" in tool
        assert "description" in tool
        assert "inputSchema" in tool
        schema = tool["inputSchema"]
        assert schema.get("type") == "object"
        assert "properties" in schema


def test_search_by_keyword(server: TwentyFirstMCPServer) -> None:
    result = server.search_components(query="hero", limit=5)
    assert result["status"] == "success"
    assert result["is_error"] is False
    assert result["count"] >= 1
    names = [c["name"] for c in result["components"]]
    assert any("hero" in n.lower() for n in names)


def test_search_by_tag(server: TwentyFirstMCPServer) -> None:
    result = server.search_components(tag="animation", limit=10)
    assert result["status"] == "success"
    assert result["count"] >= 1


def test_search_no_match(server: TwentyFirstMCPServer) -> None:
    result = server.search_components(query="xyz-not-found", limit=5)
    assert result["status"] == "empty"
    assert result["count"] == 0


def test_get_component_details(server: TwentyFirstMCPServer) -> None:
    result = server.get_component_details("@21st-century/hero")
    assert result["status"] == "success"
    assert result["is_error"] is False
    assert result["component"]["category"] == "marketing"


def test_get_component_details_short_name(server: TwentyFirstMCPServer) -> None:
    result = server.get_component_details("hero")
    assert result["status"] == "success"
    assert result["component"]["name"] == "@21st-century/hero"


def test_get_component_details_not_found(server: TwentyFirstMCPServer) -> None:
    result = server.get_component_details("nonexistent")
    assert result["is_error"] is True
    assert result["status"] == "not_found"


def test_plan_install(server: TwentyFirstMCPServer) -> None:
    result = server.plan_install(["@21st-century/hero", "text-rotate"])
    assert result["status"] == "success"
    assert len(result["components"]) == 2
    assert result["install_steps"]
    assert result["missing"] == []


def test_plan_install_missing(server: TwentyFirstMCPServer) -> None:
    result = server.plan_install(["hero", "does-not-exist"])
    assert result["is_error"] is True
    assert "does-not-exist" in result["missing"]


def test_check_stack_compatibility(server: TwentyFirstMCPServer) -> None:
    result = server.check_stack_compatibility(["hero", "particles"], framework="nextjs", tailwind=True)
    assert result["ok"] is True
    assert "@21st-century/hero" in result["compatible"]


def test_ping(server: TwentyFirstMCPServer) -> None:
    import asyncio

    assert asyncio.run(server.ping()) is True


def test_remote_catalog_falls_back(monkeypatch: Any) -> None:
    def broken_urlopen(*args: Any, **kwargs: Any) -> Any:
        raise OSError("network down")

    monkeypatch.setattr("urllib.request.urlopen", broken_urlopen)
    server = TwentyFirstMCPServer()
    assert server._degraded_reason is not None
    result = server.search_components(query="hero")
    assert result["status"] == "success"
    assert result["degraded"] is True
