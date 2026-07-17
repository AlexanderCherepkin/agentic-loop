"""Template manager for multi-language project presets."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import yaml

from .config import ProjectStarterConfig, TemplatePreset

logger = logging.getLogger(__name__)


class TemplateManager:
    """Discovers, loads and applies project starter presets."""

    LANGUAGE_KEYWORDS: dict[str, list[str]] = {
        "python": ["python", "fastapi", "django", "flask", "sqlalchemy", "pydantic"],
        "typescript": ["typescript", "javascript", "node", "nextjs", "react", "express", "nest", "prisma"],
        "go": ["go", "golang", "gin", "fiber", "echo", "chi"],
        "rust": ["rust", "actix", "axum", "rocket", "tokio"],
    }

    def __init__(self, config: ProjectStarterConfig | None = None) -> None:
        self.config = config or ProjectStarterConfig()
        self.templates_dir = Path(self.config.templates_dir)
        self.presets: dict[str, TemplatePreset] = {}
        self.discover()

    def discover(self) -> list[str]:
        """Scan ``templates_dir`` and load all valid presets."""
        self.presets.clear()
        if not self.templates_dir.exists():
            logger.info("Templates directory not found: %s", self.templates_dir)
            return []

        loaded: list[str] = []
        for path in sorted(self.templates_dir.iterdir()):
            if not path.is_dir():
                continue
            preset_file = path / "preset.yaml"
            if not preset_file.exists():
                continue
            try:
                preset = self._load_preset(path)
                self.presets[preset.id] = preset
                loaded.append(preset.id)
            except Exception:
                logger.exception("Failed to load preset %s", path)
        logger.info("Loaded presets: %d", len(loaded))
        return loaded

    def _load_preset(self, preset_dir: Path) -> TemplatePreset:
        """Read preset.yaml and files from ``files/``."""
        preset_file = preset_dir / "preset.yaml"
        raw = yaml.safe_load(preset_file.read_text(encoding="utf-8")) or {}

        preset_id = raw.get("id") or preset_dir.name
        files_dir = preset_dir / "files"
        files: dict[str, str] = {}
        if files_dir.exists():
            for file_path in files_dir.rglob("*"):
                if not file_path.is_file():
                    continue
                relative = file_path.relative_to(files_dir).as_posix()
                try:
                    files[relative] = file_path.read_text(encoding="utf-8")
                except UnicodeDecodeError:
                    logger.warning("Skipping binary template file: %s", relative)

        return TemplatePreset(
            id=preset_id,
            name=raw.get("name") or preset_id,
            description=raw.get("description", ""),
            tags=raw.get("tags") or [],
            stack=raw.get("stack") or {},
            base_category=raw.get("base_category"),
            variables=raw.get("variables") or {},
            files=files,
            language=raw.get("language", "python").lower(),
        )

    def list_presets(self) -> list[dict[str, Any]]:
        """Return a summary of all presets."""
        return [
            {
                "id": p.id,
                "name": p.name,
                "description": p.description,
                "tags": p.tags,
                "stack": p.stack,
                "base_category": p.base_category,
                "language": p.language,
                "files_count": len(p.files),
                "files": sorted(p.files.keys()),
            }
            for p in self.presets.values()
        ]

    def get_preset(self, preset_id: str | None) -> TemplatePreset | None:
        """Return a preset by id."""
        if preset_id is None:
            return None
        return self.presets.get(preset_id)

    def get_preset_files(self, preset_id: str | None) -> dict[str, str]:
        """Return files for a preset."""
        preset = self.get_preset(preset_id)
        return preset.files if preset else {}

    def build_context(self, preset_id: str | None) -> dict[str, Any] | None:
        """Build a JSON-serializable context for agent prompts."""
        preset = self.get_preset(preset_id)
        if preset is None:
            return None
        return preset.to_dict()

    def apply(self, preset_id: str | None, generated_codebase: dict[str, str]) -> dict[str, str]:
        """Merge a generated codebase with a preset skeleton.

        Generated files take priority; skeleton files remain if the LLM did
        not return them.
        """
        if preset_id is None:
            return generated_codebase
        preset = self.get_preset(preset_id)
        if preset is None:
            return generated_codebase

        merged = dict(preset.files)
        merged.update(generated_codebase)
        logger.info(
            "Applied preset %s: %d skeleton + %d generated = %d total",
            preset.id,
            len(preset.files),
            len(generated_codebase),
            len(merged),
        )
        return merged

    def detect_language(self, text: str) -> str | None:
        """Detect programming language from brief keywords."""
        if not self.config.language_auto_detect_enabled:
            return None
        text_lower = text.lower()
        scores: dict[str, int] = {}
        for language, keywords in self.LANGUAGE_KEYWORDS.items():
            scores[language] = sum(1 for keyword in keywords if keyword in text_lower)
        if not scores or max(scores.values()) == 0:
            return None
        return max(scores, key=scores.get)

    def find_match(
        self,
        classification: dict[str, Any],
        language: str | None = None,
    ) -> str | None:
        """Pick the best preset for a classification and language."""
        project_type = classification.get("project_type") or {}
        base_category = project_type.get("base_category")
        if not base_category:
            return None
        language = (language or self.config.default_language).lower()
        candidates = [
            p for p in self.presets.values()
            if p.base_category and p.base_category.lower() == base_category.lower()
        ]
        if not candidates:
            return None
        for preset in candidates:
            if preset.language == language:
                return preset.id
        return candidates[0].id

    def format_prompt_context(self, preset_id: str | None) -> str:
        """Format a preset context for insertion into an agent prompt."""
        return self.format_prompt_context_static(self.build_context(preset_id))

    @staticmethod
    def format_prompt_context_static(context: dict[str, Any] | None) -> str:
        """Format a JSON context for an agent prompt."""
        if not context:
            return ""
        return (
            "\n\n=== PROJECT STARTER TEMPLATE ===\n"
            f"{json.dumps(context, ensure_ascii=False, indent=2)}\n"
            "=== END TEMPLATE ==="
        )
