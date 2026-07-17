"""Configuration dataclasses for the project starter template manager."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class TemplatePreset:
    """Model of a project starter preset."""

    id: str
    name: str
    description: str = ""
    tags: list[str] = field(default_factory=list)
    stack: dict[str, str] = field(default_factory=dict)
    base_category: str | None = None
    variables: dict[str, Any] = field(default_factory=dict)
    files: dict[str, str] = field(default_factory=dict)
    language: str = "python"

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "tags": self.tags,
            "stack": self.stack,
            "base_category": self.base_category,
            "variables": self.variables,
            "files": self.files,
            "language": self.language,
        }


@dataclass
class ProjectStarterConfig:
    """Top-level configuration for the project starter engine."""

    templates_dir: Path = field(
        default_factory=lambda: Path(__file__).resolve().parent.parent.parent
        / "templates"
        / "web_project_agents"
    )
    language_auto_detect_enabled: bool = True
    default_language: str = "python"
    available_languages: tuple[str, ...] = ("python", "typescript", "go", "rust")

    def to_dict(self) -> dict[str, Any]:
        return {
            "templates_dir": str(self.templates_dir),
            "language_auto_detect_enabled": self.language_auto_detect_enabled,
            "default_language": self.default_language,
            "available_languages": list(self.available_languages),
        }
