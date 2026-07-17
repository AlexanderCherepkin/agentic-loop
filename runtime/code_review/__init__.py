"""Code review runtime module.

Provides a deterministic CodeReviewer engine and a patch-based diff applier
adapted from the source bot. Used by self-correction agents to validate and
fix generated codebases.
"""

from __future__ import annotations

from .config import CodeReviewConfig
from .diff_engine import Patch, PatchApplier
from .engine import CodeIssue, CodeReviewer, ReviewResult

__all__ = [
    "CodeIssue",
    "CodeReviewConfig",
    "CodeReviewer",
    "Patch",
    "PatchApplier",
    "ReviewResult",
]
