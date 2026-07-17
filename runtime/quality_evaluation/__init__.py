"""Quality evaluation runtime module.

Scores generated manifests and codebases against a checklist and can trigger
regeneration when the score is too low.
"""

from __future__ import annotations

from .config import QualityEvaluationConfig
from .engine import QualityEvaluationResult, QualityEvaluator

__all__ = [
    "QualityEvaluationConfig",
    "QualityEvaluationResult",
    "QualityEvaluator",
]
