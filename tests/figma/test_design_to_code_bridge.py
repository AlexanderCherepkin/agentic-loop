"""Tests for figma-agent-core/design_to_code_bridge.py."""

from __future__ import annotations

import importlib.util
import sys
import tempfile
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent
BRIDGE_PATH = ROOT / "figma-agent-core" / "design_to_code_bridge.py"
FIXTURES = ROOT / "tests" / "figma" / "fixtures"


def _load_bridge() -> Any:
    spec = importlib.util.spec_from_file_location("figma_design_to_code_bridge", str(BRIDGE_PATH))
    module = importlib.util.module_from_spec(spec)
    sys.modules["figma_design_to_code_bridge"] = module
    spec.loader.exec_module(module)
    return module


bridge = _load_bridge()


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


def test_process_returns_all_three_artifacts():
    doc = _minimal_figma_doc()
    result = bridge.process_figma_document(doc, workspace_root=".")

    assert result.tokens is not None
    assert result.layout is not None
    assert result.component_tree is not None
    assert result.tokens.colors
    assert result.layout.root is not None
    assert result.component_tree.root is not None


def test_layout_root_reflects_autolayout():
    doc = _minimal_figma_doc()
    result = bridge.process_figma_document(doc, workspace_root=".")
    root = result.layout.root

    assert root.layout_mode == "VERTICAL"
    assert root.flex_direction == "column"
    assert root.justify_content == "center"
    assert root.align_items == "center"
    assert root.gap_px == 24.0
    assert root.padding == {"top": 64.0, "right": 32.0, "bottom": 64.0, "left": 32.0}


def test_component_tree_maps_tailwind_classes():
    doc = _minimal_figma_doc()
    result = bridge.process_figma_document(doc, workspace_root=".")
    root = result.component_tree.root

    assert any("flex" in cls for cls in root.tailwind_classes)
    assert result.component_tree.components, "expected at least one extracted component"

    hero_component = result.component_tree.components[0]
    assert hero_component["name"] == "HeroSection"
    assert hero_component["figma_name"] == "Hero_section"
    assert hero_component["file_path"].endswith("HeroSection.tsx")


def test_extracted_components_are_registered():
    doc = _minimal_figma_doc()
    result = bridge.process_figma_document(doc, workspace_root=".")

    assert result.component_tree.page_component is not None
    assert isinstance(result.component_tree.components, list)


def test_summary_counts_are_present():
    doc = _minimal_figma_doc()
    result = bridge.process_figma_document(doc, workspace_root=".")

    assert result.summary["layout_nodes"] >= 4
    assert result.summary["autolayout_nodes"] >= 2
    assert result.summary["text_nodes"] == 2


def test_write_artifacts_creates_files():
    doc = _minimal_figma_doc()
    result = bridge.process_figma_document(doc, workspace_root=".")
    bridge_instance = bridge.DesignToCodeBridge(workspace_root=".")

    with tempfile.TemporaryDirectory() as tmp:
        paths = bridge_instance.write_artifacts(result, tmp)
        assert Path(paths["design_tokens"]).exists()
        assert Path(paths["layout_data"]).exists()
        assert Path(paths["component_tree"]).exists()
        assert Path(paths["summary"]).exists()


def test_to_json_is_serializable():
    doc = _minimal_figma_doc()
    result = bridge.process_figma_document(doc, workspace_root=".")
    json_text = result.to_json()
    assert isinstance(json_text, str)
    assert "tokens" in json_text
    assert "layout" in json_text
    assert "component_tree" in json_text
