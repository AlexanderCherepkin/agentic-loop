from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


DEFAULT_COSTS: dict[str, dict[str, float]] = {
    "claude-opus-4-8": {"input": 0.015, "output": 0.075},
    "claude-sonnet-5": {"input": 0.003, "output": 0.015},
    "claude-sonnet-4-6": {"input": 0.003, "output": 0.015},
    "claude-haiku-4-5-20251001": {"input": 0.0008, "output": 0.0032},
    "gpt-4o": {"input": 0.005, "output": 0.015},
    "gpt-4o-mini": {"input": 0.00015, "output": 0.0006},
    "gpt-3.5-turbo": {"input": 0.0005, "output": 0.0015},
    "deepseek-chat": {"input": 0.00014, "output": 0.00028},
    "default": {"input": 0.0, "output": 0.0},
}


def _estimate_tokens(text: str) -> int:
    return max(1, len(text) // 4)


@dataclass
class CostTrackingConfig:
    enabled: bool = field(
        default_factory=lambda: os.getenv("COST_TRACKING_ENABLED", "false").lower()
        not in ("false", "0", "off", "no")
    )
    db_path: Path | str = field(
        default_factory=lambda: os.getenv("COST_DB_PATH", "data/cost_tracking.db")
    )
    costs_json: str | None = field(
        default_factory=lambda: os.getenv("COSTS_JSON")
    )
    costs_path: Path | str | None = field(
        default_factory=lambda: os.getenv("COSTS_PATH")
    )
    default_currency: str = "USD"

    def __post_init__(self) -> None:
        self.db_path = Path(self.db_path)
        if self.costs_path:
            self.costs_path = Path(self.costs_path)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "CostTrackingConfig":
        return cls(
            enabled=bool(data.get("enabled", False)),
            db_path=data.get("db_path", "data/cost_tracking.db"),
            costs_json=data.get("costs_json"),
            costs_path=data.get("costs_path"),
            default_currency=data.get("default_currency", "USD"),
        )

    def load_costs(self) -> dict[str, dict[str, float]]:
        costs = dict(DEFAULT_COSTS)
        if self.costs_path and Path(self.costs_path).exists():
            try:
                with Path(self.costs_path).open(encoding="utf-8") as f:
                    costs.update(json.load(f))
            except Exception:
                pass
        if self.costs_json:
            try:
                costs.update(json.loads(self.costs_json))
            except Exception:
                pass
        return costs
