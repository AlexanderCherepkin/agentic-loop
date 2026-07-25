"""Tests for model economy configuration dataclasses and loader."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))

from runtime.engine.model_economy_config import (
    AuxiliarySlots,
    Mode,
    ModelEconomyConfig,
    ModelRef,
    SmartRouter,
    load_model_economy_config,
)

pytestmark = [pytest.mark.core, pytest.mark.runtime]


class TestModelRef:
    def test_to_dict_roundtrip(self):
        ref = ModelRef(provider="openai", model="gpt-4o")
        assert ModelRef.from_dict(ref.to_dict()) == ref


class TestAuxiliarySlots:
    def test_default_slots_are_cheap(self):
        slots = AuxiliarySlots()
        assert slots.title.provider == "google"
        assert slots.code_review.provider == "openai"

    def test_slot_lookup(self):
        slots = AuxiliarySlots.from_dict(
            {
                "title": {"provider": "anthropic", "model": "claude-haiku"},
                "vision": {"provider": "google", "model": "gemini-2.5-flash"},
            }
        )
        assert slots.slot("title").provider == "anthropic"
        with pytest.raises(KeyError):
            slots.slot("unknown")


class TestMode:
    def test_model_for_main_and_slots(self):
        mode = Mode.from_dict(
            "default",
            {
                "description": "d",
                "main": {"provider": "anthropic", "model": "claude-sonnet-5"},
                "auxiliary": {"title": {"provider": "google", "model": "gemini-flash"}},
            },
        )
        assert mode.model_for(None).model == "claude-sonnet-5"
        assert mode.model_for("title").model == "gemini-flash"

    def test_guardrail_template_optional(self):
        mode = Mode.from_dict(
            "g",
            {
                "description": "d",
                "main": {"provider": "anthropic", "model": "claude-sonnet-5"},
                "auxiliary": {},
                "guardrail_template": "Be safe.",
            },
        )
        assert mode.guardrail_template == "Be safe."


class TestSmartRouter:
    def test_defaults(self):
        router = SmartRouter.from_dict("auto", {"provider": "openrouter", "model": "openrouter/auto"})
        assert router.min_coding_score == 0.0
        assert router.min_context_tokens == 0


class TestModelEconomyConfig:
    def test_get_mode_unknown_raises(self):
        cfg = ModelEconomyConfig(modes={}, default_mode="default")
        with pytest.raises(KeyError):
            cfg.get_mode("missing")

    def test_merge_overrides_mode(self):
        cfg = ModelEconomyConfig.from_dict(
            {
                "default_mode": "default",
                "modes": {
                    "default": {
                        "description": "base",
                        "main": {"provider": "anthropic", "model": "claude-sonnet-5"},
                        "auxiliary": {},
                    }
                },
            }
        )
        merged = cfg.merge(
            {
                "modes": {
                    "default": {
                        "main": {"provider": "openai", "model": "gpt-4o"}
                    }
                }
            }
        )
        assert merged.get_mode("default").main.provider == "openai"


class TestLoadModelEconomyConfig:
    def test_loads_project_defaults(self):
        cfg = load_model_economy_config()
        assert "default" in cfg.modes
        assert cfg.default_mode == "default"
        assert cfg.guardrail_template is not None
        assert "auto" in cfg.smart_routers
        assert "pareto_code" in cfg.smart_routers

    def test_merge_user_config_nested_section(self, tmp_path):
        project = tmp_path / "model_economy.yaml"
        project.write_text(
            """
guardrail_template: Project template
default_mode: default
modes:
  default:
    description: base
    main:
      provider: anthropic
      model: claude-sonnet-5
    auxiliary:
      title:
        provider: google
        model: gemini-flash-latest
""",
            encoding="utf-8",
        )
        user = tmp_path / "hermes.yaml"
        user.write_text(
            """
model_economy:
  guardrail_template: User template
  modes:
    default:
      main:
        provider: openai
        model: gpt-4o
""",
            encoding="utf-8",
        )
        cfg = load_model_economy_config(project, user)
        assert cfg.guardrail_template == "User template"
        assert cfg.get_mode("default").main.provider == "openai"
        assert cfg.get_mode("default").auxiliary.title.model == "gemini-flash-latest"
