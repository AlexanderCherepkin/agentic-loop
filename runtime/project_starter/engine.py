"""ProjectStarterEngine — materialises a starter package from a brief."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .config import ProjectStarterConfig
from .template_manager import TemplateManager


@dataclass
class ProjectStarterResult:
    """Result of generating a starter package."""

    template_id: str = ""
    template_name: str = ""
    stack: dict[str, str] = field(default_factory=dict)
    language: str = "python"
    files: list[dict[str, str]] = field(default_factory=list)
    commands: list[str] = field(default_factory=list)
    readme: str = ""
    env_example: str = ""
    next_steps: list[str] = field(default_factory=list)
    confidence: float = 0.0
    missing_inputs: list[str] = field(default_factory=list)
    next_phase_hint: str = "execution"

    def to_dict(self) -> dict[str, Any]:
        return {
            "template_id": self.template_id,
            "template_name": self.template_name,
            "stack": self.stack,
            "language": self.language,
            "files": self.files,
            "commands": self.commands,
            "readme": self.readme,
            "env_example": self.env_example,
            "next_steps": self.next_steps,
            "confidence": self.confidence,
            "missing_inputs": self.missing_inputs,
            "next_phase_hint": self.next_phase_hint,
        }


class ProjectStarterEngine:
    """Selects a starter preset and prepares a starter package."""

    def __init__(self, config: ProjectStarterConfig | None = None) -> None:
        self.config = config or ProjectStarterConfig()
        self.manager = TemplateManager(self.config)

    def build_package(
        self,
        brief: str,
        classification: dict[str, Any] | None = None,
        language: str | None = None,
        preferred_preset_id: str | None = None,
    ) -> ProjectStarterResult:
        """Build a starter package for a brief/classification."""
        result = ProjectStarterResult()

        # Determine language.
        detected_language = language or self.manager.detect_language(brief)
        result.language = detected_language or self.config.default_language

        # Determine preset.
        preset_id = preferred_preset_id
        if preset_id is None and classification is not None:
            preset_id = self.manager.find_match(classification, result.language)
        preset = self.manager.get_preset(preset_id)
        if preset is None:
            result.missing_inputs.append("No matching starter preset found for the classification")
            result.confidence = 0.5
            return result

        result.template_id = preset.id
        result.template_name = preset.name
        result.stack = dict(preset.stack)
        result.stack.setdefault("language", result.language)

        # Build file list.
        result.files = [{"path": k, "content": v} for k, v in preset.files.items()]

        # Derive commands from stack hints.
        result.commands = self._derive_commands(preset)

        # Build README and env example from preset variables.
        result.readme = self._build_readme(preset)
        result.env_example = self._build_env_example(preset)
        result.next_steps = [
            f"Install dependencies: {result.commands[0]}" if result.commands else "Install dependencies",
            "Review and customize README.md",
            "Fill in .env.example values",
        ]
        result.confidence = 0.9
        result.next_phase_hint = "execution"
        return result

    def _derive_commands(self, preset: Any) -> list[str]:
        stack = preset.stack or {}
        language = (preset.language or "python").lower()
        framework = (stack.get("framework") or "").lower()

        if language == "python":
            if "django" in framework:
                return ["pip install -r requirements.txt", "python manage.py migrate", "python manage.py runserver"]
            if "flask" in framework:
                return ["pip install -r requirements.txt", "flask run"]
            return ["pip install -r requirements.txt", "uvicorn main:app --reload"]
        if language == "typescript":
            return ["npm install", "npm run dev"]
        if language == "go":
            return ["go mod tidy", "go run main.go"]
        if language == "rust":
            return ["cargo build", "cargo run"]
        return ["install dependencies", "run application"]

    def _build_readme(self, preset: Any) -> str:
        lines = [
            f"# {preset.name}",
            "",
            preset.description,
            "",
            "## Stack",
            *[f"- {k}: {v}" for k, v in (preset.stack or {}).items()],
            "",
            "## Getting started",
            "See `.env.example` for required environment variables.",
        ]
        return "\n".join(lines)

    def _build_env_example(self, preset: Any) -> str:
        variables = preset.variables or {}
        lines = ["# Environment variables"]
        for key, value in variables.items():
            lines.append(f"{key}={value}")
        return "\n".join(lines) if variables else "# Add environment variables here\n"
