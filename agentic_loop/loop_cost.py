"""CLI entry point for python -m agentic_loop.loop_cost."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path

import yaml

try:
    from runtime.loop_engine.loop_cost_estimator import LoopCostEstimator
except ImportError:
    LoopCostEstimator = None  # type: ignore[misc, assignment]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="loop-cost",
        description="Estimate cost of a loop preset before running it.",
    )
    parser.add_argument(
        "--preset",
        required=True,
        help="Path to a loop preset YAML file.",
    )
    parser.add_argument(
        "--budget",
        type=float,
        default=None,
        help="Optional USD budget cap; sets budget_ok in the output.",
    )
    parser.add_argument(
        "--workspace",
        default=".",
        help="Workspace root.",
    )
    return parser


def _fallback_estimate(preset: dict) -> dict:
    """Heuristic cost estimate used when LoopCostEstimator is not yet available."""
    max_iterations = int(preset.get("max_iterations", 1))
    verification_plan = preset.get("verification_plan") or {}
    critic_count = int(verification_plan.get("critics", 2))
    estimated_tokens = max_iterations * (2000 + critic_count * 4000)
    estimated_usd = round(estimated_tokens / 1000 * 0.005, 6)
    return {
        "estimated_tokens": estimated_tokens,
        "estimated_usd": estimated_usd,
    }


def estimate_cost(preset_path: Path, budget: float | None, workspace: Path) -> dict:
    """Return estimated_tokens, estimated_usd, and budget_ok for a preset."""
    preset_path = preset_path.resolve()
    workspace = workspace.resolve()

    if not preset_path.is_file():
        raise FileNotFoundError(f"Preset not found: {preset_path}")

    with open(preset_path, encoding="utf-8") as f:
        preset = yaml.safe_load(f) or {}

    if LoopCostEstimator is not None:
        estimator = LoopCostEstimator(workspace=workspace)
        estimate = estimator.estimate(preset)
        if hasattr(estimate, "__dataclass_fields__"):
            result = asdict(estimate)
            if "estimated_tokens" not in result and "estimated_total_tokens" in result:
                result["estimated_tokens"] = result["estimated_total_tokens"]
        else:
            result = estimate
    else:
        result = _fallback_estimate(preset)

    budget_ok = bool(result.get("budget_ok", True))
    if budget is not None:
        budget_ok = result["estimated_usd"] <= budget
    result["budget_ok"] = budget_ok

    return result


def main(args: list[str] | None = None) -> int:
    parser = build_parser()
    parsed = parser.parse_args(args)
    result = estimate_cost(
        Path(parsed.preset),
        parsed.budget,
        Path(parsed.workspace),
    )
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result["budget_ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
