"""pytest tests for the Brand Compliance MCP server.

These tests verify tool registration, policy checks, token audits, and PR slop
scanning without requiring a real DESIGN.md or design_tokens.json in the repo.
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

# Ensure project root is on PYTHONPATH
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import pytest

from mcp_servers.brand_compliance_server import BrandComplianceMCPServer


@pytest.fixture
def server(tmp_path: Path) -> BrandComplianceMCPServer:
    return BrandComplianceMCPServer(str(tmp_path))


def test_server_name_and_tool_count(server: BrandComplianceMCPServer) -> None:
    assert server.name == "brand_compliance"
    assert server._initialized is True
    tools = server.get_tools_list()
    assert len(tools) == 3
    names = {t["name"] for t in tools}
    assert names == {"check_brand_policy", "check_design_tokens", "check_pr_slop"}


def test_tool_schemas(server: BrandComplianceMCPServer) -> None:
    for tool in server.get_tools_list():
        assert "name" in tool
        assert "description" in tool
        assert "inputSchema" in tool
        schema = tool["inputSchema"]
        assert schema.get("type") == "object"
        assert "properties" in schema


def test_check_brand_policy_missing_files(server: BrandComplianceMCPServer) -> None:
    result = server.check_brand_policy()
    assert result["status"] == "error"
    assert result["is_error"] is True
    assert not result["design_md_exists"]
    assert not result["tokens_exists"]
    assert result["errors"]


def test_check_brand_policy_aligned(tmp_path: Path, server: BrandComplianceMCPServer) -> None:
    design_md = tmp_path / "DESIGN.md"
    design_md.write_text("direction: premium-light\ncolor: #0a0a0a\n")
    tokens = tmp_path / "design_tokens.json"
    tokens.write_text(
        '{"direction": {"$value": "premium-light"}, "color": {"surface": {"$type": "color", "$value": "#0a0a0a"}}}'
    )

    result = server.check_brand_policy()
    assert result["status"] == "success"
    assert result["is_error"] is False
    assert result["direction_match"]["mismatch"] is False
    assert result["palette_match"]["mismatch"] is False
    assert result["ok"] is True


def test_check_design_tokens_detects_forbidden_fonts(tmp_path: Path, server: BrandComplianceMCPServer) -> None:
    tokens = tmp_path / "design_tokens.json"
    tokens.write_text(
        '{"fontFamily": {"body": {"$value": "Inter, sans-serif"}, "heading": {"$value": "Papyrus"}}}'
    )

    result = server.check_design_tokens()
    assert result["status"] == "success"
    assert result["is_error"] is False
    violations = result["violations"]
    assert any(v["rule"] == "forbidden_font" and v["family"] == "inter" for v in violations)
    assert any(v["rule"] == "forbidden_font" and v["family"] == "papyrus" for v in violations)
    assert result["ok"] is False


def test_check_design_tokens_allows_clean_tokens(tmp_path: Path, server: BrandComplianceMCPServer) -> None:
    tokens = tmp_path / "design_tokens.json"
    tokens.write_text(
        '{"fontFamily": {"body": {"$value": "Manrope, sans-serif"}}, "color": {"surface": {"$type": "color", "$value": "#0a0a0a"}}}'
    )

    result = server.check_design_tokens(strict=True)
    assert result["status"] == "success"
    assert result["is_error"] is False
    assert result["violations"] == []
    assert result["ok"] is True


def test_check_pr_slop_detects_slop(server: BrandComplianceMCPServer, tmp_path: Path) -> None:
    slop_file = tmp_path / "Sloppy.tsx"
    slop_file.write_text(
        '<div className="font-Inter text-gray-500 shadow-md transition-all w-17px">slop</div>'
    )
    result = server.check_pr_slop(path=str(slop_file))
    assert result["status"] == "success"
    assert result["is_error"] is False
    rules = {v["rule"] for v in result["violations"]}
    assert "default_font" in rules
    assert "flat_gray_text" in rules
    assert "generic_shadow" in rules
    assert "layout_transition" in rules
    assert "magic_inline" in rules
    assert result["ok"] is False


def test_check_pr_slop_clean(server: BrandComplianceMCPServer, tmp_path: Path) -> None:
    clean_file = tmp_path / "Clean.tsx"
    clean_file.write_text(
        '<div className="font-sans text-surface-900 shadow-elevation transition-colors">clean</div>'
    )
    result = server.check_pr_slop(path=str(clean_file))
    assert result["status"] == "success"
    assert result["is_error"] is False
    assert result["violations"] == []
    assert result["ok"] is True


def test_check_pr_slop_from_patch_text(server: BrandComplianceMCPServer) -> None:
    patch = "+ .font-Roboto { font-family: Roboto; }\n+ .shadow-lg { box-shadow: 0 10px 15px; }"
    result = server.check_pr_slop(path="", patch_text=patch)
    rules = {v["rule"] for v in result["violations"]}
    assert "default_font" in rules
    assert "generic_shadow" in rules


def test_ping(server: BrandComplianceMCPServer) -> None:
    import asyncio

    assert asyncio.run(server.ping()) is True


def test_check_brand_policy_resolves_explicit_paths(tmp_path: Path) -> None:
    alt = tmp_path / "alt"
    alt.mkdir()
    design_md = alt / "BRAND.md"
    design_md.write_text("direction: dark\ncolor: #ff0000\n")
    tokens = alt / "brand_tokens.json"
    tokens.write_text(
        '{"direction": {"$value": "dark"}, "color": {"accent": {"$type": "color", "$value": "#ff0000"}}}'
    )

    server = BrandComplianceMCPServer(str(tmp_path))
    result = server.check_brand_policy(
        design_md_path=str(design_md), tokens_path=str(tokens)
    )
    assert result["status"] == "success"
    assert result["ok"] is True
