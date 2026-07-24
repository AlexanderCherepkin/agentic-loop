"""Skill integration runtime module.

Deterministic write gate for approved skill and wiki operations.
This module materializes the decisions produced by the skill planning agents
(skill_request_router, wiki_ingest_planner, wiki_lint_planner) and the
skill_integrator.md execution agent.
"""

from __future__ import annotations

from .config import SkillIntegrationConfig
from .engine import (
    IntegrationResult,
    SkillIntegrationEngine,
    SkillProposal,
    WikiProposal,
)

__all__ = [
    "IntegrationResult",
    "SkillIntegrationConfig",
    "SkillIntegrationEngine",
    "SkillProposal",
    "WikiProposal",
]
