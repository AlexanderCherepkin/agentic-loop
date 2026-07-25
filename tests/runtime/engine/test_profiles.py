"""Tests for ProfileResolver and LLMEngine profile integration."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))

from runtime.engine.llm_engine import LLMConfig, LLMEngine, LLMProvider
from runtime.engine.profile_resolver import ProfileResolver

pytestmark = [pytest.mark.core, pytest.mark.runtime]


@pytest.fixture
def profiles_root(tmp_path):
    root = tmp_path / "profiles"
    architect = root / "architect"
    architect.mkdir(parents=True)
    (architect / "config.yaml").write_text(
        "name: architect\nprovider: anthropic\nmodel: claude-opus-4-8\nmode: premium_final\n",
        encoding="utf-8",
    )
    (architect / "SOUL.md").write_text(
        "---\nname: architect\n---\n\nYou are a senior architect. Prefer minimal reversible designs.\n",
        encoding="utf-8",
    )
    return root


class TestProfileResolver:
    def test_resolve_existing_profile(self, profiles_root):
        resolver = ProfileResolver(profiles_root)
        profile = resolver.resolve("architect")
        assert profile.profile_id == "architect"
        assert profile.model_ref.model == "claude-opus-4-8"
        assert profile.soul_prompt is not None
        assert "senior architect" in profile.soul_prompt

    def test_resolve_missing_profile_raises(self, profiles_root):
        resolver = ProfileResolver(profiles_root)
        with pytest.raises(KeyError):
            resolver.resolve("missing")

    def test_list_profiles(self, profiles_root):
        resolver = ProfileResolver(profiles_root)
        assert resolver.list_profiles() == ["architect"]

    def test_full_system_prefix_composes(self, profiles_root):
        resolver = ProfileResolver(profiles_root)
        profile = resolver.resolve("architect")
        full = profile.full_system_prefix("base prompt")
        assert "senior architect" in full
        assert "base prompt" in full

    def test_profile_without_soul(self, tmp_path):
        root = tmp_path / "profiles" / "minimal"
        root.mkdir(parents=True)
        (root / "config.yaml").write_text(
            "name: minimal\nmodel: gpt-4o-mini\nprovider: openai\n",
            encoding="utf-8",
        )
        resolver = ProfileResolver(tmp_path / "profiles")
        profile = resolver.resolve("minimal")
        assert profile.soul_prompt is None
        assert profile.model_ref.provider == "openai"

    def test_fallback_to_active_mode(self, profiles_root):
        from runtime.engine.mode_manager import ModeManager
        from runtime.engine.model_economy_config import ModelEconomyConfig

        config = ModelEconomyConfig.from_dict(
            {
                "default_mode": "default",
                "modes": {
                    "default": {
                        "description": "base",
                        "main": {"provider": "google", "model": "gemini-flash-latest"},
                        "auxiliary": {},
                    }
                },
            }
        )
        manager = ModeManager(config)

        # Profile with no provider/model in config falls back to active mode
        profile_dir = profiles_root / "fallback"
        profile_dir.mkdir()
        (profile_dir / "config.yaml").write_text("name: fallback\n", encoding="utf-8")
        (profile_dir / "SOUL.md").write_text("# Fallback persona\n", encoding="utf-8")

        resolver = ProfileResolver(profiles_root)
        profile = resolver.resolve("fallback", mode_manager=manager)
        assert profile.model_ref.provider == "google"
        assert profile.model_ref.model == "gemini-flash-latest"


class TestLLMEngineProfiles:
    def test_resolve_profile_model(self, profiles_root):
        engine = LLMEngine(
            LLMConfig(provider=LLMProvider.MOCK, model="mock-engine"),
            profile_resolver=ProfileResolver(profiles_root),
        )
        provider, model = engine.resolve_profile_model("architect")
        assert provider == LLMProvider.ANTHROPIC
        assert model == "claude-opus-4-8"

    def test_apply_profile_and_guardrails(self, profiles_root):
        engine = LLMEngine(
            LLMConfig(provider=LLMProvider.MOCK, model="mock-engine"),
            profile_resolver=ProfileResolver(profiles_root),
        )
        system = engine._apply_profile_and_guardrails("base prompt", profile_id="architect")
        assert "senior architect" in system
        assert "base prompt" in system

    def test_apply_profile_missing_raises(self, profiles_root):
        engine = LLMEngine(
            LLMConfig(provider=LLMProvider.MOCK, model="mock-engine"),
            profile_resolver=ProfileResolver(profiles_root),
        )
        with pytest.raises(KeyError):
            engine._apply_profile_and_guardrails("base prompt", profile_id="missing")
