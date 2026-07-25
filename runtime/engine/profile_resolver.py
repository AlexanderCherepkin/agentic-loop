"""Profile resolver: per-profile model + system prompt stored in ~/.hermes/profiles.

A profile is a directory under ``~/.hermes/profiles/<id>/`` containing:
  - ``config.yaml`` with optional ``model``, ``provider``, ``mode``, ``guardrail_template``.
  - ``SOUL.md`` with a persona/system prompt.

ProfileResolver acts as a decorator over ``ModeManager`` and does not mutate it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .mode_manager import ModeManager
from .model_economy_config import ModelRef


@dataclass(frozen=True)
class ResolvedProfile:
    """Effective model and prompts for a profile."""

    profile_id: str
    model_ref: ModelRef
    guardrail_template: str | None = None
    soul_prompt: str | None = None
    mode_name: str | None = None

    def full_system_prefix(self, base_system: str = "") -> str:
        """Compose the final system prompt prefix from guardrail + SOUL + base."""
        parts: list[str] = []
        if self.guardrail_template:
            parts.append(self.guardrail_template.strip())
        if self.soul_prompt:
            parts.append(self.soul_prompt.strip())
        if base_system:
            parts.append(base_system.strip())
        return "\n\n".join(parts)


class ProfileResolver:
    """Resolve a profile from disk and compose its effective configuration."""

    _SOUL_RE = re.compile(r"^---\s*\n.*?\n---\s*\n", re.DOTALL)

    def __init__(self, profiles_root: str | Path | None = None):
        self._profiles_root = Path(profiles_root) if profiles_root else Path.home() / ".hermes" / "profiles"

    def _profile_dir(self, profile_id: str) -> Path:
        return self._profiles_root / profile_id

    def _load_yaml(self, path: Path) -> dict[str, Any]:
        import yaml  # type: ignore

        if not path.exists():
            return {}
        with path.open("r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        return data if isinstance(data, dict) else {}

    def _read_soul(self, path: Path) -> str | None:
        if not path.exists():
            return None
        text = path.read_text(encoding="utf-8")
        text = self._SOUL_RE.sub("", text, count=1)
        text = text.strip()
        return text if text else None

    def resolve(
        self,
        profile_id: str,
        mode_manager: ModeManager | None = None,
    ) -> ResolvedProfile:
        """Resolve ``profile_id`` against disk and optional active mode.

        Raises:
            KeyError: if the profile directory does not exist.
        """
        profile_dir = self._profile_dir(profile_id)
        if not profile_dir.exists():
            raise KeyError(f"Profile not found: {profile_id} at {profile_dir}")

        config = self._load_yaml(profile_dir / "config.yaml")
        soul = self._read_soul(profile_dir / "SOUL.md")

        provider = str(config.get("provider", "anthropic"))
        model = str(config.get("model", "claude-sonnet-5"))

        if mode_manager is not None:
            active = mode_manager.active_mode
            # If profile does not specify model/provider, fall back to active mode main.
            if "provider" not in config:
                provider = active.main.provider
            if "model" not in config:
                model = active.main.model

        return ResolvedProfile(
            profile_id=profile_id,
            model_ref=ModelRef(provider=provider, model=model),
            guardrail_template=config.get("guardrail_template"),
            soul_prompt=soul,
            mode_name=config.get("mode"),
        )

    def list_profiles(self) -> list[str]:
        """Return IDs of existing profiles."""
        if not self._profiles_root.exists():
            return []
        return [p.name for p in self._profiles_root.iterdir() if p.is_dir()]
