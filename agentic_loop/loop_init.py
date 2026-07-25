"""CLI entry point for python -m agentic_loop.loop_init."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import yaml


CONSTRAINTS_SEED = """# Agentic Loop Constraints

This file accumulates hard-learned constraints from loop execution.
It is loaded at the start of every `/loop`, `/goal`, or `/workflows` run.
Entries added by `loop_verifier.py` are append-only and timestamped.
Manual edits are allowed but should be logged in the entry metadata.

## Seed

- Loop engine start: constraints file initialized.
"""


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="loop-init",
        description="Scaffold a new loop instance from a preset YAML file.",
    )
    parser.add_argument(
        "--preset",
        required=True,
        help="Path to a loop preset YAML file (e.g. runtime/loop_presets/ci_sweeper.yaml).",
    )
    parser.add_argument(
        "--name",
        required=True,
        help="Name for the loop instance; produces <name>.loop.yaml.",
    )
    parser.add_argument(
        "--workspace",
        default=".",
        help="Workspace root where the instance and CONSTRAINTS.md live.",
    )
    return parser


def init_loop(preset_path: Path, name: str, workspace: Path) -> dict:
    """Load preset, write loop instance file, and seed CONSTRAINTS.md if absent."""
    preset_path = preset_path.resolve()
    workspace = workspace.resolve()

    if not preset_path.is_file():
        raise FileNotFoundError(f"Preset not found: {preset_path}")

    with open(preset_path, encoding="utf-8") as f:
        preset = yaml.safe_load(f) or {}

    instance_path = workspace / f"{name}.loop.yaml"
    instance = {
        "name": name,
        "preset": preset.get("name", preset_path.stem),
        "goal": preset.get("goal"),
        "max_iterations": preset.get("max_iterations", 1),
        "trust_level": preset.get("trust_level", "L1"),
        "schedule": preset.get("schedule"),
        "verification_plan": preset.get("verification_plan"),
        "human_zones": preset.get("human_zones", []),
        "exit_conditions": preset.get("exit_conditions", []),
    }

    with open(instance_path, "w", encoding="utf-8") as f:
        yaml.dump(instance, f, allow_unicode=True, sort_keys=False)

    constraints_path = workspace / ".agent_loop" / "CONSTRAINTS.md"
    constraints_updated = False
    if not constraints_path.exists():
        constraints_path.parent.mkdir(parents=True, exist_ok=True)
        constraints_path.write_text(CONSTRAINTS_SEED, encoding="utf-8")
        constraints_updated = True

    return {
        "instance_path": str(instance_path),
        "constraints_updated": constraints_updated,
    }


def main(args: list[str] | None = None) -> int:
    parser = build_parser()
    parsed = parser.parse_args(args)
    result = init_loop(Path(parsed.preset), parsed.name, Path(parsed.workspace))
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
