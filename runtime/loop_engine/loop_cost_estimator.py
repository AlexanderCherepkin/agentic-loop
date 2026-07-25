"""Estimate cost of a loop before it starts, with hard budget stop."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from ..cost_tracking.engine import CostTrackingEngine


@dataclass
class LoopCostEstimate:
    preset_id: str
    estimated_input_tokens: int
    estimated_output_tokens: int
    estimated_total_tokens: int
    estimated_usd: float
    budget_limit: float | None
    spent: float
    remaining: float | None
    budget_ok: bool


class LoopCostEstimator:
    """Estimate loop cost from a preset YAML or dict and enforce budget guard."""

    # Heuristic token estimates per step class.
    DEFAULT_INPUT_TOKENS_PER_STEP: int = 4000
    DEFAULT_OUTPUT_TOKENS_PER_STEP: int = 1500

    def __init__(
        self,
        cost_engine: CostTrackingEngine | None = None,
        workspace: Path | str | None = None,
    ):
        self.cost_engine = cost_engine or CostTrackingEngine()
        self.workspace = Path(workspace) if workspace else Path.cwd()

    def estimate(
        self,
        preset: dict[str, Any] | Path | str,
        scope: str = "loop_default",
        extra_iterations: int = 0,
    ) -> LoopCostEstimate:
        """Return a cost estimate for the given preset and current budget state."""
        if isinstance(preset, (Path, str)):
            preset_path = Path(preset)
            data = self._load_preset(preset_path)
            preset_id = data.get("id", preset_path.stem)
        else:
            data = preset
            preset_id = data.get("id", "unknown")

        steps = data.get("steps", [])
        iterations = int(data.get("max_iterations", 1)) + extra_iterations

        executor_model = data.get("executor_model", "claude-haiku-4-5")
        verifier_model = data.get("verifier_model", "claude-opus-4-8")
        min_critics = int(data.get("min_critics", 2))

        executor_input = self.DEFAULT_INPUT_TOKENS_PER_STEP * len(steps)
        executor_output = self.DEFAULT_OUTPUT_TOKENS_PER_STEP * len(steps)
        verifier_input = 2000 + executor_output
        verifier_output = 800

        per_iteration_input = executor_input + verifier_input * min_critics
        per_iteration_output = executor_output + verifier_output * min_critics

        total_input = per_iteration_input * iterations
        total_output = per_iteration_output * iterations
        total_tokens = total_input + total_output

        verify_input = verifier_input * min_critics * iterations
        verify_output = verifier_output * min_critics * iterations
        exec_input = total_input - verify_input
        exec_output = total_output - verify_output
        exec_cost = self._cost_for(executor_model, exec_input, exec_output)
        verify_cost = self._cost_for(verifier_model, verify_input, verify_output)
        estimated_usd = exec_cost + verify_cost

        budget_state = self.cost_engine.check_budget(scope, extra_cost=estimated_usd)
        budget_ok = bool(budget_state.get("allowed", True))
        limit = budget_state.get("limit")
        spent = float(budget_state.get("spent", 0.0))
        remaining = budget_state.get("remaining")

        return {
            "preset_id": preset_id,
            "estimated_input_tokens": total_input,
            "estimated_output_tokens": total_output,
            "estimated_total_tokens": total_tokens,
            "estimated_tokens": total_tokens,
            "estimated_usd": round(estimated_usd, 6),
            "budget_limit": limit,
            "spent": spent,
            "remaining": round(remaining, 6) if remaining is not None else None,
            "budget_ok": budget_ok,
        }

    def check_before_call(self, scope: str, extra_cost: float) -> dict[str, Any]:
        """Hard stop guard: returns allowed=False if budget would be exceeded."""
        state = self.cost_engine.check_budget(scope, extra_cost=extra_cost)
        return {
            "scope": scope,
            "allowed": bool(state.get("allowed", True)),
            "spent": float(state.get("spent", 0.0)),
            "limit": state.get("limit"),
            "remaining": state.get("remaining"),
        }

    def _load_preset(self, path: Path) -> dict[str, Any]:
        text = path.read_text(encoding="utf-8")
        data: dict[str, Any] = yaml.safe_load(text)
        if not isinstance(data, dict):
            raise ValueError(f"Preset {path} is not a YAML mapping")
        return data

    def _cost_for(self, model: str, input_tokens: int, output_tokens: int) -> float:
        rates = self.cost_engine.get_model_cost(model)
        input_cost = rates.get("input", 0.0) * input_tokens / 1000.0
        output_cost = rates.get("output", 0.0) * output_tokens / 1000.0
        return input_cost + output_cost
