"""SVG radial renderer for the /journey memory graph."""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from .config import JourneyConfig
from .parser import JourneyEdge, JourneyGraph, JourneyNode


@dataclass
class JourneyRenderResult:
    """Output of the renderer."""

    html: str
    node_count: int
    edge_count: int


class JourneyRenderer:
    """Render a JourneyGraph as a self-contained radial SVG HTML page."""

    _TYPE_ORDER = {"index": 0, "wiki": 1, "skill": 2}
    _COLORS = {
        "index": "#f59e0b",
        "wiki": "#38bdf8",
        "skill": "#a78bfa",
    }

    def __init__(self, config: JourneyConfig | None = None):
        self.config = config or JourneyConfig()

    def render(self, graph: JourneyGraph) -> JourneyRenderResult:
        """Return a complete HTML string with an embedded radial SVG graph."""
        positions = self._layout(graph)
        svg = self._build_svg(graph, positions)
        html = self._wrap_html(svg, len(graph.nodes), len(graph.edges))
        return JourneyRenderResult(html=html, node_count=len(graph.nodes), edge_count=len(graph.edges))

    def render_to_file(self, graph: JourneyGraph, path: str | Path) -> JourneyRenderResult:
        """Render and write the HTML file, returning the result."""
        result = self.render(graph)
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_text(result.html, encoding="utf-8")
        return result

    def _layout(self, graph: JourneyGraph) -> dict[str, tuple[float, float]]:
        center_x = self.config.width / 2
        center_y = self.config.height / 2
        margin = 60
        max_radius = min(self.config.width, self.config.height) / 2 - margin
        nodes_by_layer: dict[int, list[JourneyNode]] = {0: [], 1: [], 2: []}
        for node in graph.nodes:
            layer = self._TYPE_ORDER.get(node.type, 1)
            nodes_by_layer[layer].append(node)

        positions: dict[str, tuple[float, float]] = {}
        if nodes_by_layer[0]:
            positions[nodes_by_layer[0][0].id] = (center_x, center_y)

        layer_count = max(1, len([layer for layer in nodes_by_layer if nodes_by_layer[layer]]))
        radius_step = max_radius / layer_count

        for layer, nodes in nodes_by_layer.items():
            if not nodes or layer == 0 and positions:
                continue
            radius = radius_step * (layer + 0.5)
            angle_offset = layer * (math.pi / 3)
            for i, node in enumerate(nodes):
                angle = angle_offset + (2 * math.pi * i / max(1, len(nodes)))
                x = center_x + radius * math.cos(angle)
                y = center_y + radius * math.sin(angle)
                positions[node.id] = (x, y)
        return positions

    def _build_svg(self, graph: JourneyGraph, positions: dict[str, tuple[float, float]]) -> str:
        lines: list[str] = [
            f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {self.config.width} {self.config.height}" width="{self.config.width}" height="{self.config.height}" role="img" aria-label="Journey radial memory graph">',
            '  <defs>',
            '    <marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">',
            '      <path d="M 0 0 L 10 5 L 0 10 z" fill="#64748b" />',
            '    </marker>',
            '  </defs>',
            '  <rect width="100%" height="100%" fill="#0f172a" />',
        ]

        for edge in graph.edges:
            if edge.source not in positions or edge.target not in positions:
                continue
            x1, y1 = positions[edge.source]
            x2, y2 = positions[edge.target]
            mid_x = (x1 + x2) / 2
            mid_y = (y1 + y2) / 2
            # Offset control point outward to curve edges.
            cx = mid_x + (mid_x - self.config.width / 2) * 0.15
            cy = mid_y + (mid_y - self.config.height / 2) * 0.15
            lines.append(
                f'  <path d="M {x1:.1f},{y1:.1f} Q {cx:.1f},{cy:.1f} {x2:.1f},{y2:.1f}" '
                f'stroke="#475569" stroke-width="1" fill="none" marker-end="url(#arrow)" />'
            )

        for node in graph.nodes:
            x, y = positions.get(node.id, (self.config.width / 2, self.config.height / 2))
            color = self._COLORS.get(node.type, "#94a3b8")
            r = 8 if node.type == "index" else 6
            title = self._node_title(node)
            lines.append(
                f'  <g class="node" data-id="{node.id}">'
                f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{r}" fill="{color}" stroke="#0f172a" stroke-width="2" />'
                f'<title>{title}</title>'
                f'<text x="{x:.1f}" y="{y + r + 12:.1f}" text-anchor="middle" fill="#e2e8f0" font-size="10">{self._escape(node.label)}</text>'
                f'</g>'
            )

        lines.append("  </svg>")
        return "\n".join(lines)

    def _wrap_html(self, svg: str, node_count: int, edge_count: int) -> str:
        return f"""
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>/journey — memory graph</title>
  <style>
    body {{ margin: 0; background: #0f172a; color: #e2e8f0; font-family: system-ui, sans-serif; }}
    header {{ padding: 1rem 1.5rem; border-bottom: 1px solid #334155; }}
    h1 {{ margin: 0; font-size: 1.25rem; }}
    .stats {{ color: #94a3b8; font-size: 0.875rem; margin-top: 0.25rem; }}
    .legend {{ display: flex; gap: 1rem; margin-top: 0.5rem; font-size: 0.875rem; }}
    .legend span {{ display: flex; align-items: center; gap: 0.25rem; }}
    .dot {{ width: 0.625rem; height: 0.625rem; border-radius: 50%; display: inline-block; }}
    #graph {{ width: 100%; height: calc(100vh - 120px); display: flex; align-items: center; justify-content: center; overflow: auto; }}
    svg {{ max-width: 100%; max-height: 100%; }}
    .node:hover circle {{ stroke: #f8fafc; stroke-width: 3; }}
  </style>
</head>
<body>
  <header>
    <h1>/journey — radial memory graph</h1>
    <div class="stats">{node_count} nodes · {edge_count} edges · read-only snapshot</div>
    <div class="legend">
      <span><i class="dot" style="background:{self._COLORS['index']}"></i> index</span>
      <span><i class="dot" style="background:{self._COLORS['wiki']}"></i> wiki</span>
      <span><i class="dot" style="background:{self._COLORS['skill']}"></i> skill</span>
    </div>
  </header>
  <div id="graph">
    {svg}
  </div>
</body>
</html>
""".strip()

    def _node_title(self, node: JourneyNode) -> str:
        parts = [f"{node.label} ({node.type})"]
        if node.group and node.group != node.type:
            parts.append(f"group: {node.group}")
        if node.timestamp:
            parts.append(node.timestamp.strftime("%Y-%m-%d"))
        if node.meta.get("description"):
            parts.append(node.meta["description"])
        return self._escape("\n".join(parts))

    def _escape(self, text: str) -> str:
        return (
            text.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;")
        )
