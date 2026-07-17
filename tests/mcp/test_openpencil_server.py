"""pytest tests for the Open Pencil MCP server.

Uses monkeypatch on subprocess to avoid needing a real `npx open-pencil`
runner installed.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import pytest

from mcp_servers.openpencil_server import OpenPencilMCPServer


@pytest.fixture
def server(tmp_path: Path) -> OpenPencilMCPServer:
    return OpenPencilMCPServer(str(tmp_path))


def test_server_initializes(server: OpenPencilMCPServer) -> None:
    assert server.name == "open_pencil"
    assert server._initialized is True
    tools = server.get_tools_list()
    assert len(tools) == 4
    names = {t["name"] for t in tools}
    assert names == {
        "openpencil_from_design_md",
        "openpencil_from_figma_json",
        "openpencil_audit_output",
        "openpencil_check_runner",
    }


def test_tool_schemas(server: OpenPencilMCPServer) -> None:
    for tool in server.get_tools_list():
        assert "name" in tool
        assert "description" in tool
        assert "inputSchema" in tool
        schema = tool["inputSchema"]
        assert schema.get("type") == "object"
        assert "properties" in schema


def test_check_runner_degraded(server: OpenPencilMCPServer, monkeypatch: Any) -> None:
    def fake_run(*args: Any, **kwargs: Any) -> subprocess.CompletedProcess:
        return subprocess.CompletedProcess(args=args, returncode=1, stdout="", stderr="not found")

    monkeypatch.setattr(subprocess, "run", fake_run)
    result = server.openpencil_check_runner()
    assert result["is_error"] is False
    assert result["available"] is False
    assert result["status"] == "degraded"


def test_from_design_md_missing_file(server: OpenPencilMCPServer) -> None:
    result = server.openpencil_from_design_md("/nonexistent/DESIGN.md")
    assert result["is_error"] is True
    assert "DESIGN.md not found" in result["errors"][0]


def test_from_design_md_missing_sections(server: OpenPencilMCPServer, tmp_path: Path) -> None:
    design_md = tmp_path / "DESIGN.md"
    design_md.write_text("# Brand Core\nNo sections.\n")
    result = server.openpencil_from_design_md(str(design_md))
    assert result["is_error"] is True
    assert result["violations_before"]
    assert "missing_design_section" in result["violations_before"][0]["rule"]


def test_from_design_md_success(server: OpenPencilMCPServer, tmp_path: Path, monkeypatch: Any) -> None:
    design_md = tmp_path / "DESIGN.md"
    design_md.write_text(
        "# Design\n\nColor System\nTypography\nAnti-Slop Gates\n", encoding="utf-8"
    )
    out = tmp_path / "open-pencil-output"

    class CompletedProcess:
        returncode = 0
        stdout = "generated"
        stderr = ""

    def fake_run(args: Any, **kwargs: Any) -> subprocess.CompletedProcess:
        out.mkdir(parents=True, exist_ok=True)
        (out / "Button.tsx").write_text("// generated", encoding="utf-8")
        return CompletedProcess()

    monkeypatch.setattr(subprocess, "run", fake_run)

    result = server.openpencil_from_design_md(str(design_md), output_dir=str(out))
    assert result["is_error"] is False
    assert result["ok"] is True
    assert result["component_count"] >= 1


def test_from_figma_json_missing_file(server: OpenPencilMCPServer) -> None:
    result = server.openpencil_from_figma_json("/nonexistent/figma.json")
    assert result["is_error"] is True
    assert "Figma JSON not found" in result["errors"][0]


def test_audit_output_detects_slop(server: OpenPencilMCPServer, tmp_path: Path) -> None:
    out = tmp_path / "open-pencil-output"
    out.mkdir(parents=True)
    bad = out / "Card.tsx"
    bad.write_text('<div className="shadow-md transition-all font-Inter text-gray-500"></div>')

    result = server.openpencil_audit_output(str(out))
    rules = {v["rule"] for v in result["violations_after"]}
    assert "generic_shadow" in rules
    assert "layout_transition" in rules
    assert "default_font" in rules
    assert "flat_gray_text" in rules
    assert result["ok"] is False


def test_audit_output_with_tokens(server: OpenPencilMCPServer, tmp_path: Path) -> None:
    out = tmp_path / "open-pencil-output"
    out.mkdir(parents=True)
    (out / "Button.tsx").write_text('// clean', encoding="utf-8")

    tokens = tmp_path / "design_tokens.json"
    tokens.write_text(
        '{"fontFamily": {"body": {"$value": "Inter, sans-serif"}}, "color": {"muted": {"$value": "#808080"}}}'
    )

    result = server.openpencil_audit_output(str(out), tokens_path=str(tokens))
    rules = {v["rule"] for v in result["violations_after"]}
    assert "forbidden_font" in rules
    assert "flat_gray_muted" in rules


def test_ping(server: OpenPencilMCPServer) -> None:
    import asyncio

    assert asyncio.run(server.ping()) is True
