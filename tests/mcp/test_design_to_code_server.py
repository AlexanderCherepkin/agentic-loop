"""pytest tests for the Design-to-Code MCP server."""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import pytest

from mcp_servers.design_to_code_server import DesignToCodeMCPServer


ROOT = Path(__file__).resolve().parent.parent.parent


def _minimal_figma_doc() -> dict[str, Any]:
    return {
        "id": "0:1",
        "name": "Landing Page",
        "type": "FRAME",
        "visible": True,
        "layoutMode": "VERTICAL",
        "itemSpacing": 24,
        "paddingTop": 64,
        "paddingRight": 32,
        "paddingBottom": 64,
        "paddingLeft": 32,
        "primaryAxisAlignItems": "CENTER",
        "counterAxisAlignItems": "CENTER",
        "box": {"x": 0, "y": 0, "width": 1200, "height": 800},
        "fills": [{"type": "SOLID", "color": {"r": 1, "g": 1, "b": 1}}],
        "children": [
            {
                "id": "1:1",
                "name": "Hero section",
                "type": "FRAME",
                "visible": True,
                "layoutMode": "VERTICAL",
                "itemSpacing": 16,
                "paddingTop": 48,
                "paddingRight": 24,
                "paddingBottom": 48,
                "paddingLeft": 24,
                "primaryAxisAlignItems": "CENTER",
                "counterAxisAlignItems": "CENTER",
                "box": {"x": 0, "y": 0, "width": 1200, "height": 400},
                "children": [
                    {
                        "id": "1:2",
                        "name": "Headline",
                        "type": "TEXT",
                        "visible": True,
                        "characters": "Build faster",
                        "box": {"x": 0, "y": 0, "width": 400, "height": 56},
                        "style": {
                            "fontFamily": "Inter",
                            "fontSize": 48,
                            "fontWeight": 700,
                            "lineHeightPx": 52,
                            "fills": [{"type": "SOLID", "color": {"r": 0.1, "g": 0.1, "b": 0.12}}],
                        },
                    },
                    {
                        "id": "1:3",
                        "name": "CTA",
                        "type": "TEXT",
                        "visible": True,
                        "characters": "Get started",
                        "box": {"x": 0, "y": 0, "width": 120, "height": 24},
                        "style": {
                            "fontFamily": "Inter",
                            "fontSize": 16,
                            "fontWeight": 600,
                            "lineHeightPx": 24,
                            "fills": [{"type": "SOLID", "color": {"r": 0.23, "g": 0.51, "b": 0.96}}],
                        },
                    },
                ],
            }
        ],
    }


@pytest.fixture
def server(tmp_path: Path) -> DesignToCodeMCPServer:
    """Provide an isolated server backed by a temporary copy of figma-agent-core."""
    shutil.copytree(
        ROOT / "figma-agent-core",
        tmp_path / "figma-agent-core",
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
    )
    return DesignToCodeMCPServer(str(tmp_path))


@pytest.fixture
def figma_json_path(tmp_path: Path) -> str:
    path = tmp_path / "figma_node.json"
    path.write_text(json.dumps(_minimal_figma_doc(), ensure_ascii=False), encoding="utf-8")
    return str(path)


def test_server_initializes(server: DesignToCodeMCPServer) -> None:
    assert server.name == "design_to_code"
    assert server._initialized is True
    tools = server.get_tools_list()
    assert len(tools) == 6
    names = {t["name"] for t in tools}
    assert names == {
        "process_figma_document",
        "extract_tokens",
        "extract_layout",
        "extract_component_tree",
        "write_design_to_code_artifacts",
        "check_bridge_available",
    }


def test_tool_schemas(server: DesignToCodeMCPServer) -> None:
    for tool in server.get_tools_list():
        assert "name" in tool
        assert "description" in tool
        assert "inputSchema" in tool
        schema = tool["inputSchema"]
        assert schema.get("type") == "object"
        assert "properties" in schema


def test_check_bridge_available(server: DesignToCodeMCPServer) -> None:
    result = server.check_bridge_available()
    assert result["is_error"] is False
    assert result["available"] is True
    assert result["status"] == "success"


def test_process_figma_document(server: DesignToCodeMCPServer, figma_json_path: str, tmp_path: Path) -> None:
    output_dir = tmp_path / "d2c-output"
    result = server.process_figma_document(figma_json_path, output_dir=str(output_dir))

    assert result["status"] == "success"
    assert result["is_error"] is False
    assert "tokens" in result
    assert "layout" in result
    assert "component_tree" in result
    assert result["summary"]["layout_nodes"] >= 4
    assert result["summary"]["text_nodes"] == 2
    assert output_dir.exists()
    assert (output_dir / "design_tokens.json").exists()
    assert (output_dir / "layout_data.json").exists()
    assert (output_dir / "component_tree.json").exists()
    assert (output_dir / "design_to_code_summary.json").exists()


def test_extract_tokens(server: DesignToCodeMCPServer, figma_json_path: str) -> None:
    result = server.extract_tokens(figma_json_path)
    assert result["status"] == "success"
    assert result["is_error"] is False
    assert "tokens" in result
    assert "colors" in result["tokens"]


def test_extract_layout(server: DesignToCodeMCPServer, figma_json_path: str) -> None:
    result = server.extract_layout(figma_json_path)
    assert result["status"] == "success"
    assert result["is_error"] is False
    assert "layout" in result
    assert result["layout"]["root"]["flex_direction"] == "column"


def test_extract_component_tree(server: DesignToCodeMCPServer, figma_json_path: str) -> None:
    result = server.extract_component_tree(figma_json_path)
    assert result["status"] == "success"
    assert result["is_error"] is False
    assert "component_tree" in result
    assert result["component_tree"]["root"]["semantic_tag"] in {"div", "section", "main"}


def test_write_design_to_code_artifacts(server: DesignToCodeMCPServer, figma_json_path: str, tmp_path: Path) -> None:
    process_result = server.process_figma_document(figma_json_path)
    output_dir = tmp_path / "written-artifacts"

    result = server.write_design_to_code_artifacts(
        json.dumps(
            {
                "tokens": process_result["tokens"],
                "layout": process_result["layout"],
                "component_tree": process_result["component_tree"],
                "summary": process_result["summary"],
            },
            ensure_ascii=False,
        ),
        output_dir=str(output_dir),
    )

    assert result["status"] == "success"
    assert result["is_error"] is False
    assert (output_dir / "design_tokens.json").exists()
    assert (output_dir / "layout_data.json").exists()
    assert (output_dir / "component_tree.json").exists()
    assert (output_dir / "design_to_code_summary.json").exists()


def test_process_missing_file(server: DesignToCodeMCPServer) -> None:
    result = server.process_figma_document("/nonexistent/figma.json")
    assert result["status"] == "error"
    assert result["is_error"] is True
    assert "Figma JSON not found" in result["error"]


def test_ping(server: DesignToCodeMCPServer) -> None:
    import asyncio

    assert asyncio.run(server.ping()) is True
