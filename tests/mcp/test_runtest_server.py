"""pytest tests for the Runtest MCP server.

These tests verify tool registration, test discovery, execution planning,
failure analysis, flaky detection, and report generation using a temporary
workspace with sample pytest files.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

# Ensure project root is on PYTHONPATH
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import pytest

from mcp_servers.runtest_server import RuntestMCPServer


@pytest.fixture
def runtest_server(tmp_path: Path) -> RuntestMCPServer:
    return RuntestMCPServer(str(tmp_path))


@pytest.fixture
def sample_tests(tmp_path: Path) -> Path:
    (tmp_path / "test_sample.py").write_text(
        "def test_pass():\n    assert True\n\ndef test_fail():\n    assert False\n",
        encoding="utf-8",
    )
    return tmp_path


def test_runtest_server_initializes(runtest_server: RuntestMCPServer) -> None:
    assert runtest_server.name == "tools_runtest"
    tools = runtest_server.get_tools_list()
    assert len(tools) == 8
    names = {t["name"] for t in tools}
    expected = {
        "discover_tests", "plan_execution", "optimize_suite", "execute_test",
        "collect_coverage", "analyze_failure", "detect_flaky", "generate_report",
    }
    assert names == expected


def test_runtest_server_ping(runtest_server: RuntestMCPServer) -> None:
    assert asyncio.run(runtest_server.ping()) is True


def test_runtest_tool_schemas(runtest_server: RuntestMCPServer) -> None:
    for tool in runtest_server.get_tools_list():
        assert "name" in tool
        assert "description" in tool
        assert "inputSchema" in tool
        schema = tool["inputSchema"]
        assert schema.get("type") == "object"
        assert "properties" in schema


def test_discover_tests(runtest_server: RuntestMCPServer, sample_tests: Path) -> None:
    result = asyncio.run(runtest_server.discover_tests(path=".", framework="python"))
    assert result["count"] == 2
    names = {t["test_name"] for t in result["tests"]}
    assert names == {"test_pass", "test_fail"}


def test_plan_execution(runtest_server: RuntestMCPServer) -> None:
    tests = [{"name": "t1"}, {"name": "t2"}, {"name": "t3"}]
    result = asyncio.run(runtest_server.plan_execution(tests=tests, strategy="balanced"))
    assert result["total_tests"] == 3
    assert len(result["plan"]["phases"]) == 2


def test_optimize_suite(runtest_server: RuntestMCPServer) -> None:
    tests = [{"file": "a.py"}, {"file": "b.py"}, {"file": "a.py"}]
    result = asyncio.run(runtest_server.optimize_suite(tests=tests, max_parallel=2))
    assert result["file_count"] == 2
    assert len(result["parallel_groups"]) == 1


def test_execute_test_pass(runtest_server: RuntestMCPServer, sample_tests: Path) -> None:
    result = asyncio.run(runtest_server.execute_test(
        test_file="test_sample.py", test_name="test_pass", framework="pytest"
    ))
    assert result["passed"] is True
    assert result["exit_code"] == 0


def test_execute_test_fail(runtest_server: RuntestMCPServer, sample_tests: Path) -> None:
    result = asyncio.run(runtest_server.execute_test(
        test_file="test_sample.py", test_name="test_fail", framework="pytest"
    ))
    assert result["passed"] is False
    assert "AssertionError" in result["stdout"]


def test_execute_test_missing_file(runtest_server: RuntestMCPServer) -> None:
    result = asyncio.run(runtest_server.execute_test(test_file="missing.py"))
    assert result.get("error") is not None


def test_analyze_failure(runtest_server: RuntestMCPServer) -> None:
    result = asyncio.run(runtest_server.analyze_failure(
        test_name="t", stdout="", stderr="ImportError: No module named x"
    ))
    assert any(issue["type"] == "import" for issue in result["issues"])


def test_detect_flaky(runtest_server: RuntestMCPServer) -> None:
    runs = [{"passed": True}, {"passed": False}, {"passed": True}, {"passed": False}]
    result = asyncio.run(runtest_server.detect_flaky(test_name="t", run_results=runs))
    assert result["is_flaky"] is True
    assert result["verdict"] == "FLAKY"


def test_generate_report(runtest_server: RuntestMCPServer) -> None:
    results = [
        {"passed": True, "latency_ms": 100},
        {"passed": False, "latency_ms": 200},
    ]
    result = asyncio.run(runtest_server.generate_report(results=results, format="summary"))
    assert result["total"] == 2
    assert result["passed"] == 1
    assert result["failed"] == 1
