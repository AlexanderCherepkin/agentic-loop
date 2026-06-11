from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .base import MCPServer, MCPTool


@dataclass
class ServerInfo:
    name: str
    category: str
    agent_count: int
    server: MCPServer
    tools: list[str] = field(default_factory=list)


class MCPRegistry:
    """Registry and discovery for all MCP servers across tools_* categories."""

    CATEGORY_MAP = {
        "tools_read": "Read file pipeline",
        "tools_search": "Search code pipeline",
        "tools_replace": "Replace in file pipeline",
        "tools_runcom": "Run command pipeline",
        "tools_runtest": "Run tests pipeline",
        "tools_terminal": "Terminal I/O pipeline",
        "tools_manangr": "Project management pipeline",
        "tools_database": "Database query pipeline",
        "tools_web": "Web request pipeline",
        "tools_memory": "Memory store pipeline",
    }

    def __init__(self):
        self._servers: dict[str, ServerInfo] = {}
        self._tool_to_server: dict[str, str] = {}

    def register(self, info: ServerInfo):
        self._servers[info.category] = info
        for tool_name in info.tools:
            self._tool_to_server[tool_name] = info.category

    def get_server(self, category: str) -> MCPServer | None:
        info = self._servers.get(category)
        return info.server if info else None

    def get_all_servers(self) -> dict[str, MCPServer]:
        return {cat: info.server for cat, info in self._servers.items()}

    def get_all_tools(self) -> list[dict[str, Any]]:
        tools: list[dict[str, Any]] = []
        for info in self._servers.values():
            tools.extend(info.server.get_tools_list())
        return tools

    def find_tool(self, tool_name: str) -> MCPServer | None:
        category = self._tool_to_server.get(tool_name)
        if category:
            return self._servers[category].server
        return None

    async def ping(self, category: str | None = None) -> dict[str, bool]:
        """Health check one or all servers. Returns {name: bool}."""
        results: dict[str, bool] = {}
        if category:
            info = self._servers.get(category)
            if info:
                results[info.name] = await info.server.ping()
        else:
            for info in self._servers.values():
                results[info.name] = await info.server.ping()
        return results

    def is_healthy(self, tool_name: str) -> bool:
        """Quick check if the server owning a tool is healthy."""
        server = self.find_tool(tool_name)
        if not server:
            return False
        return server._initialized

    async def call_tool(self, tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        server = self.find_tool(tool_name)
        if not server:
            return {"error": f"Tool not found: {tool_name}", "is_error": True}
        if not await server.ping():
            return {"error": f"MCP server for {tool_name} is not responding", "is_error": True}
        result = await server.call_tool(tool_name, arguments)
        return {"content": result.content, "is_error": result.is_error}

    @property
    def server_count(self) -> int:
        return len(self._servers)

    @property
    def tool_count(self) -> int:
        return len(self._tool_to_server)
