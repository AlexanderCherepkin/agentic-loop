"""pytest tests for the premium-design motion executor.

Verifies that DTCG motion tokens are turned into Framer Motion variants,
CSS transitions, and a Tailwind extension, while blocking layout-property
animations and respecting prefers-reduced-motion in generated comments.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import pytest

from runtime.premium_design.motion_executor import MotionExecutor, MotionExecutorResult


@pytest.fixture
def sample_tokens() -> dict:
    return {
        "motion": {
            "allowed_properties": {"$value": ["opacity", "transform", "color"]},
            "duration": {
                "base": {"$type": "duration", "$value": "0.25s"},
                "fast": {"$type": "duration", "$value": "0.15s"},
                "slow": {"$type": "duration", "$value": "0.45s"},
            },
            "easing": {
                "product": {"$type": "cubicBezier", "$value": [0.16, 1, 0.3, 1]},
                "exit": {"$type": "cubicBezier", "$value": [0.4, 0, 1, 1]},
            },
        }
    }


def test_execute_generates_all_representations(sample_tokens: dict) -> None:
    executor = MotionExecutor(sample_tokens)
    result = executor.execute()
    assert isinstance(result, MotionExecutorResult)
    assert result.ok is True
    assert result.motion_level > 0
    assert "opacity" in result.allowed_properties
    assert set(result.framer_motion_variants.keys()) == {"fade", "slideUp", "scaleIn"}
    assert "base" in result.css_transitions
    assert "exit" in result.css_transitions
    assert result.tailwind_extend.get("transitionDuration", {}).get("base") == "0.25s"
    assert "product" in result.tailwind_extend.get("transitionTimingFunction", {})


def test_execute_rejects_layout_properties(sample_tokens: dict) -> None:
    sample_tokens["motion"]["allowed_properties"]["$value"].append("width")
    executor = MotionExecutor(sample_tokens)
    result = executor.execute()
    assert result.ok is False
    assert any(v["rule"] == "layout_animation" and v["property"] == "width" for v in result.violations)


def test_execute_returns_error_for_invalid_motion_type() -> None:
    executor = MotionExecutor({"motion": ["invalid"]})
    result = executor.execute()
    assert result.ok is False
    assert any(v["rule"] == "missing_motion_section" for v in result.violations)


def test_framer_ease_conversion(sample_tokens: dict) -> None:
    executor = MotionExecutor(sample_tokens)
    result = executor.execute()
    fade = result.framer_motion_variants["fade"]
    assert fade["transition"]["ease"] == [0.16, 1.0, 0.3, 1.0]


def test_write_artifacts(tmp_path: Path, sample_tokens: dict) -> None:
    executor = MotionExecutor(sample_tokens)
    result = executor.execute()
    paths = executor.write_artifacts(result, tmp_path / "motion", prefix="tokens")

    assert (tmp_path / "motion" / "tokens.ts").exists()
    assert (tmp_path / "motion" / "tokens.css").exists()
    assert (tmp_path / "motion" / "tokens-tailwind-extend.json").exists()
    assert set(paths.keys()) == {"framer_motion", "css", "tailwind_extend"}

    ts_text = paths["framer_motion"].read_text(encoding="utf-8")
    assert "prefers-reduced-motion" in ts_text
    assert "fadeVariants" in ts_text

    css_text = paths["css"].read_text(encoding="utf-8")
    assert "transition-base" in css_text
    assert "@media (prefers-reduced-motion: no-preference)" in css_text
