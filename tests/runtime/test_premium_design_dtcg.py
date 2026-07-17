"""Tests for the premium DTCG token generator."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from runtime.premium_design import DtcgTokenEngine, PremiumDesignConfig, detect_slop_tokens
from runtime.premium_design.dtcg_engine import _analyze_direction


@pytest.fixture
def engine():
    return DtcgTokenEngine()


def test_analyze_direction_editorial():
    assert _analyze_direction("Мода и архитектура в одном журнале") == "editorial"
    assert _analyze_direction("Fashion editorial publication") == "editorial"


def test_analyze_direction_tech():
    assert _analyze_direction("SaaS dashboard для AI API") == "minimal_tech"
    assert _analyze_direction("Machine learning platform") == "minimal_tech"


def test_analyze_direction_retro():
    assert _analyze_direction("Ретро-футуристичный dark mode лендинг") == "retro_futuristic"


def test_analyze_direction_brutalist():
    assert _analyze_direction("Brutalist poster-style сайт") == "brutalist"


def test_analyze_direction_defaults_to_swiss():
    assert _analyze_direction("просто хороший сайт") == "swiss_minimal"


def test_generate_returns_dtcg_structure(engine: DtcgTokenEngine):
    result = engine.generate("SaaS dashboard для AI API", variance=0.5, density=0.0, motion=0.0)

    assert result.direction == "minimal_tech"
    assert "$description" in result.tokens
    assert result.tokens["direction"]["$type"] == "string"
    assert result.tokens["color"]["primary"]["$type"] == "color"
    assert result.tokens["fontFamily"]["body"]["$type"] == "fontFamily"
    assert result.tokens["spacing"]["md"]["$type"] == "dimension"
    assert result.tokens["shadow"]["soft"]["$type"] == "shadow"
    assert result.tokens["motion"]["easing"]["product"]["$type"] == "cubicBezier"


def test_no_forbidden_fonts_in_generated_tokens(engine: DtcgTokenEngine):
    result = engine.generate("Лендинг для AI-стартапа", variance=0.6, density=0.2, motion=0.4)
    violations = detect_slop_tokens(result.tokens)
    font_violations = [v for v in violations if v["rule"] == "forbidden_font"]
    assert not font_violations, f"Forbidden fonts found: {font_violations}"


def test_muted_color_is_not_flat_gray(engine: DtcgTokenEngine):
    result = engine.generate("Editorial media site", variance=0.3, density=0.0)
    muted = result.tokens["color"]["muted"]["$value"]
    assert muted.lower() not in ("#777777", "#808080", "#888888", "#999999")


def test_spacing_grows_non_linearly(engine: DtcgTokenEngine):
    result = engine.generate("SaaS dashboard", variance=0.5, density=0.0)
    spacing = result.tokens["spacing"]
    values = [int(spacing[k]["$value"].replace("px", "")) for k in ("xs", "sm", "md", "lg", "xl", "2xl")]
    # Large jump between md and xl (anti-slop #15)
    assert values[-1] - values[0] >= 48


def test_motion_forbids_layout_properties(engine: DtcgTokenEngine):
    result = engine.generate("Dashboard", motion=0.8)
    allowed = result.tokens["motion"]["allowed_properties"]["$value"]
    for prop in ("width", "height", "margin", "padding", "top", "left"):
        assert prop not in allowed


def test_detect_slop_flags_forbidden_font():
    tokens = {
        "fontFamily": {
            "body": {"$value": "'Inter', sans-serif", "$type": "fontFamily"}
        }
    }
    violations = detect_slop_tokens(tokens)
    assert any(v["rule"] == "forbidden_font" and v["family"] == "inter" for v in violations)


def test_detect_slop_flags_generic_shadow():
    tokens = {
        "shadow": {
            "card": {"$value": "0 4px 6px rgba(0,0,0,0.1)", "$type": "shadow"}
        }
    }
    violations = detect_slop_tokens(tokens)
    assert any(v["rule"] == "generic_shadow" for v in violations)


def test_detect_slop_flags_uniform_padding():
    tokens = {
        "spacing": {
            "sm": {"$value": "8px", "$type": "dimension"},
            "md": {"$value": "10px", "$type": "dimension"},
        }
    }
    violations = detect_slop_tokens(tokens)
    assert any(v["rule"] == "uniform_padding" for v in violations)


def test_detect_slop_flags_layout_animation():
    tokens = {
        "motion": {
            "allowed_properties": {
                "$value": ["width", "height", "transform"],
                "$type": "stringArray",
            }
        }
    }
    violations = detect_slop_tokens(tokens)
    assert any(v["rule"] == "layout_animation" for v in violations)


def test_tailwind_patch_is_serializable(engine: DtcgTokenEngine):
    result = engine.generate("SaaS landing page")
    patch = result.tailwind_config_patch
    assert "theme" in patch
    assert "extend" in patch["theme"]
    assert "colors" in patch["theme"]["extend"]
    assert "fontFamily" in patch["theme"]["extend"]
    # Should be JSON-serializable
    json.dumps(patch)


def test_write_artifacts_creates_files(engine: DtcgTokenEngine):
    result = engine.generate("Fashion editorial")
    with tempfile.TemporaryDirectory() as tmp:
        paths = engine.write_artifacts(result, tmp, design_md_content="# Design\n")
        assert Path(paths["design_tokens"]).exists()
        assert Path(paths["design_md"]).exists()
        loaded = json.loads(Path(paths["design_tokens"]).read_text(encoding="utf-8"))
        assert loaded["direction"]["$value"] == "editorial"


def test_write_artifacts_includes_motion(engine: DtcgTokenEngine):
    result = engine.generate("SaaS dashboard", motion=0.5)
    with tempfile.TemporaryDirectory() as tmp:
        paths = engine.write_artifacts(result, tmp, design_md_content="# Design\n", include_motion=True)
        assert Path(paths["design_tokens"]).exists()
        assert Path(paths["framer_motion"]).exists()
        assert Path(paths["css"]).exists()
        assert Path(paths["tailwind_extend"]).exists()


def test_generate_motion_artifacts_raises_on_bad_tokens(engine: DtcgTokenEngine):
    with tempfile.TemporaryDirectory() as tmp:
        bad_tokens = {
            "motion": {
                "allowed_properties": {"$value": ["width"]},
                "duration": {},
                "easing": {},
            }
        }
        with pytest.raises(ValueError):
            engine.generate_motion_artifacts(bad_tokens, tmp)


def test_empty_brief_raises(engine: DtcgTokenEngine):
    with pytest.raises(ValueError):
        engine.generate("")
    with pytest.raises(ValueError):
        engine.generate("   ")


def test_direction_override_takes_precedence(engine: DtcgTokenEngine):
    result = engine.generate("SaaS dashboard", direction_override="editorial")
    assert result.direction == "editorial"


def test_refactoring_ui_threshold_is_configurable():
    config = PremiumDesignConfig(refactoring_ui_threshold=1.0)
    engine = DtcgTokenEngine(config=config)
    with pytest.raises(ValueError) as exc_info:
        engine.generate("Лендинг")
    assert "threshold=1.0" in str(exc_info.value)


def test_non_strict_mode_returns_failed_result():
    config = PremiumDesignConfig(refactoring_ui_threshold=1.0, strict_refactoring_ui=False)
    engine = DtcgTokenEngine(config=config)
    result = engine.generate("Лендинг")
    assert result.refactoring_ui_passed is False
    assert result.refactoring_ui_aggregate < 1.0
    assert result.tokens["refactoring_ui_scores"]["passed"] is False


def test_default_strict_mode_raises_on_low_score():
    config = PremiumDesignConfig(refactoring_ui_threshold=1.0)
    engine = DtcgTokenEngine(config=config)
    with pytest.raises(ValueError):
        engine.generate("Лендинг")
