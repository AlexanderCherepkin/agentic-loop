"""Tests for runtime/premium_design engine and config."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from runtime.premium_design.config import PremiumDesignConfig
from runtime.premium_design.engine import PremiumDesignEngine


pytestmark = [pytest.mark.core, pytest.mark.runtime]


def _valid_tokens(direction: str = "editorial") -> dict:
    return {
        "direction": direction,
        "fonts": {
            "base_ui": {"family": "Adisan Richard", "fallback": "system-ui, sans-serif"},
            "display": {"family": "Tiempos Headline", "fallback": "Georgia, serif"},
            "accent": {"family": "Bebas Neue", "fallback": "Abril Fatface, sans-serif"},
            "mono": {"family": "JetBrains Mono", "fallback": "monospace"},
        },
        "colors": {
            "background": {"base": "#0a0a0a", "elevated": "#141414"},
            "text": {"primary": "#f5f5f5", "secondary": "#a3a3a3", "muted": "#525252"},
            "accent": {"primary": "#ff3b30", "secondary": "#007aff"},
        },
        "spacing": {
            "scale": [4, 10, 18, 30, 48, 78],
            "section": {"small": "30px", "medium": "78px", "large": "120px"},
        },
        "grid": {"base_module": "10px", "columns": 12, "gutter": "30px"},
        "motion": {
            "allowed_properties": ["transform", "opacity", "filter"],
            "easing": "cubic-bezier(0.25, 0.1, 0.25, 1)",
            "duration_scale": [150, 300, 600],
        },
        "components": {
            "button": {
                "hover": "transform translateX(4px) + color shift to accent",
                "shape": "sharp rectangle with 2px border",
            }
        },
        "anti_slop": {"verdict": "pending"},
    }


def _design_md(direction: str = "editorial") -> str:
    return f"""# Premium Design: Demo

## Direction
{direction}

## Mood & References
ink, oversized type, grid, contrast, restraint. References: Swiss International Style, Tmag, Area 17.

## Typography
- Base UI: Adisan Richard, fallback system-ui
- Display: Tiempos Headline
- Accent: Bebas Neue
- Mono: JetBrains Mono

## Color System
background base #0a0a0a, text primary #f5f5f5, accent primary #ff3b30.

## Layout Grid
12-column grid, 30px gutter, base module 10px.

## Spacing Scale
4, 10, 18, 30, 48, 78.

## Components Concept
Button: sharp rectangle with 2px border; hover uses transform translateX(4px) + color shift.

## Anti-Slop Checklist
All 10 rules considered.
"""


def test_config_from_dict_defaults():
    cfg = PremiumDesignConfig.from_dict({})
    assert cfg.design_md_name == "DESIGN.md"
    assert cfg.tokens_name == "design_tokens.json"
    assert "Inter" in cfg.forbidden_fonts
    assert "Adisan Richard" in cfg.allowed_fonts


def test_config_validation_errors(tmp_path):
    cfg = PremiumDesignConfig.from_dict({"design_md_name": "", "tokens_name": ""})
    errors = cfg.validate()
    assert any("design_md_name" in e for e in errors)
    assert any("tokens_name" in e for e in errors)


def test_engine_passes_anti_slop(tmp_path):
    root = tmp_path / "project"
    root.mkdir()
    engine = PremiumDesignEngine(root)
    result = engine.write_artifacts(_design_md(), _valid_tokens())

    assert result.status == "pass"
    assert not result.refinement_actions
    assert all(c.status == "pass" for c in result.anti_slop_checks)

    design_path = root / "DESIGN.md"
    tokens_path = root / "design_tokens.json"
    assert design_path.exists()
    assert tokens_path.exists()

    tokens = json.loads(tokens_path.read_text(encoding="utf-8"))
    assert tokens["anti_slop"]["verdict"] == "pass"


def test_engine_fails_on_forbidden_font(tmp_path):
    root = tmp_path / "project"
    root.mkdir()
    tokens = _valid_tokens()
    tokens["fonts"]["base_ui"]["family"] = "Inter"
    design_md = _design_md().replace("Adisan Richard", "Inter")

    engine = PremiumDesignEngine(root)
    result = engine.write_artifacts(design_md, tokens)

    assert result.status == "fail"
    assert any("Inter" in a for a in result.refinement_actions)
    assert any(c.id == "fonts" and c.status == "fail" for c in result.anti_slop_checks)


def test_engine_fails_on_card_shadow(tmp_path):
    root = tmp_path / "project"
    root.mkdir()
    tokens = _valid_tokens()
    tokens["components"]["card"] = {"shadow": "0 4px 6px rgba(0,0,0,0.1)"}

    engine = PremiumDesignEngine(root)
    result = engine.write_artifacts(_design_md(), tokens)

    assert result.status == "fail"
    assert any("shadow" in a.lower() for a in result.refinement_actions)


def test_engine_fails_on_gray_on_white(tmp_path):
    root = tmp_path / "project"
    root.mkdir()
    tokens = _valid_tokens()
    tokens["colors"]["background"]["base"] = "#ffffff"
    tokens["colors"]["text"]["primary"] = "#666666"

    engine = PremiumDesignEngine(root)
    result = engine.write_artifacts(_design_md(), tokens)

    assert result.status == "fail"
    assert any("gray" in a.lower() for a in result.refinement_actions)


def test_engine_fails_on_uniform_padding(tmp_path):
    root = tmp_path / "project"
    root.mkdir()
    tokens = _valid_tokens()
    tokens["spacing"]["scale"] = [16, 16, 16]

    engine = PremiumDesignEngine(root)
    result = engine.write_artifacts(_design_md(), tokens)

    assert result.status == "fail"
    assert any("spacing" in a.lower() for a in result.refinement_actions)


def test_engine_fails_on_layout_animation(tmp_path):
    root = tmp_path / "project"
    root.mkdir()
    tokens = _valid_tokens()
    tokens["motion"]["allowed_properties"] = ["width", "height", "transform"]

    engine = PremiumDesignEngine(root)
    result = engine.write_artifacts(_design_md(), tokens)

    assert result.status == "fail"
    assert any("transform" in a.lower() for a in result.refinement_actions)


def test_engine_fails_single_hero_section(tmp_path):
    root = tmp_path / "project"
    root.mkdir()
    design_md = _design_md().replace(
        "## Layout Grid\n12-column grid, 30px gutter, base module 10px.",
        "## Layout Grid\nFull viewport hero section with centered headline and single centered CTA button."
    )

    engine = PremiumDesignEngine(root)
    result = engine.write_artifacts(design_md, _valid_tokens())

    assert result.status == "fail"
    assert any("hero" in a.lower() for a in result.refinement_actions)
    assert any(c.id == "single_hero_section" and c.status == "fail" for c in result.anti_slop_checks)


def test_engine_passes_single_hero_with_asymmetry(tmp_path):
    root = tmp_path / "project"
    root.mkdir()
    design_md = _design_md().replace(
        "## Layout Grid\n12-column grid, 30px gutter, base module 10px.",
        "## Layout Grid\nSplit hero with off-center headline and asymmetric grid; one CTA aligned to the left column."
    )

    engine = PremiumDesignEngine(root)
    result = engine.write_artifacts(design_md, _valid_tokens())

    assert all(c.id != "single_hero_section" or c.status == "pass" for c in result.anti_slop_checks)


def test_engine_fails_generic_3col_cards(tmp_path):
    root = tmp_path / "project"
    root.mkdir()
    design_md = _design_md().replace(
        "## Components Concept\nButton: sharp rectangle with 2px border; hover uses transform translateX(4px) + color shift.",
        "## Components Concept\nThree feature cards with equal padding and icon on top; one CTA each."
    )

    engine = PremiumDesignEngine(root)
    result = engine.write_artifacts(design_md, _valid_tokens())

    assert result.status == "fail"
    assert any("3-card" in a.lower() or "symmetry" in a.lower() for a in result.refinement_actions)
    assert any(c.id == "generic_3col_cards" and c.status == "fail" for c in result.anti_slop_checks)


def test_engine_fails_gradient_blob(tmp_path):
    root = tmp_path / "project"
    root.mkdir()
    design_md = _design_md().replace(
        "## Mood & References\nink, oversized type, grid, contrast, restraint. References: Swiss International Style, Tmag, Area 17.",
        "## Mood & References\nBlurred gradient orb top left; soft pastel hero blob."
    )

    engine = PremiumDesignEngine(root)
    result = engine.write_artifacts(design_md, _valid_tokens())

    assert result.status == "fail"
    assert any("gradient" in a.lower() for a in result.refinement_actions)
    assert any(c.id == "gradient_blobs" and c.status == "fail" for c in result.anti_slop_checks)


def test_engine_fails_generic_shadow_radius_8(tmp_path):
    root = tmp_path / "project"
    root.mkdir()
    tokens = _valid_tokens()
    tokens["components"]["card"] = {"shadow": "0 8px 16px rgba(0,0,0,0.08)"}

    engine = PremiumDesignEngine(root)
    result = engine.write_artifacts(_design_md(), tokens)

    assert result.status == "fail"
    assert any("shadow" in a.lower() for a in result.refinement_actions)


def test_engine_fails_unfriendly_animation(tmp_path):
    root = tmp_path / "project"
    root.mkdir()
    tokens = _valid_tokens()
    tokens["motion"]["allowed_properties"] = ["width", "height", "opacity"]

    engine = PremiumDesignEngine(root)
    result = engine.write_artifacts(_design_md(), tokens)

    assert result.status == "fail"
    assert any("transform" in a.lower() for a in result.refinement_actions)
    assert any(c.id == "layout_animations" and c.status == "fail" for c in result.anti_slop_checks)
