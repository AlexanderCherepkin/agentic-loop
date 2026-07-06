"""pytest tests for the Replace MCP server.

These tests verify tool registration, safe file edits, backups, diffs, validation,
write verification, rollback, and deletion using a temporary workspace.
"""

from __future__ import annotations

import asyncio
import hashlib
import sys
from pathlib import Path

# Ensure project root is on PYTHONPATH
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import pytest

from mcp_servers.replace_server import ReplaceMCPServer


@pytest.fixture
def replace_server(tmp_path: Path) -> ReplaceMCPServer:
    return ReplaceMCPServer(str(tmp_path))


@pytest.fixture
def sample_file(tmp_path: Path) -> Path:
    p = tmp_path / "sample.py"
    p.write_text("print('hello')\n", encoding="utf-8")
    return p


def test_replace_server_initializes(replace_server: ReplaceMCPServer) -> None:
    assert replace_server.name == "tools_replace"
    tools = replace_server.get_tools_list()
    assert len(tools) == 10
    names = {t["name"] for t in tools}
    expected = {
        "create_backup", "match_pattern", "apply_edit", "generate_diff",
        "rank_edit_candidates", "validate_edit", "write_file",
        "verify_write", "rollback", "safe_delete",
    }
    assert names == expected


def test_replace_server_ping(replace_server: ReplaceMCPServer) -> None:
    assert asyncio.run(replace_server.ping()) is True


def test_replace_tool_schemas(replace_server: ReplaceMCPServer) -> None:
    for tool in replace_server.get_tools_list():
        assert "name" in tool
        assert "description" in tool
        assert "inputSchema" in tool
        schema = tool["inputSchema"]
        assert schema.get("type") == "object"
        assert "properties" in schema


def test_match_pattern(replace_server: ReplaceMCPServer, sample_file: Path) -> None:
    result = asyncio.run(replace_server.match_pattern(path="sample.py", pattern="hello"))
    assert result["count"] == 1
    assert result["matches"][0]["line"] == 1


def test_apply_edit(replace_server: ReplaceMCPServer, sample_file: Path) -> None:
    result = asyncio.run(replace_server.apply_edit(
        path="sample.py", old_string="hello", new_string="world"
    ))
    assert result["replaced"] is True
    assert sample_file.read_text(encoding="utf-8") == "print('world')\n"


def test_create_backup(replace_server: ReplaceMCPServer, sample_file: Path) -> None:
    result = asyncio.run(replace_server.create_backup(path="sample.py"))
    assert result["backup_id"].startswith("sample.py.")
    backup_path = Path(result["backup_path"])
    assert backup_path.exists()


def test_validate_edit_valid_python(replace_server: ReplaceMCPServer) -> None:
    result = asyncio.run(replace_server.validate_edit(path="sample.py", content="x = 1\n"))
    assert result["valid"] is True
    assert result["line_count"] == 2


def test_validate_edit_invalid_python(replace_server: ReplaceMCPServer) -> None:
    result = asyncio.run(replace_server.validate_edit(path="sample.py", content="x =\n"))
    assert result["valid"] is False
    assert any("syntax" in issue.lower() for issue in result["issues"])


def test_write_file(replace_server: ReplaceMCPServer, tmp_path: Path) -> None:
    result = asyncio.run(replace_server.write_file(path="new.py", content="y = 2\n"))
    assert result["written"] is True
    assert (tmp_path / "new.py").read_text(encoding="utf-8") == "y = 2\n"


def test_verify_write(replace_server: ReplaceMCPServer, sample_file: Path) -> None:
    expected = hashlib.sha256(sample_file.read_bytes()).hexdigest()
    result = asyncio.run(replace_server.verify_write(path="sample.py", expected_hash=expected))
    assert result["match"] is True


def test_safe_delete(replace_server: ReplaceMCPServer, sample_file: Path) -> None:
    result = asyncio.run(replace_server.safe_delete(path="sample.py"))
    assert result["deleted"] is True
    assert not sample_file.exists()


def test_rollback(replace_server: ReplaceMCPServer, sample_file: Path) -> None:
    backup = asyncio.run(replace_server.create_backup(path="sample.py"))
    sample_file.write_text("changed", encoding="utf-8")
    result = asyncio.run(replace_server.rollback(path="sample.py", backup_id=backup["backup_id"]))
    assert result["rolled_back"] is True
    assert sample_file.read_text(encoding="utf-8") == "print('hello')\n"
