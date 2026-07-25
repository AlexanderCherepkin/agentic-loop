"""Mock routing tests for LLMEngine model-economy integration."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))

from runtime.engine.llm_engine import LLMConfig, LLMEngine, LLMProvider
from runtime.engine.mode_manager import ModeManager
from runtime.engine.model_economy_config import ModelEconomyConfig

pytestmark = [pytest.mark.core, pytest.mark.runtime]


@pytest.fixture
def config():
    return ModelEconomyConfig.from_dict(
        {
            "default_mode": "default",
            "guardrail_template": "Be minimal.",
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
                }
            },
            "smart_routers": {
                "pareto_code": {
                    "provider": "openrouter",
                    "model": "openrouter/pareto-code",
                    "min_coding_score": 0.65,
                    "min_context_tokens": 65536,
                }
            },
        }
    )


class TestLLMEngineModelEconomy:
    def test_main_path_uses_engine_config(self, config):
        manager = ModeManager(config)
        engine = LLMEngine(LLMConfig(provider=LLMProvider.MOCK, model="mock-engine"), mode_manager=manager)
        provider, model = engine.resolve_model("main")
        assert provider == LLMProvider.MOCK
        assert model == "mock-engine"

    def test_auxiliary_slot_routing(self, config):
        manager = ModeManager(config)
        engine = LLMEngine(LLMConfig(provider=LLMProvider.MOCK, model="mock-engine"), mode_manager=manager)
        provider, model = engine.resolve_model("title")
        assert provider == LLMProvider.GOOGLE
        assert model == "gemini-flash-latest"

        provider, model = engine.resolve_model("code_review")
        assert provider == LLMProvider.OPENAI
        assert model == "gpt-4o-mini"

    def test_apply_guardrails_prefixes_template(self, config):
        manager = ModeManager(config)
        engine = LLMEngine(LLMConfig(provider=LLMProvider.MOCK, model="mock-engine"), mode_manager=manager)
        guarded = engine.apply_guardrails("system prompt")
        assert guarded.startswith("Be minimal.")
        assert "system prompt" in guarded

    def test_apply_guardrails_passthrough_when_no_template(self, config):
        manager = ModeManager(config)
        manager.set_mode("default")  # already default, but ensure template from mode
        engine = LLMEngine(LLMConfig(provider=LLMProvider.MOCK, model="mock-engine"), mode_manager=manager)
        engine.mode_manager.config.guardrail_template = None
        assert engine.apply_guardrails("system prompt") == "system prompt"

    def test_check_drift_returns_none_for_clean_state(self, config):
        manager = ModeManager(config)
        engine = LLMEngine(LLMConfig(provider=LLMProvider.MOCK, model="mock-engine"), mode_manager=manager)
        report = engine.check_drift()
        assert report.severity.value == "none"

    def test_check_drift_raises_when_critical(self, config):
        manager = ModeManager(config)
        manager.override("title", "openai", "gpt-4o")
        engine = LLMEngine(LLMConfig(provider=LLMProvider.MOCK, model="mock-engine"), mode_manager=manager)
        report = engine.check_drift()
        assert report.severity.value == "warning"
        with pytest.raises(RuntimeError):
            engine.check_drift(critical=True)

    def test_openrouter_provider_enum(self):
        assert LLMProvider("openrouter") == LLMProvider.OPENROUTER
        assert LLMProvider("google") == LLMProvider.GOOGLE

    def test_unknown_provider_string_maps_to_anthropic(self, config):
        manager = ModeManager(config)
        engine = LLMEngine(LLMConfig(provider=LLMProvider.MOCK, model="mock-engine"), mode_manager=manager)
        # Inject an override with a provider not in the enum
        manager.override("summary", "unknown-provider", "mystery-model")
        provider, model = engine.resolve_model("summary")
        assert provider == LLMProvider.ANTHROPIC
        assert model == "mystery-model"
