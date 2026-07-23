"""Tests for PonytailOptimizer deterministic helpers."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from runtime.engine.ponytail_optimizer import PonytailOptimizer


pytestmark = [pytest.mark.core, pytest.mark.runtime]


def test_default_mode_is_full():
    opt = PonytailOptimizer()
    assert opt.mode == "full"
    assert opt.mode_enabled is True


def test_invalid_mode_defaults_to_full():
    opt = PonytailOptimizer(default_mode="unknown")
    assert opt.mode == "full"


def test_set_mode_switches_validly():
    opt = PonytailOptimizer()
    msg = opt.set_mode("lite")
    assert opt.mode == "lite"
    assert "LITE" in msg


def test_set_mode_rejects_unknown():
    opt = PonytailOptimizer()
    msg = opt.set_mode("bad")
    assert opt.mode == "full"
    assert "Unknown" in msg


def test_mode_off_disables_injection():
    opt = PonytailOptimizer(default_mode="off")
    assert opt.mode_enabled is False
    assert opt.inject_rules("base", "code_change") == "base"


def test_coding_task_types_inject_rules():
    opt = PonytailOptimizer()
    for task in ["code_change", "fix", "generate_component", "backend_bridge"]:
        injected = opt.inject_rules("base", task)
        assert "PONYTAIL PROTOCOL" in injected


def test_non_coding_task_types_passthrough():
    opt = PonytailOptimizer()
    for task in ["question", "summary", "translation", "chat"]:
        assert opt.inject_rules("base", task) == "base"


def test_coding_heuristic_for_unlisted_tasks():
    opt = PonytailOptimizer()
    assert "PONYTAIL PROTOCOL" in opt.inject_rules("base", "optimize_layout")
    assert "PONYTAIL PROTOCOL" in opt.inject_rules("base", "build_api_route")


def test_extract_metrics_computes_reduction():
    opt = PonytailOptimizer()
    original = "line1\nline2\nline3\n"
    generated = "line1\nline3\n"
    metrics = opt.extract_metrics(original, generated)
    assert metrics.original_loc == 3
    assert metrics.generated_loc == 2
    assert metrics.saved_loc == 1
    assert metrics.reduction_percentage == 33.33


def test_extract_metrics_zero_original():
    opt = PonytailOptimizer()
    metrics = opt.extract_metrics("", "x = 1")
    assert metrics.saved_loc == 0
    assert metrics.reduction_percentage == 0.0


def test_to_dict():
    opt = PonytailOptimizer(default_mode="ultra")
    assert opt.to_dict() == {"mode": "ultra", "enabled": True}
