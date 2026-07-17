"""Project starter template manager and engine.

Loads multi-language project presets from ``templates/web_project_agents/`` and
merges them with LLM-generated codebases. Used by ``project_starter_agent.md``
and ``project_developer.md``.
"""

from __future__ import annotations

from .config import ProjectStarterConfig, TemplatePreset
from .engine import ProjectStarterEngine
from .template_manager import TemplateManager

__all__ = [
    "ProjectStarterConfig",
    "ProjectStarterEngine",
    "TemplateManager",
    "TemplatePreset",
]
