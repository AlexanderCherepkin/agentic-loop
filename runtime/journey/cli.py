"""CLI entry point for /journey."""

from __future__ import annotations

import argparse
import webbrowser
from pathlib import Path

from runtime.safety.file_system_guard import safe_write_file

from .config import JourneyConfig
from .parser import JourneyParser
from .renderer import JourneyRenderer


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="/journey", description="Generate a read-only radial memory graph.")
    parser.add_argument("--workspace", default=".", help="Workspace root containing memory/wiki and .claude/skills.")
    parser.add_argument("--output", default=None, help="Override output HTML path.")
    parser.add_argument("--open", action="store_true", dest="open_browser", help="Open the generated HTML in the default browser.")
    parser.add_argument("--no-open", action="store_false", dest="open_browser", help="Do not open the browser after generation.")
    parser.add_argument("--width", type=int, default=960, help="SVG width.")
    parser.add_argument("--height", type=int, default=960, help="SVG height.")
    parser.set_defaults(open_browser=False)
    return parser


def main(args: list[str] | None = None) -> int:
    parser = build_parser()
    parsed = parser.parse_args(args)

    config = JourneyConfig(
        workspace_root=parsed.workspace,
        output_dir="journey-out",
        output_file="index.html",
        width=parsed.width,
        height=parsed.height,
    )
    if parsed.output:
        out_path = Path(parsed.output)
        config.output_dir = str(out_path.parent)
        config.output_file = out_path.name

    graph = JourneyParser(config).parse()
    result = JourneyRenderer(config).render(graph)

    output_path = safe_write_file(
        Path(config.workspace_root).resolve(),
        Path(config.output_dir) / config.output_file,
        result.html,
    )

    print(f"/journey generated {result.node_count} nodes and {result.edge_count} edges at {output_path}")
    if parsed.open_browser:
        webbrowser.open(f"file://{output_path.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
