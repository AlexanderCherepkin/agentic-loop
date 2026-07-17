"""Configuration dataclasses for the Web Project Agents runtime module."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class ProjectClassifierConfig:
    """Configuration for the project classifier agent."""

    prompt_version: str = "default"
    use_cache: bool = True
    cache_ttl_seconds: int = 86400
    cache_db_path: str = ".agent_loop/data/classifications_cache.db"


@dataclass
class ProjectArchitectConfig:
    """Configuration for the project architect agent."""

    prompt_version: str = "default"
    include_adr: bool = False


@dataclass
class ProjectDeveloperConfig:
    """Configuration for the project developer agent."""

    prompt_version: str = "default"
    default_language: str = "python"


@dataclass
class WebProjectAgentsConfig:
    """Top-level configuration for all Web Project Agents."""

    classifier: ProjectClassifierConfig = field(default_factory=ProjectClassifierConfig)
    architect: ProjectArchitectConfig = field(default_factory=ProjectArchitectConfig)
    developer: ProjectDeveloperConfig = field(default_factory=ProjectDeveloperConfig)
    prompt_manifest_path: Path = field(
        default_factory=lambda: Path(__file__).with_name("prompt_manifest.yaml")
    )
    templates_dir: Path = field(
        default_factory=lambda: Path(__file__).resolve().parent.parent.parent
        / "templates"
        / "web_project_agents"
    )
    generated_projects_dir: Path = field(
        default_factory=lambda: Path("generated_projects")
    )

    def to_dict(self) -> dict[str, Any]:
        return {
            "classifier": self.classifier.__dict__,
            "architect": self.architect.__dict__,
            "developer": self.developer.__dict__,
            "prompt_manifest_path": str(self.prompt_manifest_path),
            "templates_dir": str(self.templates_dir),
            "generated_projects_dir": str(self.generated_projects_dir),
        }
