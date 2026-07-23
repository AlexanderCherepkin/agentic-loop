"""pytest tests for the Project Management (Manangr) MCP server.

These tests verify tool registration, structure analysis, dependency mapping,
impact analysis, task planning, and config management using a temporary workspace.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

# Ensure project root is on PYTHONPATH
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import pytest

from mcp_servers.manangr_server import ManangrMCPServer


@pytest.fixture
def manangr_server(tmp_path: Path) -> ManangrMCPServer:
    return ManangrMCPServer(str(tmp_path))


@pytest.fixture
def python_project(tmp_path: Path) -> Path:
    (tmp_path / "main.py").write_text("import helper\nprint(helper.run())\n", encoding="utf-8")
    (tmp_path / "helper.py").write_text("def run():\n    return 1\n", encoding="utf-8")
    return tmp_path


def test_manangr_server_initializes(manangr_server: ManangrMCPServer) -> None:
    assert manangr_server.name == "tools_manangr"
    tools = manangr_server.get_tools_list()
    assert len(tools) == 8
    names = {t["name"] for t in tools}
    expected = {
        "analyze_structure", "map_dependencies", "analyze_impact", "plan_tasks",
        "suggest_refactor", "manage_config", "generate_docs", "organize_files",
    }
    assert names == expected


def test_manangr_server_ping(manangr_server: ManangrMCPServer) -> None:
    assert asyncio.run(manangr_server.ping()) is True


def test_manangr_tool_schemas(manangr_server: ManangrMCPServer) -> None:
    for tool in manangr_server.get_tools_list():
        assert "name" in tool
        assert "description" in tool
        assert "inputSchema" in tool
        schema = tool["inputSchema"]
        assert schema.get("type") == "object"
        assert "properties" in schema


def test_analyze_structure(manangr_server: ManangrMCPServer, python_project: Path) -> None:
    result = asyncio.run(manangr_server.analyze_structure(path="."))
    assert result["total_files"] == 2
    assert ".py" in result["extensions"]


def test_map_dependencies(manangr_server: ManangrMCPServer, python_project: Path) -> None:
    result = asyncio.run(manangr_server.map_dependencies(path=".", language="python"))
    assert result["file_count"] >= 1
    assert "main.py" in result["dependencies"]


def test_analyze_impact(manangr_server: ManangrMCPServer, python_project: Path) -> None:
    result = asyncio.run(manangr_server.analyze_impact(file_path="helper.py"))
    assert result["target"] == "helper.py"
    assert result["risk"] == "MEDIUM"
    assert "main.py" in result["affected_files"]


def test_plan_tasks(manangr_server: ManangrMCPServer) -> None:
    result = asyncio.run(manangr_server.plan_tasks(requirements="Add auth. Add tests. Add docs.", max_tasks=5))
    assert result["total"] == 3
    assert result["tasks"][0]["priority"] == "high"


def test_manage_config_read(manangr_server: ManangrMCPServer, python_project: Path) -> None:
    (python_project / "config.json").write_text('{"x": 1}', encoding="utf-8")
    result = asyncio.run(manangr_server.manage_config(config_path="config.json", action="read"))
    assert result["parsed"] == {"x": 1}


def test_manage_config_write(manangr_server: ManangrMCPServer, python_project: Path) -> None:
    result = asyncio.run(manangr_server.manage_config(config_path="config.json", action="write", data={"y": 2}))
    assert result["written"] is True
    assert (python_project / "config.json").read_text(encoding="utf-8") == '{\n  "y": 2\n}'


def test_generate_docs(manangr_server: ManangrMCPServer, python_project: Path) -> None:
    # main.py defines no functions/classes of its own; add a class so both files appear.
    (python_project / "main.py").write_text(
        "import helper\n\nclass App:\n    pass\n\nprint(helper.run())\n",
        encoding="utf-8",
    )
    result = asyncio.run(manangr_server.generate_docs(path=".", format="markdown"))
    assert result["total_modules"] >= 2
    modules = {m["file"] for m in result["modules"]}
    assert modules >= {"main.py", "helper.py"}



def test_organize_files(manangr_server: ManangrMCPServer, python_project: Path) -> None:
    result = asyncio.run(manangr_server.organize_files(path="."))
    assert result["total_files"] == 2
    assert ".py" in result["by_type"]


def test_analyze_structure_blocks_path_traversal(manangr_server: ManangrMCPServer) -> None:
    result = asyncio.run(manangr_server.analyze_structure(path="../../../etc"))
    assert "error" in result
    assert "Access denied" in result["error"]


def test_manage_config_write_blocks_path_traversal(manangr_server: ManangrMCPServer, tmp_path: Path) -> None:
    victim = tmp_path.parent / "stolen.json"
    result = asyncio.run(
        manangr_server.manage_config(config_path="../stolen.json", action="write", data={"pwned": True})
    )
    assert "error" in result
    assert "Access denied" in result["error"]
    assert not victim.exists()
