"""Skill automation runtime module.

Detects markdown sources suitable for reusable Claude Code skills and
triggers graphify knowledge-graph refreshes after significant workspace
changes.
"""

from __future__ import annotations

from .config import SkillAutomationConfig
from .engine import (
    GraphifyNeed,
    SkillAutomationEngine,
    SkillAutomationResult,
    SourceCandidate,
)

__all__ = [
    "GraphifyNeed",
    "SkillAutomationConfig",
    "SkillAutomationEngine",
    "SkillAutomationResult",
    "SourceCandidate",
]
