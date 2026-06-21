"""Unit tests for figma-agent-core/layout_engine.py.

Loads the module via importlib because the directory name contains a hyphen.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import Any, Dict

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent
LAYOUT_ENGINE_PATH = ROOT / "figma-agent-core" / "layout_engine.py"


def _load_layout_engine() -> Any:
    spec = importlib.util.spec_from_file_location("figma_layout_engine", str(LAYOUT_ENGINE_PATH))
    module = importlib.util.module_from_spec(spec)
    sys.modules["figma_layout_engine"] = module
    spec.loader.exec_module(module)
    return module


layout_engine = _load_layout_engine()


def _find_class(node: Dict[str, Any], class_name: str) -> bool:
    return class_name in node.get("classes", [])


def test_load_module() -> None:
    assert hasattr(layout_engine, "FigmaLayoutEngine")
    assert hasattr(layout_engine, "convert_figma_node")


def test_empty_node_returns_section() -> None:
    result = layout_engine.convert_figma_node({
        "id": "0:1",
        "name": "Canvas",
        "type": "FRAME",
        "visible": True,
    })
    root = result.root
    assert root.tag == "section"
    assert root.figma_id == "0:1"


def test_autolayout_vertical_with_gap_and_padding() -> None:
    node = {
        "id": "10:1",
        "name": "Features",
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
        "box": {"x": 0, "y": 0, "width": 1200, "height": 600},
        "children": [],
    }
    result = layout_engine.convert_figma_node(node)
    classes = result.root.classes
    assert "flex" in classes
    assert "flex-col" in classes
    assert "gap-[24px]" in classes
    assert "py-[64px]" in classes
    assert "px-[32px]" in classes
    assert "justify-center" in classes
    assert "items-center" in classes
    assert "w-[1200px]" in classes
    assert "h-[600px]" in classes


def test_autolayout_horizontal_space_between() -> None:
    node = {
        "id": "20:1",
        "name": "Header",
        "type": "FRAME",
        "visible": True,
        "layoutMode": "HORIZONTAL",
        "itemSpacing": 0,
        "paddingTop": 16,
        "paddingRight": 24,
        "paddingBottom": 16,
        "paddingLeft": 24,
        "primaryAxisAlignItems": "SPACE_BETWEEN",
        "counterAxisAlignItems": "CENTER",
        "children": [],
    }
    result = layout_engine.convert_figma_node(node)
    classes = result.root.classes
    assert "flex-row" in classes
    assert "justify-between" in classes
    assert "items-center" in classes
    assert "p-[16px]" not in classes
    assert "py-[16px]" in classes
    assert "px-[24px]" in classes


def test_text_node_typography() -> None:
    node = {
        "id": "30:1",
        "name": "Headline",
        "type": "TEXT",
        "visible": True,
        "characters": "Build fast",
        "box": {"x": 100, "y": 200, "width": 400, "height": 48},
        "style": {
            "fontFamily": "Inter",
            "fontSize": 40,
            "fontWeight": 700,
            "lineHeightPx": 48,
            "letterSpacing": -1,
            "textAlignHorizontal": "CENTER",
            "fills": [{"type": "SOLID", "hex": "#111827"}],
        },
    }
    result = layout_engine.convert_figma_node(node)
    root = result.root
    assert root.tag == "h1"
    assert root.text == "Build fast"
    assert "text-[40px]" in root.classes
    assert "font-[700]" in root.classes
    assert "font-[Inter]" in root.classes
    assert "text-center" in root.classes
    assert "text-[#111827]" in root.classes
    assert result.text_node_count == 1


def test_text_tag_fallback_to_paragraph() -> None:
    node = {
        "id": "31:1",
        "name": "Description",
        "type": "TEXT",
        "visible": True,
        "characters": "Some body text",
        "style": {"fontSize": 16, "fontWeight": 400},
    }
    result = layout_engine.convert_figma_node(node)
    assert result.root.tag == "p"


def test_asset_node_becomes_image() -> None:
    node = {
        "id": "40:1",
        "name": "Hero image",
        "type": "IMAGE",
        "visible": True,
        "isAsset": True,
        "publicPath": "/images/hero_40_1.png",
        "box": {"x": 0, "y": 0, "width": 600, "height": 400},
    }
    result = layout_engine.convert_figma_node(node)
    root = result.root
    assert root.tag == "img"
    assert root.src == "/images/hero_40_1.png"
    assert "w-[600px]" in root.classes
    assert "h-[400px]" in root.classes
    assert result.asset_count == 1


def test_shape_with_fill_and_radius() -> None:
    node = {
        "id": "50:1",
        "name": "Card bg",
        "type": "RECTANGLE",
        "visible": True,
        "box": {"x": 0, "y": 0, "width": 300, "height": 200},
        "fills": [{"type": "SOLID", "hex": "#ffffff"}],
        "cornerRadius": 16,
    }
    result = layout_engine.convert_figma_node(node)
    root = result.root
    assert root.tag == "div"
    assert "bg-white" in root.classes
    assert "rounded-2xl" in root.classes
    assert "w-[300px]" in root.classes
    assert "h-[200px]" in root.classes


def test_nested_autolayout_children_preserve_structure() -> None:
    child = {
        "id": "60:2",
        "name": "Row",
        "type": "FRAME",
        "visible": True,
        "layoutMode": "HORIZONTAL",
        "itemSpacing": 12,
        "children": [
            {
                "id": "60:3",
                "name": "Label",
                "type": "TEXT",
                "visible": True,
                "characters": "Label",
                "style": {"fontSize": 14, "fontWeight": 500},
            }
        ],
    }
    parent = {
        "id": "60:1",
        "name": "Wrapper",
        "type": "FRAME",
        "visible": True,
        "layoutMode": "VERTICAL",
        "itemSpacing": 8,
        "children": [child],
    }
    result = layout_engine.convert_figma_node(parent)
    assert result.root.tag == "section"
    assert result.root.children[0].tag == "div"
    assert "flex-row" in result.root.children[0].classes
    assert "gap-[12px]" in result.root.children[0].classes
    assert result.root.children[0].children[0].tag == "p"


def test_absolute_positioning_for_non_autolayout() -> None:
    parent = {
        "id": "70:1",
        "name": "Canvas",
        "type": "FRAME",
        "visible": True,
        "box": {"x": 0, "y": 0, "width": 800, "height": 600},
        "children": [
            {
                "id": "70:2",
                "name": "Badge",
                "type": "FRAME",
                "visible": True,
                "box": {"x": 720, "y": 20, "width": 60, "height": 24},
                "fills": [{"type": "SOLID", "hex": "#22c55e"}],
            }
        ],
    }
    result = layout_engine.convert_figma_node(parent)
    badge = result.root.children[0]
    assert "absolute" in badge.classes
    assert badge.inline_styles.get("left") == "720px"
    assert badge.inline_styles.get("top") == "20px"


def test_invisible_nodes_are_skipped() -> None:
    parent = {
        "id": "80:1",
        "name": "Wrapper",
        "type": "FRAME",
        "visible": True,
        "children": [
            {"id": "80:2", "name": "Hidden", "type": "TEXT", "visible": False},
            {"id": "80:3", "name": "Visible", "type": "TEXT", "visible": True, "characters": "OK"},
        ],
    }
    result = layout_engine.convert_figma_node(parent)
    assert len(result.root.children) == 1
    assert result.root.children[0].text == "OK"


def test_shadow_effect_maps_to_inline_style() -> None:
    node = {
        "id": "90:1",
        "name": "Shadow box",
        "type": "RECTANGLE",
        "visible": True,
        "box": {"width": 200, "height": 100},
        "effects": [
            {
                "type": "DROP_SHADOW",
                "hex": "rgba(0, 0, 0, 0.15)",
                "offset": {"x": 0, "y": 4},
                "radius": 16,
            }
        ],
    }
    result = layout_engine.convert_figma_node(node)
    assert result.root.inline_styles.get("box-shadow") == "0px 4px 16px rgba(0, 0, 0, 0.15)"


def test_stats_counters() -> None:
    node = {
        "id": "100:1",
        "name": "Section",
        "type": "FRAME",
        "visible": True,
        "children": [
            {"id": "100:2", "name": "T", "type": "TEXT", "visible": True, "characters": "A"},
            {"id": "100:3", "name": "I", "type": "IMAGE", "visible": True, "isAsset": True, "publicPath": "/images/i.png"},
            {"id": "100:4", "name": "D", "type": "FRAME", "visible": True},
        ],
    }
    result = layout_engine.convert_figma_node(node)
    assert result.node_count == 4
    assert result.text_node_count == 1
    assert result.asset_count == 1


def _load_fixture(name: str) -> Dict[str, Any]:
    path = Path(__file__).resolve().parent / "fixtures" / name
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def test_raw_color_computed_when_hex_missing() -> None:
    node = {
        "id": "110:1",
        "name": "Button",
        "type": "FRAME",
        "visible": True,
        "layoutMode": "HORIZONTAL",
        "absoluteBoundingBox": {"x": 0, "y": 0, "width": 120, "height": 40},
        "fills": [{"type": "SOLID", "color": {"r": 0.23, "g": 0.51, "b": 0.96, "a": 1}}],
    }
    result = layout_engine.convert_figma_node(node)
    assert "bg-[#3b82f5]" in result.root.classes


def test_gradient_stops_from_raw_figma() -> None:
    node = {
        "id": "120:1",
        "name": "Hero Section",
        "type": "FRAME",
        "visible": True,
        "layoutMode": "VERTICAL",
        "absoluteBoundingBox": {"x": 0, "y": 0, "width": 1440, "height": 600},
        "fills": [
            {
                "type": "GRADIENT_LINEAR",
                "gradientStops": [
                    {"position": 0, "color": {"r": 1, "g": 1, "b": 1, "a": 1}},
                    {"position": 1, "color": {"r": 0, "g": 0, "b": 0, "a": 1}},
                ],
            }
        ],
    }
    result = layout_engine.convert_figma_node(node)
    assert result.root.inline_styles.get("background") == "linear-gradient(180deg, #ffffff 0%, #000000 100%)"


def test_vector_without_image_fill_becomes_shape() -> None:
    node = {
        "id": "130:1",
        "name": "Icon",
        "type": "VECTOR",
        "visible": True,
        "absoluteBoundingBox": {"x": 0, "y": 0, "width": 48, "height": 48},
        "fills": [{"type": "SOLID", "color": {"r": 0.23, "g": 0.51, "b": 0.96, "a": 1}}],
    }
    result = layout_engine.convert_figma_node(node)
    assert result.root.tag == "div"
    assert result.root.src is None
    assert "bg-[#3b82f5]" in result.root.classes


def test_counter_axis_stretch_maps_to_items_stretch() -> None:
    node = {
        "id": "140:1",
        "name": "Row",
        "type": "FRAME",
        "visible": True,
        "layoutMode": "HORIZONTAL",
        "counterAxisAlignItems": "STRETCH",
        "children": [],
    }
    result = layout_engine.convert_figma_node(node)
    assert "items-stretch" in result.root.classes


def test_semantic_tags_on_saas_landing_fixture() -> None:
    data = _load_fixture("saas_landing.json")
    result = layout_engine.convert_figma_node(data)
    root = result.root

    navbar = root.children[0]
    assert navbar.tag == "header"
    assert "w-[1440px]" in navbar.classes
    assert "h-[72px]" in navbar.classes

    hero = root.children[1]
    assert hero.tag == "section"
    assert hero.inline_styles.get("background", "").startswith("linear-gradient")

    hero_buttons = hero.children[2]
    assert hero_buttons.tag == "div"

    features = root.children[2]
    cards_row = features.children[1]
    assert "items-stretch" in cards_row.classes

    card = cards_row.children[0]
    assert card.tag == "article"
    assert "bg-[#f7faff]" in card.classes
    assert card.inline_styles.get("box-shadow", "").startswith("0px 4px 24px")

    card_title = card.children[1]
    assert card_title.tag == "h3"

    footer = root.children[3]
    assert footer.tag == "footer"
    assert "bg-[#0d0d14]" in footer.classes


def test_absolute_bounding_box_fallback_for_size() -> None:
    node = {
        "id": "150:1",
        "name": "Box",
        "type": "FRAME",
        "visible": True,
        "absoluteBoundingBox": {"x": 0, "y": 0, "width": 100, "height": 200},
    }
    result = layout_engine.convert_figma_node(node)
    assert "w-[100px]" in result.root.classes
    assert "h-[200px]" in result.root.classes
