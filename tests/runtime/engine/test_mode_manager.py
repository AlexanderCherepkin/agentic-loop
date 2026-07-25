"""Tests for ModeManager runtime state."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))

from runtime.engine.mode_manager import ModeManager
from runtime.engine.model_economy_config import ModelEconomyConfig

pytestmark = [pytest.mark.core, pytest.mark.runtime]


@pytest.fixture
def config():
    return ModelEconomyConfig.from_dict(
        {
            "default_mode": "default",
            "guardrail_template": "Base guardrail",
            "modes": {
                "default": {
                    "description": "base",
                    "main": {"provider": "anthropic", "model": "claude-sonnet-5"},
                    "auxiliary": {
                        "title": {"provider": "google", "model": "gemini-flash-latest"},
                        "vision": {"provider": "google", "model": "gemini-2.5-flash"},
                        "compression": {"provider": "google", "model": "gemini-flash-latest"},
                        "approval": {"provider": "openai", "model": "gpt-4o-mini"},
                        "web_extract": {"provider": "google", "model": "gemini-flash-latest"},
                        "code_review": {"provider": "openai", "model": "gpt-4o-mini"},
                        "summary": {"provider": "google", "model": "gemini-flash-latest"},
                    },
                },
                "cheap": {
                    "description": "cheap",
                    "main": {"provider": "google", "model": "gemini-flash-latest"},
                    "auxiliary": {
                        "title": {"provider": "google", "model": "gemini-flash-latest"},
                        "vision": {"provider": "google", "model": "gemini-2.5-flash"},
                        "compression": {"provider": "google", "model": "gemini-flash-latest"},
                        "approval": {"provider": "openai", "model": "gpt-4o-mini"},
                        "web_extract": {"provider": "google", "model": "gemini-flash-latest"},
                        "code_review": {"provider": "openai", "model": "gpt-4o-mini"},
                        "summary": {"provider": "google", "model": "gemini-flash-latest"},
                    },
                    "guardrail_template": "Cheap guardrail",
                },
            },
        }
    )


class TestModeManager:
    def test_default_mode_from_config(self, config):
        manager = ModeManager(config)
        assert manager.active_mode_name == "default"
        assert manager.active_mode.main.model == "claude-sonnet-5"

    def test_set_mode_switches_and_clears_overrides(self, config):
        manager = ModeManager(config)
        manager.override("title", "openai", "gpt-4o")
        manager.set_mode("cheap")
        assert manager.active_mode_name == "cheap"
        assert manager.overrides == {}

    def test_override_changes_effective_config(self, config):
        manager = ModeManager(config)
        manager.override("title", "anthropic", "claude-haiku")
        effective = manager.current_effective_refs()
        assert effective["title"].provider == "anthropic"
        assert effective["title"].model == "claude-haiku"

    def test_unknown_slot_raises(self, config):
        manager = ModeManager(config)
        with pytest.raises(KeyError):
            manager.override("unknown", "openai", "gpt-4o")

    def test_guardrail_mode_overrides_config(self, config):
        manager = ModeManager(config)
        assert manager.guardrail_template == "Base guardrail"
        manager.set_mode("cheap")
        assert manager.guardrail_template == "Cheap guardrail"

    def test_snapshot_roundtrip(self, config, tmp_path):
        manager = ModeManager(config)
        manager.override("title", "anthropic", "claude-haiku")
        path = tmp_path / "snapshot.json"
        written = manager.persist_snapshot(path)
        assert written == path
        assert path.exists()

        manager.override("title", "openai", "gpt-4o")
        loaded = manager.load_snapshot(path)
        assert loaded["title"].provider == "anthropic"

        report_effective = manager.current_effective_refs()
        assert report_effective["title"].provider == "openai"
