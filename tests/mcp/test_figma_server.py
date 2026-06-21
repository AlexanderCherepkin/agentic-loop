"""pytest tests for the Figma MCP server.

These tests mock subprocess invocation and filesystem state so they run without
a real Figma API key or network access. They verify tool registration, schema
shape, and the mapping from MCP tool calls to figma-agent-core scripts.
"""

from __future__ import annotations

import asyncio
import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

# Ensure project root is on PYTHONPATH
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import pytest

from mcp_servers.figma_server import FigmaMCPServer


@pytest.fixture
def project_root() -> Path:
    return Path(__file__).resolve().parent.parent.parent


@pytest.fixture
def figma_server(project_root: Path) -> FigmaMCPServer:
    """Live FigmaMCPServer pointing at the real figma-agent-core directory."""
    return FigmaMCPServer(str(project_root))


@pytest.fixture
def degraded_server(tmp_path: Path) -> FigmaMCPServer:
    """FigmaMCPServer with a missing figma-agent-core directory (degraded)."""
    empty_workspace = tmp_path / "no_figma_core"
    empty_workspace.mkdir()
    return FigmaMCPServer(str(empty_workspace))


def test_figma_server_initializes(figma_server: FigmaMCPServer) -> None:
    assert figma_server.name == "figma"
    assert figma_server._initialized is True
    tools = figma_server.get_tools_list()
    assert len(tools) == 6
    names = {t["name"] for t in tools}
    expected = {
        "figma_bootstrap",
        "figma_analyze",
        "figma_generate_spec",
        "figma_generate_component",
        "figma_download_assets",
        "figma_run_pipeline",
    }
    assert names == expected


def test_figma_server_degraded_without_core(degraded_server: FigmaMCPServer) -> None:
    assert degraded_server._degraded_reason is not None
    result = degraded_server.figma_run_pipeline(dry_run=True)
    assert result["status"] == "degraded"
    assert "figma-agent-core not found" in result["error"]


def test_figma_server_ping(figma_server: FigmaMCPServer) -> None:
    assert asyncio.run(figma_server.ping()) is True


def test_figma_tool_schemas(figma_server: FigmaMCPServer) -> None:
    for tool in figma_server.get_tools_list():
        assert "name" in tool
        assert "description" in tool
        assert "inputSchema" in tool
        schema = tool["inputSchema"]
        assert schema.get("type") == "object"
        assert "properties" in schema


def test_figma_bootstrap_invokes_script(figma_server: FigmaMCPServer) -> None:
    completed = MagicMock(spec=subprocess.CompletedProcess)
    completed.returncode = 0
    completed.stdout = "bootstrap ok"
    completed.stderr = ""

    with patch("subprocess.run", return_value=completed) as mock_run:
        result = figma_server.figma_bootstrap(force_refresh=True, node_id="123:456", api_depth=3)

    assert result["status"] == "success"
    assert result["returncode"] == 0
    mock_run.assert_called_once()
    args, kwargs = mock_run.call_args
    assert kwargs.get("cwd") == str(figma_server._core_dir)
    cmd = args[0]
    assert cmd[0] == sys.executable
    assert cmd[1] == "bootstrap.py"
    assert "--force" in cmd
    assert "--node-id" in cmd
    assert "123:456" in cmd
    assert "--api-depth" in cmd
    assert "3" in cmd


def test_figma_generate_component_invokes_agent(figma_server: FigmaMCPServer) -> None:
    completed = MagicMock(spec=subprocess.CompletedProcess)
    completed.returncode = 0
    completed.stdout = "component ok"
    completed.stderr = ""

    with patch("subprocess.run", return_value=completed) as mock_run:
        result = figma_server.figma_generate_component(
            file="figma_node.json",
            node_id="662:808",
            output_name="HeroSection",
            skip_assets=True,
        )

    assert result["status"] == "success"
    mock_run.assert_called_once()
    args, _ = mock_run.call_args
    cmd = args[0]
    assert cmd[1] == "agent.py"
    assert "--file" in cmd
    assert "figma_node.json" in cmd
    assert "--node-id" in cmd
    assert "662:808" in cmd
    assert "--output-name" in cmd
    assert "HeroSection" in cmd
    assert "--skip-assets" in cmd


def test_figma_run_pipeline_dry_run(figma_server: FigmaMCPServer) -> None:
    completed = MagicMock(spec=subprocess.CompletedProcess)
    completed.returncode = 0
    completed.stdout = "dry run ok"
    completed.stderr = ""

    with patch("subprocess.run", return_value=completed) as mock_run:
        result = figma_server.figma_run_pipeline(
            dry_run=True,
            all_sections=True,
            api_depth=2,
            spec_output="spec.md",
        )

    assert result["status"] == "success"
    mock_run.assert_called_once()
    args, _ = mock_run.call_args
    cmd = args[0]
    assert cmd[1] == "conductor.py"
    assert "--all" in cmd
    assert "--dry-run" in cmd
    assert "--all-sections" in cmd
    assert "--api-depth" in cmd
    assert "2" in cmd
    assert "--spec-output" in cmd
    assert "spec.md" in cmd


def test_figma_run_pipeline_handles_subprocess_error(figma_server: FigmaMCPServer) -> None:
    completed = MagicMock(spec=subprocess.CompletedProcess)
    completed.returncode = 1
    completed.stdout = ""
    completed.stderr = "token invalid"

    with patch("mcp_servers.figma_server.subprocess.run", return_value=completed):
        result = figma_server.figma_run_pipeline(dry_run=True)

    assert result["status"] == "error"
    assert result["returncode"] == 1
    assert result["stderr"] == "token invalid"


def test_figma_run_pipeline_timeout(figma_server: FigmaMCPServer) -> None:
    with patch("mcp_servers.figma_server.subprocess.run", side_effect=subprocess.TimeoutExpired("cmd", 600)):
        result = figma_server.figma_run_pipeline(dry_run=True)

    assert result["status"] == "timeout"


def test_figma_analyze_schema_has_optional_file(figma_server: FigmaMCPServer) -> None:
    tool = next(t for t in figma_server.get_tools_list() if t["name"] == "figma_analyze")
    props = tool["inputSchema"]["properties"]
    assert "file" in props
    assert props["file"]["type"] == "string"
    assert tool["inputSchema"].get("required", []) == []
