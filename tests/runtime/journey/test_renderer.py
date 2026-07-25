"""Tests for the /journey SVG renderer."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))

from runtime.journey.parser import JourneyEdge, JourneyGraph, JourneyNode
from runtime.journey.renderer import JourneyRenderer


class TestJourneyRenderer:
    def test_render_includes_nodes_and_edges(self):
        graph = JourneyGraph(
            nodes=[
                JourneyNode(id="index", label="Index", type="index"),
                JourneyNode(id="auth", label="Auth", type="wiki"),
            ],
            edges=[JourneyEdge(source="index", target="auth")],
        )
        result = JourneyRenderer().render(graph)
        assert result.node_count == 2
        assert result.edge_count == 1
        assert "index" in result.html
        assert "Auth" in result.html
        assert "<svg " in result.html

    def test_render_to_file_writes_html(self, tmp_path):
        graph = JourneyGraph(nodes=[JourneyNode(id="a", label="A", type="wiki")])
        out_path = tmp_path / "journey.html"
        result = JourneyRenderer().render_to_file(graph, out_path)
        assert out_path.exists()
        assert out_path.read_text(encoding="utf-8") == result.html
