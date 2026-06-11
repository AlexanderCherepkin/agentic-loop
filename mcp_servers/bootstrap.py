#!/usr/bin/env python3
"""
MCP Bootstrap — wires all 10 MCP servers into the registry and connects them to the runtime.

Usage:
    python -m mcp_servers.bootstrap           # Register all servers, print summary
    python -m mcp_servers.bootstrap --serve    # Run all servers via stdio (JSON-RPC)
    python -m mcp_servers.bootstrap --test     # Run self-test on all servers
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

from .registry import MCPRegistry, ServerInfo
from .read_server import ReadMCPServer
from .search_server import SearchMCPServer
from .replace_server import ReplaceMCPServer
from .runcom_server import RuncomMCPServer
from .runtest_server import RuntestMCPServer
from .terminal_server import TerminalMCPServer
from .manangr_server import ManangrMCPServer
from .database_server import DatabaseMCPServer
from .web_server import WebMCPServer
from .memory_server import MemoryMCPServer


def create_registry(workspace_root: str = ".") -> MCPRegistry:
    """Create and populate the MCP registry with all 10 servers."""
    registry = MCPRegistry()
    root = Path(workspace_root).resolve()

    servers = [
        ("tools_read", ReadMCPServer(str(root)), "Read file pipeline — 9 tools"),
        ("tools_search", SearchMCPServer(str(root)), "Search code pipeline — 8 tools"),
        ("tools_replace", ReplaceMCPServer(str(root)), "Replace in file pipeline — 10 tools"),
        ("tools_runcom", RuncomMCPServer(str(root)), "Run command pipeline — 9 tools"),
        ("tools_runtest", RuntestMCPServer(str(root)), "Run tests pipeline — 8 tools"),
        ("tools_terminal", TerminalMCPServer(str(root)), "Terminal I/O pipeline — 9 tools"),
        ("tools_manangr", ManangrMCPServer(str(root)), "Project management pipeline — 8 tools"),
        ("tools_database", DatabaseMCPServer(str(root)), "Database query pipeline — 11 tools"),
        ("tools_web", WebMCPServer(str(root)), "Web request pipeline — 10 tools"),
        ("tools_memory", MemoryMCPServer(str(root)), "Memory store pipeline — 11 tools"),
    ]

    for category, server, desc in servers:
        tools = server.get_tools_list()
        # Ensure memory server has its tools registered
        if category == "tools_memory":
            server.register_all()
        tools = server.get_tools_list()
        info = ServerInfo(
            name=desc,
            category=category,
            agent_count=len(tools),
            server=server,
            tools=[t["name"] for t in tools],
        )
        registry.register(info)

    return registry


async def test_all_servers(registry: MCPRegistry):
    """Run a quick self-test on every registered server."""
    results: dict[str, bool] = {}

    # Test read server
    read = registry.get_server("tools_read")
    if read:
        r = await read.call_tool("list_directory", {"path": ".", "pattern": "*.md"})
        results["read"] = "error" not in str(r.content)

    # Test search server
    search = registry.get_server("tools_search")
    if search:
        r = await search.call_tool("regex_search", {"query": "def ", "path": ".", "max_results": 5})
        results["search"] = "error" not in str(r.content)

    # Test terminal server
    term = registry.get_server("tools_terminal")
    if term:
        await term.call_tool("create_session", {"session_id": "test"})
        r = await term.call_tool("get_state", {"session_id": "test"})
        results["terminal"] = not r.is_error and "test" in str(r.content)

    # Test runcom server
    rc = registry.get_server("tools_runcom")
    if rc:
        r = await rc.call_tool("sandbox_check", {"command": "ls -la"})
        results["runcom"] = "error" not in str(r.content)

    # Test web server
    web = registry.get_server("tools_web")
    if web:
        r = await web.call_tool("analyze_error", {"status_code": 404, "response_body": ""})
        results["web"] = "error" not in str(r.content)

    # Test memory server
    mem = registry.get_server("tools_memory")
    if mem:
        mem.register_all()
        r = await mem.call_tool("list_entries", {"limit": 5})
        results["memory"] = "error" not in str(r.content)

    # Test replace server
    repl = registry.get_server("tools_replace")
    if repl:
        r = await repl.call_tool("validate_edit", {"path": "test.py", "content": "print('hello')"})
        results["replace"] = "error" not in str(r.content)

    # Test manangr server
    mgr = registry.get_server("tools_manangr")
    if mgr:
        r = await mgr.call_tool("analyze_structure", {"path": ".", "max_depth": 2})
        results["manangr"] = "error" not in str(r.content)

    # Test database server
    db = registry.get_server("tools_database")
    if db:
        await db.call_tool("open_connection", {"connection_string": ":memory:", "connection_id": "test"})
        r = await db.call_tool("analyze_schema", {"connection_id": "test"})
        results["database"] = "error" not in str(r.content)

    # Test runtest server
    rt = registry.get_server("tools_runtest")
    if rt:
        r = await rt.call_tool("discover_tests", {"path": "."})
        results["runtest"] = "error" not in str(r.content)

    return results


async def main():
    parser = argparse.ArgumentParser(description="MCP Bootstrap for Agentic Loop")
    parser.add_argument("--serve", action="store_true", help="Run all servers via stdio JSON-RPC")
    parser.add_argument("--test", action="store_true", help="Run self-test on all servers")
    parser.add_argument("--workspace", default=".", help="Workspace root path")
    parser.add_argument("--list", action="store_true", help="List all registered tools")
    args = parser.parse_args()

    registry = create_registry(args.workspace)
    print(f"MCP Registry: {registry.server_count} servers, {registry.tool_count} tools\n")

    if args.list:
        print("=" * 60)
        print("REGISTERED TOOLS")
        print("=" * 60)
        for cat, info in registry._servers.items():
            print(f"\n[{cat}] {info.name}")
            for tool_name in info.tools:
                tool = info.server._tools.get(tool_name)
                if tool:
                    print(f"  • {tool.name} — {tool.description[:80]}")
        return

    if args.test:
        print("Running self-tests...\n")
        results = await test_all_servers(registry)
        print("=" * 40)
        for name, ok in results.items():
            status = "PASS" if ok else "FAIL"
            print(f"  {name:15s} [{status}]")
        passed = sum(1 for v in results.values() if v)
        print(f"\n{passed}/{len(results)} servers operational")
        return

    if args.serve:
        print("Starting MCP servers via stdio (JSON-RPC mode)")
        print("All 10 servers registered and ready for tool calls")
        # In stdio mode, we run an aggregator that routes to the right server
        while True:
            try:
                line = sys.stdin.readline()
                if not line:
                    break
                request = json.loads(line.strip())
                method = request.get("method", "")
                req_id = request.get("id")

                if method == "initialize":
                    print(json.dumps({"jsonrpc": "2.0", "id": req_id, "result": {
                        "protocolVersion": "2024-11-05",
                        "capabilities": {"tools": {}},
                        "serverInfo": {"name": "agentic-loop-mcp", "version": "1.0.0"},
                    }}))
                    sys.stdout.flush()
                elif method == "tools/list":
                    tools = registry.get_all_tools()
                    print(json.dumps({"jsonrpc": "2.0", "id": req_id, "result": {"tools": tools}}))
                    sys.stdout.flush()
                elif method == "tools/call":
                    params = request.get("params", {})
                    tool_name = params.get("name", "")
                    arguments = params.get("arguments", {})
                    result = await registry.call_tool(tool_name, arguments)
                    print(json.dumps({"jsonrpc": "2.0", "id": req_id, "result": result}))
                    sys.stdout.flush()
                else:
                    print(json.dumps({"jsonrpc": "2.0", "id": req_id, "error": {"code": -32601, "message": f"Unknown method: {method}"}}))
                    sys.stdout.flush()
            except json.JSONDecodeError:
                continue
            except Exception as e:
                print(json.dumps({"jsonrpc": "2.0", "id": None, "error": {"code": -32603, "message": str(e)}}))
                sys.stdout.flush()
        return

    # Default: print summary
    for cat, info in registry._servers.items():
        print(f"  {cat:20s} → {info.agent_count:2d} tools | {info.name}")


if __name__ == "__main__":
    asyncio.run(main())
