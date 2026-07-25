"""CLI entry point for python -m agentic_loop.loop_audit."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


REQUIRED_DIRS = ["runtime/loop_engine", "runtime/loop_presets"]
REQUIRED_FILES = [".agent_loop/CONSTRAINTS.md"]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="loop-audit",
        description="Assess project readiness for self-improving loops.",
    )
    parser.add_argument(
        "--workspace",
        default=".",
        help="Workspace root containing runtime/loop_engine and runtime/loop_presets.",
    )
    return parser


def audit(workspace: Path) -> dict:
    """Return readiness score, blockers, and recommendations for loop usage."""
    workspace = workspace.resolve()
    blockers: list[str] = []
    recommendations: list[str] = []
    score = 100

    for rel_dir in REQUIRED_DIRS:
        path = workspace / rel_dir
        if not path.is_dir():
            blockers.append(f"Missing directory: {rel_dir}")
            score -= 25
            recommendations.append(f"Create {rel_dir}/")

    for rel_file in REQUIRED_FILES:
        path = workspace / rel_file
        if not path.is_file():
            blockers.append(f"Missing file: {rel_file}")
            score -= 15
            recommendations.append(
                f"Seed {rel_file} with `python -m agentic_loop.loop_init --preset <path> --name <name>`"
            )

    presets_dir = workspace / "runtime/loop_presets"
    if presets_dir.is_dir():
        presets = list(presets_dir.glob("*.yaml"))
        if len(presets) < 4:
            recommendations.append(
                f"Only {len(presets)} loop presets found; add more presets to runtime/loop_presets/"
            )
    else:
        recommendations.append(
            "Create runtime/loop_presets/ with at least 4 preset YAML files"
        )

    return {
        "readiness_score": max(0, score),
        "blockers": blockers,
        "recommendations": recommendations,
    }


def main(args: list[str] | None = None) -> int:
    parser = build_parser()
    parsed = parser.parse_args(args)
    result = audit(Path(parsed.workspace))
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result["readiness_score"] >= 70 else 1


if __name__ == "__main__":
    raise SystemExit(main())
