"""Model economy configuration: named modes, auxiliary slot map, and smart routers.

Project defaults live in ``runtime/config/model_economy.yaml`` (git-tracked).
User-specific overrides may be placed in ``~/.hermes/config.yaml`` under the same
keys or under a top-level ``model_economy`` section.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

AUXILIARY_SLOT_KEYS = [
    "title",
    "vision",
    "compression",
    "approval",
    "web_extract",
    "code_review",
    "summary",
]


def _load_yaml(path: Path) -> dict[str, Any]:
    """Load a YAML file or return an empty dict if it is missing."""
    import yaml  # type: ignore

    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    return data if isinstance(data, dict) else {}


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """Merge ``override`` into ``base`` recursively for dict values."""
    result = dict(base)
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


@dataclass(frozen=True)
class ModelRef:
    """A single provider/model pair."""

    provider: str
    model: str

    def to_dict(self) -> dict[str, Any]:
        return {"provider": self.provider, "model": self.model}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ModelRef:
        return cls(provider=str(data.get("provider", "anthropic")), model=str(data.get("model", "")))


@dataclass(frozen=True)
class AuxiliarySlots:
    """Cheap auxiliary slot map for routine sub-tasks."""

    title: ModelRef = field(default_factory=lambda: ModelRef("google", "gemini-flash-latest"))
    vision: ModelRef = field(default_factory=lambda: ModelRef("google", "gemini-2.5-flash"))
    compression: ModelRef = field(default_factory=lambda: ModelRef("google", "gemini-flash-latest"))
    approval: ModelRef = field(default_factory=lambda: ModelRef("openai", "gpt-4o-mini"))
    web_extract: ModelRef = field(default_factory=lambda: ModelRef("google", "gemini-flash-latest"))
    code_review: ModelRef = field(default_factory=lambda: ModelRef("openai", "gpt-4o-mini"))
    summary: ModelRef = field(default_factory=lambda: ModelRef("google", "gemini-flash-latest"))

    def slot(self, name: str) -> ModelRef:
        """Return the configured model for ``name`` or raise ``KeyError``."""
        if name not in AUXILIARY_SLOT_KEYS:
            raise KeyError(f"Unknown auxiliary slot: {name}")
        return getattr(self, name)

    def to_dict(self) -> dict[str, Any]:
        return {slot: getattr(self, slot).to_dict() for slot in AUXILIARY_SLOT_KEYS}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AuxiliarySlots:
        kwargs: dict[str, ModelRef] = {}
        for slot in AUXILIARY_SLOT_KEYS:
            slot_data = data.get(slot)
            if isinstance(slot_data, dict):
                kwargs[slot] = ModelRef.from_dict(slot_data)
        return cls(**kwargs)


@dataclass(frozen=True)
class Mode:
    """A named mode describing the main model and every auxiliary slot."""

    name: str
    description: str
    main: ModelRef
    auxiliary: AuxiliarySlots
    guardrail_template: str | None = None

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "description": self.description,
            "main": self.main.to_dict(),
            "auxiliary": self.auxiliary.to_dict(),
        }
        if self.guardrail_template is not None:
            result["guardrail_template"] = self.guardrail_template
        return result

    @classmethod
    def from_dict(cls, name: str, data: dict[str, Any]) -> Mode:
        main_data = data.get("main", {})
        if not isinstance(main_data, dict):
            main_data = {}
        return cls(
            name=name,
            description=str(data.get("description", "")),
            main=ModelRef.from_dict(main_data),
            auxiliary=AuxiliarySlots.from_dict(data.get("auxiliary", {})),
            guardrail_template=data.get("guardrail_template"),
        )

    def model_for(self, slot: str | None) -> ModelRef:
        """Return the model for ``slot`` (``None`` or ``"main"`` returns the main model)."""
        if slot is None or slot == "main":
            return self.main
        return self.auxiliary.slot(slot)


@dataclass(frozen=True)
class SmartRouter:
    """OpenRouter-style smart router configuration."""

    name: str
    provider: str
    model: str
    min_coding_score: float = 0.0
    min_context_tokens: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "model": self.model,
            "min_coding_score": self.min_coding_score,
            "min_context_tokens": self.min_context_tokens,
        }

    @classmethod
    def from_dict(cls, name: str, data: dict[str, Any]) -> SmartRouter:
        return cls(
            name=name,
            provider=str(data.get("provider", "openrouter")),
            model=str(data.get("model", "")),
            min_coding_score=float(data.get("min_coding_score", 0.0)),
            min_context_tokens=int(data.get("min_context_tokens", 0)),
        )


@dataclass
class ModelEconomyConfig:
    """Full model economy configuration including modes and smart routers."""

    modes: dict[str, Mode]
    default_mode: str
    guardrail_template: str | None = None
    smart_routers: dict[str, SmartRouter] = field(default_factory=dict)

    def get_mode(self, name: str) -> Mode:
        if name not in self.modes:
            raise KeyError(f"Unknown mode: {name}")
        return self.modes[name]

    def to_dict(self) -> dict[str, Any]:
        return {
            "guardrail_template": self.guardrail_template,
            "default_mode": self.default_mode,
            "modes": {name: mode.to_dict() for name, mode in self.modes.items()},
            "smart_routers": {name: router.to_dict() for name, router in self.smart_routers.items()},
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ModelEconomyConfig:
        modes_data = data.get("modes", {})
        if not isinstance(modes_data, dict):
            modes_data = {}
        modes = {name: Mode.from_dict(name, mode_data) for name, mode_data in modes_data.items()}
        default_mode = str(data.get("default_mode", next(iter(modes), "default")))
        smart_routers_data = data.get("smart_routers", {})
        if not isinstance(smart_routers_data, dict):
            smart_routers_data = {}
        smart_routers = {
            name: SmartRouter.from_dict(name, router_data)
            for name, router_data in smart_routers_data.items()
        }
        return cls(
            modes=modes,
            default_mode=default_mode,
            guardrail_template=data.get("guardrail_template"),
            smart_routers=smart_routers,
        )

    def merge(self, overrides: dict[str, Any]) -> ModelEconomyConfig:
        """Return a new config with ``overrides`` deep-merged on top."""
        merged_data = _deep_merge(self.to_dict(), overrides)
        return ModelEconomyConfig.from_dict(merged_data)


def _project_config_path() -> Path:
    """Return the path to the project default model economy config."""
    return Path(__file__).resolve().parent.parent.parent / "runtime" / "config" / "model_economy.yaml"


def _user_config_path() -> Path:
    """Return the path to the user-specific Hermes config file."""
    return Path.home() / ".hermes" / "config.yaml"


def load_model_economy_config(
    project_path: str | Path | None = None,
    user_path: str | Path | None = None,
) -> ModelEconomyConfig:
    """Load project defaults and merge user-specific overrides if present.

    Args:
        project_path: Override path to the project ``model_economy.yaml``.
        user_path: Override path to the user ``config.yaml``.

    Returns:
        A fully merged ``ModelEconomyConfig``.
    """
    project_file = Path(project_path) if project_path else _project_config_path()
    project_data = _load_yaml(project_file)

    user_file = Path(user_path) if user_path else _user_config_path()
    user_data = _load_yaml(user_file)
    # Support both root-level keys and a nested ``model_economy`` section.
    if "model_economy" in user_data:
        user_data = user_data["model_economy"]

    if not user_data:
        return ModelEconomyConfig.from_dict(project_data)

    merged = _deep_merge(project_data, user_data)
    return ModelEconomyConfig.from_dict(merged)


def provider_api_key_env(provider: str) -> str | None:
    """Return the conventional environment variable name for a provider API key."""
    mapping = {
        "anthropic": "ANTHROPIC_API_KEY",
        "openai": "OPENAI_API_KEY",
        "deepseek": "DEEPSEEK_API_KEY",
        "openrouter": "OPENROUTER_API_KEY",
        "google": "GOOGLE_API_KEY",
    }
    return os.getenv(mapping.get(provider.lower(), ""), None)
