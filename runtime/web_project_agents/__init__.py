"""Web Project Agents runtime module.

Provides deterministic adapters for the AgentClassifier / AgentArchitect /
AgentDeveloper agents originally from ``F:\Agents-komponents``. They are wired
into the Agentic Loop ReAct cycle as markdown agents and executed through the
existing ``runtime.engine.llm_engine.LLMEngine``.
"""

from __future__ import annotations

from .architect import ProjectArchitect
from .classifier import ProjectClassifier
from .config import WebProjectAgentsConfig
from .developer import ProjectDeveloper

__all__ = [
    "ProjectArchitect",
    "ProjectClassifier",
    "ProjectDeveloper",
    "WebProjectAgentsConfig",
]
