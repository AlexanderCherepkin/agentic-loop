"""pytest tests for the MCP registry and lazy bootstrap behavior.

These tests cover cross-server registry behavior without importing concrete
server modules so they stay lightweight and unaffected by optional dependencies.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

# Ensure project root is on PYTHONPATH
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import pytest

from mcp_servers.registry import MCPRegistry, ServerInfo


def test_empty_registry_has_no_servers() -> None:
    registry = MCPRegistry()
    assert registry.server_count == 0
    assert registry.tool_count == 0
    assert registry.categories() == []


def test_register_does_not_build_server() -> None:
    registry = MCPRegistry()
    mock_server = MagicMock()
    info = ServerInfo(
        name="test",
        category="tools_test",
        agent_count=1,
        server=mock_server,
        tools=["test_tool"],
    )
    registry.register(info)

    assert registry.server_count == 1
    assert registry.tool_count == 1
    assert registry.get_server("tools_test") is mock_server


def test_lazy_factory_is_not_invoked_until_get_server() -> None:
    registry = MCPRegistry()
    factory = MagicMock(return_value=MagicMock())
    registry.register_factory(
        category="tools_lazy",
        factory=factory,
        name="Lazy server",
        metadata={"agent_count": 2, "tools": ["lazy_a", "lazy_b"]},
    )

    assert registry.server_count == 1
    assert registry.tool_count == 2
    factory.assert_not_called()

    server = registry.get_server("tools_lazy")
    factory.assert_called_once()
    assert server is factory.return_value


def test_lazy_factory_is_not_invoked_by_metadata_queries() -> None:
    registry = MCPRegistry()
    factory = MagicMock(return_value=MagicMock())
    registry.register_factory(
        category="tools_lazy",
        factory=factory,
        name="Lazy server",
        metadata={"agent_count": 1, "tools": ["lazy_tool"]},
    )

    # Queries that must not materialize the server.
    assert registry.categories() == ["tools_lazy"]
    assert registry.server_count == 1
    assert registry.tool_count == 1
    meta = registry.get_category_metadata("tools_lazy")
    assert meta["agent_count"] == 1
    assert meta["tools"] == ["lazy_tool"]

    factory.assert_not_called()


def test_create_registry_lazy_does_not_build_servers() -> None:
    """create_registry(lazy=True) must not call _build_server() for any category
    until the first call_tool().
    """
    from mcp_servers import bootstrap

    with patch.object(bootstrap, "_build_server") as mock_build:
        mock_server = MagicMock()

        async def _ping():
            return True

        async def _call_tool(tool_name, arguments):
            return MagicMock()

        mock_server.ping = _ping
        mock_server.call_tool = _call_tool
        mock_build.return_value = (mock_server, [])

        registry = bootstrap.create_registry(workspace_root=".", eager=False)

        assert registry.server_count == 25
        mock_build.assert_not_called()

        # Even metadata and category listing must stay lazy.
        registry.categories()
        registry.get_category_metadata("tools_read")
        assert registry.tool_count > 0
        mock_build.assert_not_called()

        # First call_tool() should trigger exactly one server build.
        asyncio.run(registry.call_tool("list_directory", {"path": "."}))
        mock_build.assert_called_once()
        mock_build.assert_called_with("tools_read", Path(".").resolve(), eager=True)


def test_create_registry_eager_builds_all_servers() -> None:
    from mcp_servers import bootstrap

    with patch.object(bootstrap, "_build_server") as mock_build:
        mock_build.return_value = (MagicMock(), [])

        bootstrap.create_registry(workspace_root=".", eager=True)

        assert mock_build.call_count == len(bootstrap.CATEGORY_TOOLS)
