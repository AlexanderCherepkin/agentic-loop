"""Agent spec tests for analytics and cookie-consent subagents."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import pytest

from runtime.engine.agent_loader import AgentLoader

ANALYTICS_AGENTS = [
    "tooll_subagents/planning/analytics_requirements_analyst.md",
    "tooll_subagents/planning/analytics_provider_selector.md",
    "tooll_subagents/planning/analytics_event_mapper.md",
    "tooll_subagents/planning/analytics_script_injector.md",
    "tooll_subagents/planning/analytics_optimizer.md",
    "tooll_subagents/planning/cookie_consent_jurisdiction_mapper.md",
    "tooll_subagents/planning/cookie_consent_policy_generator.md",
    "tooll_subagents/planning/cookie_consent_banner_planner.md",
    "tooll_subagents/execution/analytics_runtime_integrator.md",
    "tooll_subagents/execution/cookie_consent_blocker.md",
    "tooll_subagents/self_correction/analytics_privacy_validator.md",
    "tooll_subagents/observability/analytics_audit_agent.md",
]


def test_analytics_agents_load_with_algorithmic_template():
    loader = AgentLoader(Path(".agent_loop"))
    for rel in ANALYTICS_AGENTS:
        spec = loader.load_agent(rel)
        assert spec.name
        assert spec.role
        assert spec.contract
        assert spec.decision_flow.steps
        assert spec.failure_modes


def test_analytics_agents_refer_to_runtime_engine():
    loader = AgentLoader(Path(".agent_loop"))
    for rel in ANALYTICS_AGENTS:
        text = (Path(".agent_loop") / rel).read_text(encoding="utf-8")
        assert "## Role" in text
        assert "## Contract" in text
        assert "## Decision Flow" in text
        assert "## Failure Modes" in text
        assert any(
            ref in text
            for ref in [
                "runtime/analytics",
                "analytics_requirements_analyst.md",
                "analytics_provider_selector.md",
                "analytics_event_mapper.md",
                "analytics_script_injector.md",
                "analytics_runtime_integrator.md",
                "cookie_consent_jurisdiction_mapper.md",
                "cookie_consent_policy_generator.md",
                "cookie_consent_blocker.md",
                "analytics_privacy_validator.md",
                "analytics_audit_agent.md",
                "audit_logger.md",
            ]
        )


def test_consent_jurisdiction_mapper_lists_all_frameworks():
    text = (
        Path(".agent_loop")
        / "tooll_subagents"
        / "planning"
        / "cookie_consent_jurisdiction_mapper.md"
    ).read_text(encoding="utf-8")
    for framework in ["GDPR", "ePrivacy", "152-FZ", "PIPL", "CCPA"]:
        assert framework in text


def test_analytics_provider_selector_lists_all_providers():
    text = (
        Path(".agent_loop") / "tooll_subagents" / "planning" / "analytics_provider_selector.md"
    ).read_text(encoding="utf-8")
    for provider in ["ga4", "yandex", "plausible", "posthog", "mixpanel"]:
        assert provider in text


def test_cookie_consent_policy_generator_has_default_deny():
    text = (
        Path(".agent_loop")
        / "tooll_subagents"
        / "planning"
        / "cookie_consent_policy_generator.md"
    ).read_text(encoding="utf-8")
    assert "default-deny" in text.lower() or "default_deny" in text


def test_analytics_privacy_validator_mentions_csp():
    text = (
        Path(".agent_loop")
        / "tooll_subagents"
        / "self_correction"
        / "analytics_privacy_validator.md"
    ).read_text(encoding="utf-8")
    assert "CSP" in text or "Content-Security-Policy" in text
