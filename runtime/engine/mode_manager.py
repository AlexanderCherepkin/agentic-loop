"""Runtime mode switching and override persistence for the model economy."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .model_economy_config import (
    AUXILIARY_SLOT_KEYS,
    Mode,
    ModelEconomyConfig,
    ModelRef,
    load_model_economy_config,
)


@dataclass
class ModeManager:
    """Holds the active mode, runtime overrides, and last persisted snapshot.

    The manager is intentionally stateful only for runtime overrides. Project and
    user mode definitions are immutable once loaded.
    """

    config: ModelEconomyConfig = field(default_factory=load_model_economy_config)
    _active_mode_name: str = ""
    _overrides: dict[str, ModelRef] = field(default_factory=dict)
    _snapshot: dict[str, ModelRef] = field(default_factory=dict)

    def __post_init__(self):
        if not self._active_mode_name:
            self._active_mode_name = self.config.default_mode

    @property
    def active_mode(self) -> Mode:
        return self.config.get_mode(self._active_mode_name)

    @property
    def active_mode_name(self) -> str:
        return self._active_mode_name

    @property
    def guardrail_template(self) -> str | None:
        """Return the active guardrail template (mode-level overrides config-level)."""
        mode_template = self.active_mode.guardrail_template
        if mode_template is not None:
            return mode_template
        return self.config.guardrail_template

    def set_mode(self, name: str) -> Mode:
        """Switch to the named mode, clearing runtime overrides."""
        mode = self.config.get_mode(name)
        self._active_mode_name = name
        self._overrides.clear()
        return mode

    def override(self, slot: str, provider: str, model: str) -> ModelRef:
        """Apply a runtime override to ``slot`` (``"main"`` or an auxiliary key)."""
        if slot != "main" and slot not in AUXILIARY_SLOT_KEYS:
            raise KeyError(f"Unknown slot: {slot}")
        ref = ModelRef(provider=provider, model=model)
        self._overrides[slot] = ref
        return ref

    def clear_overrides(self) -> None:
        """Clear all runtime overrides and return to the active mode template."""
        self._overrides.clear()

    @property
    def overrides(self) -> dict[str, ModelRef]:
        """Read-only view of current runtime overrides."""
        return dict(self._overrides)

    def current_effective_config(self) -> dict[str, Any]:
        """Return a flat dict of effective model references for all slots."""
        mode = self.active_mode
        result: dict[str, Any] = {"main": self._overrides.get("main", mode.main).to_dict()}
        for slot in AUXILIARY_SLOT_KEYS:
            result[slot] = self._overrides.get(slot, mode.auxiliary.slot(slot)).to_dict()
        return result

    @property
    def snapshot(self) -> dict[str, ModelRef]:
        """Read-only view of the last persisted snapshot."""
        return dict(self._snapshot)

    def persist_snapshot(self, path: str | Path | None = None) -> Path:
        """Persist the current effective config as the drift-detection snapshot.

        Args:
            path: Destination file. Defaults to ``.agent_loop/state/model_economy_snapshot.json``.

        Returns:
            The path written.
        """
        if path is None:
            path = Path.cwd() / ".agent_loop" / "state" / "model_economy_snapshot.json"
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        self._snapshot = self.current_effective_refs()
        with target.open("w", encoding="utf-8") as f:
            json.dump({k: v.to_dict() for k, v in self._snapshot.items()}, f, indent=2)
        return target

    def load_snapshot(self, path: str | Path | None = None) -> dict[str, ModelRef]:
        """Load a persisted snapshot and return its slot mapping."""
        if path is None:
            path = Path.cwd() / ".agent_loop" / "state" / "model_economy_snapshot.json"
        target = Path(path)
        if not target.exists():
            return {}
        with target.open("r", encoding="utf-8") as f:
            data = json.load(f)
        self._snapshot = {
            k: ModelRef(provider=v["provider"], model=v["model"])
            for k, v in data.items()
            if isinstance(v, dict)
        }
        return dict(self._snapshot)

    def current_effective_refs(self) -> dict[str, ModelRef]:
        """Return a flat ``dict[slot, ModelRef]`` for the current effective config."""
        mode = self.active_mode
        refs: dict[str, ModelRef] = {"main": self._overrides.get("main", mode.main)}
        for slot in AUXILIARY_SLOT_KEYS:
            refs[slot] = self._overrides.get(slot, mode.auxiliary.slot(slot))
        return refs
