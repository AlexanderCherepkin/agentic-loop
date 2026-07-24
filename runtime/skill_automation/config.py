"""Configuration for the skill automation runtime module."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class SkillAutomationConfig:
    """Configuration for SkillAutomationEngine."""

    workspace_root: str | Path = "."
    graphify_min_changed_files: int = 10
    graphify_new_agent_detected: bool = True
    graphify_large_corpus_warning: int = 500
    source_min_words: int = 200
    source_max_files_per_scan: int = 5
    excluded_patterns: tuple[str, ...] = (
        ".git/",
        "node_modules/",
        ".venv/",
        "__pycache__/",
        "dist/",
        "build/",
        "graphify-out/",
        ".claude/worktrees/",
        "data/",
        ".audit/",
    )
    source_extensions: tuple[str, ...] = (".md",)
    state_file: str = "data/skill_automation.jsonl"

    def to_dict(self) -> dict[str, Any]:
        return {
            "workspace_root": str(self.workspace_root),
            "graphify_min_changed_files": self.graphify_min_changed_files,
            "graphify_new_agent_detected": self.graphify_new_agent_detected,
            "graphify_large_corpus_warning": self.graphify_large_corpus_warning,
            "source_min_words": self.source_min_words,
            "source_max_files_per_scan": self.source_max_files_per_scan,
            "excluded_patterns": list(self.excluded_patterns),
            "source_extensions": list(self.source_extensions),
            "state_file": self.state_file,
        }
