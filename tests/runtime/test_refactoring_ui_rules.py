"""Tests for Refactoring UI deterministic checks."""

from __future__ import annotations

import pytest

from runtime.premium_design.refactoring_ui_rules import (
    aggregate_score,
    palette_semantic_score,
    run_all_refactoring_ui_checks,
    scale_contrast_score,
    shadow_elevation_score,
    spacing_rhythm_score,
    state_completeness_score,
    type_pairing_score,
)


def _color(value: str) -> dict[str, str]:
    return {"$value": value, "$type": "color"}


def _font(value: str) -> dict[str, str]:
    return {"$value": value, "$type": "fontFamily"}


def _dim(value: str) -> dict[str, str]:
    return {"$value": value, "$type": "dimension"}


def test_scale_contrast_detects_weak_hierarchy():
    tokens = {
        "fontSize": {
            "sm": {"$value": {"fontSize": "14px"}, "$type": "typography"},
            "base": {"$value": {"fontSize": "15px"}, "$type": "typography"},
            "lg": {"$value": {"fontSize": "16px"}, "$type": "typography"},
        }
    }
    score = scale_contrast_score(tokens)
    assert score.score < 0.7
    assert any(v.rule == "intentional_jumps" for v in score.violations)


def test_scale_contrast_passes_strong_hierarchy():
    tokens = {
        "fontSize": {
            "sm": {"$value": {"fontSize": "14px"}, "$type": "typography"},
            "base": {"$value": {"fontSize": "18px"}, "$type": "typography"},
            "lg": {"$value": {"fontSize": "24px"}, "$type": "typography"},
            "xl": {"$value": {"fontSize": "48px"}, "$type": "typography"},
        }
    }
    score = scale_contrast_score(tokens)
    assert score.score == 1.0


def test_palette_semantic_requires_roles():
    tokens = {"color": {"primary": _color("#0055FF")}}
    score = palette_semantic_score(tokens)
    assert score.score < 1.0
    assert any(v.rule == "semantic_roles_present" for v in score.violations)


def test_palette_semantic_rejects_flat_gray_on_white():
    tokens = {
        "color": {
            "background": _color("#FFFFFF"),
            "text": _color("#808080"),
        }
    }
    score = palette_semantic_score(tokens)
    assert any(v.rule == "no_flat_gray_on_white" for v in score.violations)


def test_palette_semantic_allows_cool_gray():
    tokens = {
        "color": {
            "background": _color("#FFFFFF"),
            "muted": _color("#6B6B75"),
        }
    }
    score = palette_semantic_score(tokens)
    assert not any(v.rule == "no_flat_muted" for v in score.violations)


def test_shadow_elevation_rejects_uniform_shadows():
    tokens = {
        "shadow": {
            "card": {"$value": "0 4px 24px -4px rgba(0,0,0,0.04)", "$type": "shadow"},
            "modal": {"$value": "0 4px 24px -4px rgba(0,0,0,0.04)", "$type": "shadow"},
        }
    }
    score = shadow_elevation_score(tokens)
    assert score.score == 0.0


def test_shadow_elevation_rejects_generic_shadows():
    tokens = {
        "shadow": {
            "card": {"$value": "0 4px 6px rgba(0,0,0,0.1)", "$type": "shadow"},
        }
    }
    score = shadow_elevation_score(tokens)
    assert any(v.rule == "no_generic_shadows" for v in score.violations)


def test_spacing_rhythm_rejects_uniform_scale():
    tokens = {
        "spacing": {
            "xs": _dim("4px"),
            "sm": _dim("8px"),
            "md": _dim("12px"),
            "lg": _dim("16px"),
        }
    }
    score = spacing_rhythm_score(tokens)
    assert score.score == 0.0


def test_spacing_rhythm_passes_non_linear_scale():
    tokens = {
        "spacing": {
            "xs": _dim("4px"),
            "sm": _dim("8px"),
            "md": _dim("12px"),
            "lg": _dim("30px"),
            "xl": _dim("48px"),
        }
    }
    score = spacing_rhythm_score(tokens)
    assert score.score >= 0.85


def test_type_pairing_fails_forbidden_font():
    tokens = {
        "fontFamily": {
            "display": _font("'Inter', sans-serif"),
            "body": _font("'Playfair Display', serif"),
        }
    }
    score = type_pairing_score(tokens)
    assert score.score == 0.0
    assert any(v.rule == "forbidden_font" for v in score.violations)


def test_type_pairing_fails_single_font():
    tokens = {
        "fontFamily": {
            "display": _font("'Playfair Display', serif"),
            "body": _font("'Playfair Display', serif"),
        }
    }
    score = type_pairing_score(tokens)
    assert score.score < 1.0
    assert any(v.rule == "distinct_pairing" for v in score.violations)


def test_state_completeness_checks_inline_states():
    tokens = {
        "color": {
            "primary": {
                "default": _color("#0055FF"),
                "hover": _color("#3377FF"),
                "focus": _color("#0055FF"),
                "active": _color("#0044CC"),
            }
        }
    }
    score = state_completeness_score(tokens)
    assert score.score == 1.0


def test_state_completeness_checks_standalone_states():
    tokens = {
        "color": {"primary": _color("#0055FF")},
        "states": {
            "primary": {
                "hover": _color("#3377FF"),
                "disabled": _color("#99AAFF"),
            }
        },
    }
    score = state_completeness_score(tokens)
    assert score.score == 1.0


def test_state_completeness_warns_missing_states():
    tokens = {"color": {"primary": _color("#0055FF")}}
    score = state_completeness_score(tokens)
    assert 0.5 <= score.score < 1.0
    assert any(v.rule == "interactive_states_defined" for v in score.violations)


def test_aggregate_score_computes_mean():
    scores = [
        scale_contrast_score({"fontSize": {"xl": {"$value": {"fontSize": "48px"}, "$type": "typography"}}}),
        palette_semantic_score({"color": {}}),
    ]
    assert aggregate_score(scores) == round(sum(s.score for s in scores) / 2, 2)


def test_run_all_checks_returns_six_principles():
    tokens = {
        "color": {
            "primary": _color("#1A1A17"),
            "background": _color("#FAFAFA"),
            "surface": _color("#FFFFFF"),
            "text": _color("#1A1A17"),
            "border": _color("#E8E8E6"),
            "accent": _color("#8B3A3A"),
            "muted": _color("#73736E"),
        },
        "fontFamily": {
            "display": _font("'Playfair Display', serif"),
            "body": _font("'Plus Jakarta Sans', sans-serif"),
        },
        "fontSize": {
            "base": {"$value": {"fontSize": "16px"}, "$type": "typography"},
            "xl": {"$value": {"fontSize": "48px"}, "$type": "typography"},
        },
        "spacing": {
            "sm": _dim("8px"),
            "md": _dim("16px"),
            "xl": _dim("48px"),
        },
        "shadow": {
            "soft": {"$value": "0 24px 48px -12px rgba(0,0,0,0.08)", "$type": "shadow"},
            "hard": {"$value": "0 1px 2px rgba(0,0,0,0.12)", "$type": "shadow"},
        },
    }
    scores = run_all_refactoring_ui_checks(tokens)
    principles = {s.principle for s in scores}
    assert principles == {
        "scale_contrast",
        "palette_semantic",
        "shadow_elevation",
        "spacing_rhythm",
        "type_pairing",
        "state_completeness",
    }
