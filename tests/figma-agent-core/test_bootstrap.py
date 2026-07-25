"""Smoke tests for figma-agent-core/bootstrap.py."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "figma-agent-core"))

from bootstrap import (
    FigmaExtractor,
    rgba_to_hex,
    rgba_to_rgb,
    extract_fills,
    extract_effects,
    extract_text_style,
    find_node_by_id,
    load_existing_cache,
    save_cache,
)


class TestColorHelpers:
    def test_rgba_to_hex_opaque(self):
        assert rgba_to_hex({"r": 1.0, "g": 0.0, "b": 0.0, "a": 1.0}) == "#ff0000"

    def test_rgba_to_hex_transparent(self):
        assert rgba_to_hex({"r": 0.0, "g": 1.0, "b": 0.0, "a": 0.5}) == "#00ff0080"

    def test_rgba_to_hex_none(self):
        assert rgba_to_hex(None) is None

    def test_rgba_to_rgb_opaque(self):
        assert rgba_to_rgb({"r": 0.0, "g": 0.0, "b": 1.0, "a": 1.0}) == "rgb(0, 0, 255)"

    def test_rgba_to_rgb_transparent(self):
        assert rgba_to_rgb({"r": 1.0, "g": 1.0, "b": 1.0, "a": 0.25}) == "rgba(255, 255, 255, 0.25)"


class TestExtractFills:
    def test_solid_fill(self):
        fills = [{"type": "SOLID", "color": {"r": 1.0, "g": 0.0, "b": 0.0, "a": 1.0}}]
        result = extract_fills(fills)
        assert result[0]["type"] == "SOLID"
        assert result[0]["hex"] == "#ff0000"

    def test_gradient_fill(self):
        fills = [{"type": "GRADIENT_LINEAR", "gradientStops": [{"position": 0, "color": {"r": 0, "g": 0, "b": 0, "a": 1}}]}]
        result = extract_fills(fills)
        assert result[0]["type"] == "GRADIENT_LINEAR"
        assert "stops" in result[0]

    def test_image_fill(self):
        fills = [{"type": "IMAGE", "imageRef": "abc", "scaleMode": "FILL"}]
        result = extract_fills(fills)
        assert result[0]["type"] == "IMAGE"
        assert result[0]["imageRef"] == "abc"

    def test_empty_fills(self):
        assert extract_fills([]) is None
        assert extract_fills(None) is None


class TestExtractEffects:
    def test_drop_shadow(self):
        effects = [{
            "type": "DROP_SHADOW",
            "visible": True,
            "color": {"r": 0, "g": 0, "b": 0, "a": 0.25},
            "offset": {"x": 0, "y": 4},
            "radius": 8,
            "spread": 0,
        }]
        result = extract_effects(effects)
        assert result[0]["type"] == "DROP_SHADOW"
        assert result[0]["radius"] == 8

    def test_hidden_effect_skipped(self):
        effects = [{"type": "DROP_SHADOW", "visible": False}]
        assert extract_effects(effects) is None

    def test_layer_blur(self):
        effects = [{"type": "LAYER_BLUR", "visible": True, "radius": 10}]
        result = extract_effects(effects)
        assert result[0]["type"] == "LAYER_BLUR"


class TestExtractTextStyle:
    def test_extracts_font_properties(self):
        style = {
            "fontFamily": "Inter",
            "fontSize": 16,
            "fontWeight": 500,
            "lineHeightPx": 24,
            "letterSpacing": 0.5,
            "textAlignHorizontal": "LEFT",
            "fills": [{"type": "SOLID", "color": {"r": 0, "g": 0, "b": 0, "a": 1}}],
        }
        result = extract_text_style(style)
        assert result["fontFamily"] == "Inter"
        assert result["fontSize"] == 16
        assert result["fills"][0]["hex"] == "#000000"


class TestFigmaExtractorParseUrl:
    def test_parse_file_url(self):
        extractor = FigmaExtractor("token")
        parsed = extractor.parse_url("https://www.figma.com/file/ABC123/MyFile?node-id=1:2")
        assert parsed == {"file_key": "ABC123", "node_id": "1:2"}

    def test_parse_design_url(self):
        extractor = FigmaExtractor("token")
        parsed = extractor.parse_url("https://www.figma.com/design/XYZ789/MyFile")
        assert parsed == {"file_key": "XYZ789", "node_id": "0:1"}

    def test_parse_invalid_url(self):
        extractor = FigmaExtractor("token")
        assert extractor.parse_url("https://example.com") is None


class TestFigmaExtractorIsStructural:
    def test_frame_is_structural(self):
        assert FigmaExtractor.is_structural({"type": "FRAME", "children": []}) is True

    def test_text_with_characters_is_structural(self):
        assert FigmaExtractor.is_structural({"type": "TEXT", "characters": "Hello"}) is True

    def test_invisible_group_not_structural(self):
        assert FigmaExtractor.is_structural({"type": "GROUP", "children": []}) is False

    def test_layout_mode_makes_structural(self):
        assert FigmaExtractor.is_structural({"type": "FRAME", "layoutMode": "HORIZONTAL"}) is True


class TestFigmaExtractorCompressNode:
    def test_compresses_visible_node(self):
        extractor = FigmaExtractor("token")
        node = {
            "id": "1:1",
            "name": "Frame",
            "type": "FRAME",
            "visible": True,
            "absoluteBoundingBox": {"x": 0, "y": 0, "width": 100, "height": 100},
        }
        result = extractor.compress_node(node)
        assert result["id"] == "1:1"
        assert result["box"]["width"] == 100

    def test_invisible_node_returns_none(self):
        extractor = FigmaExtractor("token")
        assert extractor.compress_node({"visible": False}) is None

    def test_max_depth_triggers_summary(self):
        extractor = FigmaExtractor("token")
        node = {
            "id": "1:1",
            "name": "Parent",
            "type": "FRAME",
            "visible": True,
            "children": [{"id": "1:2", "name": "Child", "type": "TEXT", "visible": True, "characters": "x"}],
        }
        result = extractor.compress_node(node, depth=8, max_depth=8)
        assert "children_summary" in result


class TestFindNodeById:
    def test_finds_root(self):
        root = {"id": "1:1", "children": []}
        assert find_node_by_id(root, "1:1") == root

    def test_finds_nested(self):
        child = {"id": "2:2", "children": []}
        root = {"id": "1:1", "children": [child]}
        assert find_node_by_id(root, "2:2") == child

    def test_not_found(self):
        assert find_node_by_id({"id": "1:1", "children": []}, "9:9") is None


class TestCacheHelpers:
    def test_load_existing_cache_missing(self):
        assert load_existing_cache() is None

    def test_save_and_load_cache(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        data = {"id": "1:1"}
        save_cache(data)
        loaded = load_existing_cache()
        assert loaded == data
