"""Tests for runtime/cost_tracking engine and backend."""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from runtime.cost_tracking import CostTrackingConfig, CostTrackingEngine


pytestmark = [pytest.mark.core, pytest.mark.runtime]


def test_estimate_known_model():
    engine = CostTrackingEngine(CostTrackingConfig(enabled=True))
    est = engine.estimate("gpt-4o", "input text", "output text", agent="test")
    assert est.model == "gpt-4o"
    assert est.total_cost > 0


def test_estimate_unknown_model_uses_default():
    engine = CostTrackingEngine(CostTrackingConfig(enabled=True))
    est = engine.estimate("unknown-model", "input text", "output text")
    assert est.total_cost == 0.0


def test_record_and_report(tmp_path):
    db = tmp_path / "cost.db"
    engine = CostTrackingEngine(CostTrackingConfig(enabled=True, db_path=db))
    est = engine.estimate("gpt-4o", "input", "output", agent="test")
    engine.record("demo", est)
    report = engine.get_report(scope="demo")
    assert report["total_cost"] == pytest.approx(est.total_cost)
    assert report["calls"] == 1


def test_budget_check(tmp_path):
    db = tmp_path / "cost.db"
    engine = CostTrackingEngine(CostTrackingConfig(enabled=True, db_path=db))
    engine.set_budget("demo", 0.001)
    est = engine.estimate("gpt-4o", "x" * 4000, "y" * 4000, agent="test")
    engine.record("demo", est)
    verdict = engine.check_budget("demo")
    assert verdict["limit"] == 0.001
    assert verdict["allowed"] is False


def test_record_llm_response(tmp_path):
    db = tmp_path / "cost.db"
    engine = CostTrackingEngine(CostTrackingConfig(enabled=True, db_path=db))
    est = engine.record_llm_response(
        scope="demo",
        model="gpt-4o",
        system_prompt="sys",
        user_message="user",
        response_text="resp",
        agent="test",
    )
    assert est.total_cost > 0
    assert engine.get_report(scope="demo")["calls"] == 1
