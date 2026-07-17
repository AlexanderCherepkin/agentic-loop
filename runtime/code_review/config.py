"""Configuration for the code review runtime module."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class CodeReviewConfig:
    """Configuration for CodeReviewer and PatchApplier."""

    mode: str = "review"  # "review" | "review_and_fix"
    max_iterations: int = 1
    include_linter: bool = False
    diff_mode: bool = False
    severity_threshold: str = "major"  # critical | major | minor | nit
    allowed_extensions: tuple[str, ...] = (
        ".py",
        ".ts",
        ".tsx",
        ".js",
        ".jsx",
        ".go",
        ".rs",
        ".md",
        ".json",
        ".yml",
        ".yaml",
    )
    excluded_paths: tuple[str, ...] = ("node_modules/", ".venv/", "__pycache__/", ".git/", "dist/", "build/")

    def to_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "max_iterations": self.max_iterations,
            "include_linter": self.include_linter,
            "diff_mode": self.diff_mode,
            "severity_threshold": self.severity_threshold,
            "allowed_extensions": list(self.allowed_extensions),
            "excluded_paths": list(self.excluded_paths),
        }
