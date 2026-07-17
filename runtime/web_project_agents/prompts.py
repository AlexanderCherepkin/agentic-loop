"""Load and expose the Web Project Agents prompt manifest."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)


class PromptManifest:
    """Lightweight loader for the YAML prompt manifest shared by classifier,
    architect and developer agents.
    """

    def __init__(self, path: Path | str | None = None) -> None:
        self.path = Path(path) if path else Path(__file__).with_name("prompt_manifest.yaml")
        self._data: dict[str, Any] | None = None

    def _load(self) -> dict[str, Any]:
        if self._data is None:
            if not self.path.exists():
                logger.warning("Prompt manifest not found: %s", self.path)
                return {}
            with self.path.open("r", encoding="utf-8") as fh:
                self._data = yaml.safe_load(fh) or {}
        return self._data or {}

    def get_system_prompt(self, role: str, version: str = "default") -> str | None:
        """Return the system_prompt text for a given role and version.

        Args:
            role: one of ``classifier``, ``architect``, ``developer``.
            version: key under ``prompt_versions`` (default: ``default``).
        """
        data = self._load()
        versions = data.get("prompt_versions", {})
        version_data = versions.get(version, {})
        role_data = version_data.get(role, {})
        prompt = role_data.get("system_prompt")
        if isinstance(prompt, str):
            return prompt.strip()
        return None

    def get_model_settings(self, role: str, version: str = "default") -> dict[str, Any]:
        """Return optional model settings for a role/version."""
        data = self._load()
        versions = data.get("prompt_versions", {})
        version_data = versions.get(version, {})
        role_data = version_data.get(role, {})
        return role_data.get("model_settings", {})
