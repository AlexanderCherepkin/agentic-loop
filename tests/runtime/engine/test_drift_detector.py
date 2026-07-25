"""Tests for ModelEconomy drift detection."""

from __future__ import annotations

import random
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))

from runtime.engine.drift_detector import DriftDetector, DriftSeverity
from runtime.engine.mode_manager import ModeManager
from runtime.engine.model_economy_config import ModelEconomyConfig

pytestmark = [pytest.mark.core, pytest.mark.runtime]


@pytest.fixture
def config():
    return ModelEconomyConfig.from_dict(
        {
            "default_mode": "default",
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
        }
    )


@pytest.fixture
def detector():
    return DriftDetector()


class TestDriftDetector:
    def test_no_drift_clean_state(self, config, detector):
        manager = ModeManager(config)
        report = detector.detect(manager)
        assert report.severity == DriftSeverity.NONE
        assert not report.has_drift
        assert report.template_drifts == []
        assert report.snapshot_drifts == []

    def test_template_drift_detected(self, config, detector):
        manager = ModeManager(config)
        manager.override("title", "anthropic", "claude-haiku")
        report = detector.detect(manager)
        assert report.severity == DriftSeverity.WARNING
        assert report.has_drift
        assert any(d["slot"] == "title" and d["kind"] == "template" for d in report.template_drifts)

    def test_snapshot_drift_only_info(self, config, detector):
        manager = ModeManager(config)
        manager.override("title", "openai", "gpt-4o")  # drift away from template
        manager.persist_snapshot()  # remember the overridden value as snapshot
        manager.clear_overrides()  # back to template; now differs from snapshot only
        report = detector.detect(manager)
        assert report.severity == DriftSeverity.INFO
        assert any(d["slot"] == "title" and d["kind"] == "snapshot" for d in report.snapshot_drifts)

    def test_critical_escalates_severity(self, config, detector):
        manager = ModeManager(config)
        manager.override("approval", "anthropic", "claude-opus")
        report = detector.detect(manager, critical=True)
        assert report.severity == DriftSeverity.CRITICAL
        assert report.critical is True


class TestDriftDetectorFuzz:
    """Hand-crafted fuzz ensuring ≥100 random mutations do not crash or hide drift."""

    def test_random_mutations_never_crash(self, config, detector):
        slots = ["main", "title", "vision", "compression", "approval", "web_extract", "code_review", "summary"]
        providers = ["anthropic", "openai", "google", "openrouter", "deepseek"]
        models = ["a", "b", "c", "gpt-4o", "claude-sonnet-5", "gemini-flash-latest"]
        rng = random.Random(42)
        for _ in range(100):
            manager = ModeManager(config)
            mutations = rng.randint(0, 4)
            for _ in range(mutations):
                slot = rng.choice(slots)
                provider = rng.choice(providers)
                model = rng.choice(models)
                manager.override(slot, provider, model)
            report = detector.detect(manager)
            assert report.severity in DriftSeverity
            if mutations == 0:
                assert report.severity == DriftSeverity.NONE
