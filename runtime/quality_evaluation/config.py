"""Configuration for the quality evaluation runtime module."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class QualityEvaluationConfig:
    """Configuration for QualityEvaluator."""

    min_score: float = 6.0
    max_refinement_rounds: int = 2
    criteria: tuple[str, ...] = ("relevance", "completeness", "code_quality", "structure")

    def to_dict(self) -> dict[str, Any]:
        return {
            "min_score": self.min_score,
            "max_refinement_rounds": self.max_refinement_rounds,
            "criteria": list(self.criteria),
        }
