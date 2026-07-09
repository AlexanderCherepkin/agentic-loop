"""Agent spec tests for i18n subagents."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import pytest

from runtime.engine.agent_loader import AgentLoader

I18N_AGENTS = [
    "tooll_subagents/planning/i18n_requirements_analyst.md",
    "tooll_subagents/planning/i18n_language_detector.md",
    "tooll_subagents/planning/i18n_key_extractor.md",
    "tooll_subagents/planning/i18n_dictionary_generator.md",
    "tooll_subagents/planning/i18n_routing_planner.md",
    "tooll_subagents/planning/i18n_component_rewriter.md",
    "tooll_subagents/planning/i18n_optimizer.md",
    "tooll_subagents/execution/i18n_runtime_integrator.md",
    "tooll_subagents/execution/i18n_fallback_resolver.md",
    "tooll_subagents/self_correction/i18n_rtl_validator.md",
    "tooll_subagents/self_correction/i18n_missing_key_guard.md",
    "tooll_subagents/observability/i18n_audit_agent.md",
]


def test_i18n_agents_load_with_algorithmic_template():
    loader = AgentLoader(Path(".agent_loop"))
    for rel in I18N_AGENTS:
        spec = loader.load_agent(rel)
        assert spec.name
        assert spec.role
        assert spec.contract
        assert spec.decision_flow.steps
        assert spec.failure_modes


def test_i18n_agents_refer_to_runtime_engine():
    loader = AgentLoader(Path(".agent_loop"))
    for rel in I18N_AGENTS:
        text = (Path(".agent_loop") / rel).read_text(encoding="utf-8")
        assert "## Role" in text
        assert "## Contract" in text
        assert "## Decision Flow" in text
        assert "## Failure Modes" in text
        # Every i18n agent should reference at least one other agent or runtime module
        assert any(
            ref in text
            for ref in [
                "runtime/i18n",
                "i18n_key_extractor.md",
                "i18n_dictionary_generator.md",
                "i18n_routing_planner.md",
                "i18n_component_rewriter.md",
                "i18n_runtime_integrator.md",
                "i18n_fallback_resolver.md",
                "i18n_rtl_validator.md",
                "i18n_missing_key_guard.md",
                "i18n_audit_agent.md",
                "audit_logger.md",
            ]
        )


def test_i18n_language_detector_has_llm_fallback():
    spec = AgentLoader(Path(".agent_loop")).load_agent(
        "tooll_subagents/planning/i18n_language_detector.md"
    )
    role = spec.role.lower()
    assert "language" in role
    assert any("LLM" in step or "llm" in step for step in spec.decision_flow.steps)


def test_i18n_rtl_validator_lists_rtl_locales():
    text = (
        Path(".agent_loop") / "tooll_subagents" / "self_correction" / "i18n_rtl_validator.md"
    ).read_text(encoding="utf-8")
    assert any(locale in text for locale in ["ar", "he", "fa", "ur"])
