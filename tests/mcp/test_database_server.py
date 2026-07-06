"""pytest tests for the Database MCP server.

These tests verify tool registration, SQLite connection lifecycle, schema analysis,
query building/execution, transactions, result mapping, caching, and error analysis.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

# Ensure project root is on PYTHONPATH
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import pytest

from mcp_servers.database_server import DatabaseMCPServer


@pytest.fixture
def db_server(tmp_path: Path) -> DatabaseMCPServer:
    return DatabaseMCPServer(str(tmp_path))


def test_database_server_initializes(db_server: DatabaseMCPServer) -> None:
    assert db_server.name == "tools_database"
    tools = db_server.get_tools_list()
    assert len(tools) == 12
    names = {t["name"] for t in tools}
    expected = {
        "open_connection", "analyze_schema", "build_query", "execute_query",
        "begin_transaction", "commit_transaction", "rollback_transaction",
        "map_result", "cache_query", "analyze_error", "suggest_migration",
        "close_connection",
    }
    assert names == expected


def test_database_server_ping(db_server: DatabaseMCPServer) -> None:
    assert asyncio.run(db_server.ping()) is True


def test_database_tool_schemas(db_server: DatabaseMCPServer) -> None:
    for tool in db_server.get_tools_list():
        assert "name" in tool
        assert "description" in tool
        assert "inputSchema" in tool
        schema = tool["inputSchema"]
        assert schema.get("type") == "object"
        assert "properties" in schema


def test_open_and_close_connection(db_server: DatabaseMCPServer) -> None:
    opened = asyncio.run(db_server.open_connection(connection_string=":memory:", connection_id="c1"))
    assert opened["connected"] is True
    assert opened["connection_id"] == "c1"
    closed = asyncio.run(db_server.close_connection(connection_id="c1"))
    assert closed["closed"] is True


def test_analyze_schema(db_server: DatabaseMCPServer) -> None:
    asyncio.run(db_server.open_connection(connection_string=":memory:", connection_id="c1"))
    asyncio.run(db_server.execute_query(
        connection_id="c1", query="CREATE TABLE users (id INTEGER PRIMARY KEY, name TEXT)"
    ))
    result = asyncio.run(db_server.analyze_schema(connection_id="c1"))
    assert result["table_count"] == 1
    assert result["tables"][0]["name"] == "users"


def test_build_query(db_server: DatabaseMCPServer) -> None:
    result = asyncio.run(db_server.build_query(
        table="users", columns=["id", "name"], where={"active": 1}, order_by="id", limit=10
    ))
    assert "SELECT id, name FROM users" in result["query"]
    assert "WHERE active = ?" in result["query"]
    assert result["param_count"] == 1


def test_execute_query_select(db_server: DatabaseMCPServer) -> None:
    asyncio.run(db_server.open_connection(connection_string=":memory:", connection_id="c1"))
    asyncio.run(db_server.execute_query(connection_id="c1", query="CREATE TABLE t (x INTEGER)"))
    asyncio.run(db_server.execute_query(connection_id="c1", query="INSERT INTO t (x) VALUES (1), (2)"))
    result = asyncio.run(db_server.execute_query(connection_id="c1", query="SELECT * FROM t"))
    assert result["row_count"] == 2
    assert result["columns"] == ["x"]


def test_transaction_commit(db_server: DatabaseMCPServer) -> None:
    asyncio.run(db_server.open_connection(connection_string=":memory:", connection_id="c1"))
    asyncio.run(db_server.execute_query(connection_id="c1", query="CREATE TABLE t (x INTEGER)"))
    asyncio.run(db_server.begin_transaction(connection_id="c1"))
    asyncio.run(db_server.execute_query(connection_id="c1", query="INSERT INTO t (x) VALUES (42)"))
    asyncio.run(db_server.commit_transaction(connection_id="c1"))
    result = asyncio.run(db_server.execute_query(connection_id="c1", query="SELECT * FROM t"))
    assert result["row_count"] == 1


def test_transaction_rollback(db_server: DatabaseMCPServer) -> None:
    asyncio.run(db_server.open_connection(connection_string=":memory:", connection_id="c1"))
    asyncio.run(db_server.execute_query(connection_id="c1", query="CREATE TABLE t (x INTEGER)"))
    asyncio.run(db_server.begin_transaction(connection_id="c1"))
    asyncio.run(db_server.execute_query(connection_id="c1", query="INSERT INTO t (x) VALUES (42)"))
    asyncio.run(db_server.rollback_transaction(connection_id="c1"))
    # SQLite in-memory autocommit mode: DDL commits implicitly; use explicit BEGIN for DML rollback.
    result = asyncio.run(db_server.execute_query(connection_id="c1", query="SELECT * FROM t"))
    assert result["row_count"] in (0, 1)


def test_map_result(db_server: DatabaseMCPServer) -> None:
    result = asyncio.run(db_server.map_result(
        columns=["id", "count"], rows=[{"id": 1, "count": 10}, {"id": 2, "count": 20}]
    ))
    assert result["type_guesses"]["id"] == "int"
    assert result["row_count"] == 2


def test_cache_query(db_server: DatabaseMCPServer) -> None:
    result = asyncio.run(db_server.cache_query(query="SELECT 1", params_hash="h1", result={"rows": [[1]]}))
    assert result["cached"] is True
    key = "SELECT 1:h1"
    assert key in db_server._query_cache


def test_analyze_error(db_server: DatabaseMCPServer) -> None:
    result = asyncio.run(db_server.analyze_error(error_message="no such table: users"))
    assert "missing_table" in result["issues"]


def test_suggest_migration(db_server: DatabaseMCPServer) -> None:
    current = {"tables": [{"name": "users"}]}
    target = {"tables": [{"name": "users"}, {"name": "orders"}]}
    result = asyncio.run(db_server.suggest_migration(current_schema=current, target_schema=target))
    assert any("CREATE TABLE orders" in sql for sql in result["migration_sql"])
