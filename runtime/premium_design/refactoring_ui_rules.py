"""Refactoring UI principles as deterministic, testable checks.

Each function implements one principle from Adam Wathan + Steve Schoger's
*Refactoring UI* and returns a normalized score plus a list of violations.
These checks are used as hard gates before DTCG tokens are handed off to
Tailwind/code generation.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from .config import DEFAULT_ALLOWED_FONTS, DEFAULT_FORBIDDEN_FONTS


@dataclass
class RefactoringUiViolation:
    principle: str
    rule: str
    message: str
    path: str = ""


@dataclass
class RefactoringUiScore:
    principle: str
    score: float  # 0.0–1.0
    violations: list[RefactoringUiViolation] = field(default_factory=list)


# ---------------------------------------------------------------------------
# 1. Hierarchy through scale contrast
# ---------------------------------------------------------------------------

def scale_contrast_score(tokens: dict[str, Any]) -> RefactoringUiScore:
    """Intentional size differences guide the eye; equal sizes create noise."""

    principle = "scale_contrast"
    typography = tokens.get("fontSize", {})
    if not isinstance(typography, dict) or len(typography) < 2:
        return RefactoringUiScore(
            principle=principle,
            score=0.0,
            violations=[
                RefactoringUiViolation(
                    principle=principle,
                    rule="min_two_distinct_sizes",
                    message="Typography scale must contain at least two distinct sizes.",
                    path="fontSize",
                )
            ],
        )

    sizes_px: list[float] = []
    for name, token in typography.items():
        value = _extract_typography_value(token, "fontSize")
        if value:
            sizes_px.append(value)

    if len(sizes_px) < 2:
        return RefactoringUiScore(
            principle=principle,
            score=0.0,
            violations=[
                RefactoringUiViolation(
                    principle=principle,
                    rule="resolvable_sizes",
                    message="Could not resolve at least two font sizes from fontSize tokens.",
                    path="fontSize",
                )
            ],
        )

    sizes_px = sorted(set(sizes_px))
    ratios = [sizes_px[i + 1] / sizes_px[i] for i in range(len(sizes_px) - 1)]
    # Refactoring UI recommends noticeable jumps; ratios close to 1.0 are slop.
    weak_ratios = [r for r in ratios if r < 1.2]
    score = 1.0 - (len(weak_ratios) / len(ratios))

    violations: list[RefactoringUiViolation] = []
    if weak_ratios:
        violations.append(
            RefactoringUiViolation(
                principle=principle,
                rule="intentional_jumps",
                message=f"Adjacent type sizes are too close (ratios {weak_ratios}). Increase contrast to guide hierarchy.",
                path="fontSize",
            )
        )

    return RefactoringUiScore(principle=principle, score=round(score, 2), violations=violations)


# ---------------------------------------------------------------------------
# 2. Real color palette (semantic, not gray-on-white + one accent)
# ---------------------------------------------------------------------------

REQUIRED_SEMANTIC_ROLES: tuple[str, ...] = (
    "primary",
    "background",
    "surface",
    "text",
    "border",
    "accent",
    "muted",
    "danger",
    "success",
    "warning",
)


def palette_semantic_score(tokens: dict[str, Any]) -> RefactoringUiScore:
    """A full palette has semantic roles, not just primary/secondary/gray."""

    principle = "palette_semantic"
    colors = tokens.get("color", {})
    if not isinstance(colors, dict):
        return RefactoringUiScore(
            principle=principle,
            score=0.0,
            violations=[
                RefactoringUiViolation(
                    principle=principle,
                    rule="color_section_exists",
                    message="No 'color' token section found.",
                    path="color",
                )
            ],
        )

    missing = [role for role in REQUIRED_SEMANTIC_ROLES if role not in colors]
    score = 1.0 - (len(missing) / len(REQUIRED_SEMANTIC_ROLES))

    violations: list[RefactoringUiViolation] = []
    if missing:
        violations.append(
            RefactoringUiViolation(
                principle=principle,
                rule="semantic_roles_present",
                message=f"Missing semantic color roles: {', '.join(missing)}.",
                path="color",
            )
        )

    # Detect flat gray on pure white background.
    bg = _color_value(colors.get("background"))
    text = _color_value(colors.get("text"))
    muted = _color_value(colors.get("muted"))

    if bg and bg.upper() == "#FFFFFF" and text and _is_flat_gray(text):
        violations.append(
            RefactoringUiViolation(
                principle=principle,
                rule="no_flat_gray_on_white",
                message=f"Flat gray text ({text}) on pure white background creates low-energy contrast.",
                path="color.text",
            )
        )
        score = max(0.0, score - 0.25)

    if muted and _is_flat_gray(muted):
        violations.append(
            RefactoringUiViolation(
                principle=principle,
                rule="no_flat_muted",
                message=f"Muted color ({muted}) is flat gray; shift toward warm/cool off-white.",
                path="color.muted",
            )
        )
        score = max(0.0, score - 0.15)

    return RefactoringUiScore(principle=principle, score=round(score, 2), violations=violations)


# ---------------------------------------------------------------------------
# 3. Shadows with intent (different shadows per elevation level)
# ---------------------------------------------------------------------------


def shadow_elevation_score(tokens: dict[str, Any]) -> RefactoringUiScore:
    """Shadows should differ by elevation; one shadow everywhere is generic."""

    principle = "shadow_elevation"
    shadows = tokens.get("shadow", {})
    if not isinstance(shadows, dict) or not shadows:
        # No shadows is acceptable but not ideal for layered UI.
        return RefactoringUiScore(principle=principle, score=0.8, violations=[])

    values = [
        token.get("$value", "") if isinstance(token, dict) else str(token)
        for token in shadows.values()
    ]
    unique = list(dict.fromkeys(values))

    if len(unique) == 1 and len(values) > 1:
        return RefactoringUiScore(
            principle=principle,
            score=0.0,
            violations=[
                RefactoringUiViolation(
                    principle=principle,
                    rule="distinct_elevation_shadows",
                    message="All shadow tokens share the same value; shadows must vary by elevation.",
                    path="shadow",
                )
            ],
        )

    # Generic Tailwind-style shadows are slop.
    generic_patterns = [
        r"0\s+4px\s+6px",
        r"0\s+10px\s+15px",
        r"0\s+20px\s+25px",
        r"shadow-md",
        r"shadow-lg",
    ]
    violations: list[RefactoringUiViolation] = []
    for name, value in zip(shadows.keys(), values):
        if any(re.search(p, value, re.IGNORECASE) for p in generic_patterns):
            violations.append(
                RefactoringUiViolation(
                    principle=principle,
                    rule="no_generic_shadows",
                    message=f"Shadow '{name}' uses generic Tailwind shadow value.",
                    path=f"shadow.{name}",
                )
            )

    score = 1.0 - (len(violations) / max(len(values), 1)) * 0.5
    return RefactoringUiScore(principle=principle, score=round(max(score, 0.0), 2), violations=violations)


# ---------------------------------------------------------------------------
# 4. Spacing with rhythm (non-uniform, intentional scale)
# ---------------------------------------------------------------------------


def spacing_rhythm_score(tokens: dict[str, Any]) -> RefactoringUiScore:
    """Spacing must form a rhythmic scale, not repeat the same increment."""

    principle = "spacing_rhythm"
    spacing = tokens.get("spacing", {})
    if not isinstance(spacing, dict) or len(spacing) < 3:
        return RefactoringUiScore(
            principle=principle,
            score=0.0,
            violations=[
                RefactoringUiViolation(
                    principle=principle,
                    rule="min_three_levels",
                    message="Spacing scale needs at least three distinct levels.",
                    path="spacing",
                )
            ],
        )

    values_px = [
        _dimension_px(token)
        for token in spacing.values()
        if isinstance(token, dict)
    ]
    if len(values_px) < 3:
        return RefactoringUiScore(
            principle=principle,
            score=0.0,
            violations=[
                RefactoringUiViolation(
                    principle=principle,
                    rule="resolvable_dimensions",
                    message="Could not resolve at least three spacing dimensions.",
                    path="spacing",
                )
            ],
        )

    values_px = sorted(set(values_px))
    diffs = [values_px[i + 1] - values_px[i] for i in range(len(values_px) - 1)]
    unique_diffs = len(set(round(d, 1) for d in diffs))

    if unique_diffs <= 1:
        return RefactoringUiScore(
            principle=principle,
            score=0.0,
            violations=[
                RefactoringUiViolation(
                    principle=principle,
                    rule="non_linear_scale",
                    message=f"Spacing increments are uniform ({diffs}); use a rhythmic non-linear scale.",
                    path="spacing",
                )
            ],
        )

    # Outer spacing should grow faster than inner (anti-slop rule #15).
    if diffs and sorted(diffs) == diffs and len(diffs) >= 2:
        # Already accelerating.
        score = 1.0
    else:
        score = 0.85

    return RefactoringUiScore(principle=principle, score=round(score, 2), violations=[])


# ---------------------------------------------------------------------------
# 5. Typography with character (pairing strategy, no one font everywhere)
# ---------------------------------------------------------------------------


def type_pairing_score(tokens: dict[str, Any]) -> RefactoringUiScore:
    """Real type pairing uses 2–4 roles; one font everywhere or forbidden fonts fail."""

    principle = "type_pairing"
    fonts = tokens.get("fontFamily", {})
    if not isinstance(fonts, dict) or len(fonts) < 2:
        return RefactoringUiScore(
            principle=principle,
            score=0.0,
            violations=[
                RefactoringUiViolation(
                    principle=principle,
                    rule="min_two_roles",
                    message="Use at least two fontFamily roles (display, body, mono, etc.).",
                    path="fontFamily",
                )
            ],
        )

    forbidden = {f.lower() for f in DEFAULT_FORBIDDEN_FONTS}

    hard_violations: list[RefactoringUiViolation] = []
    warnings: list[RefactoringUiViolation] = []
    first_families: list[str] = []
    for role, token in fonts.items():
        stack = token.get("$value", "") if isinstance(token, dict) else str(token)
        families = [f.strip().strip("'\"") for f in stack.split(",")]
        if families:
            first_families.append(families[0])
        for family in families:
            clean = family.lower()
            if clean in forbidden:
                hard_violations.append(
                    RefactoringUiViolation(
                        principle=principle,
                        rule="forbidden_font",
                        message=f"Font '{family}' is forbidden.",
                        path=f"fontFamily.{role}",
                    )
                )

    unique_first = list(dict.fromkeys(f.lower() for f in first_families))
    if len(unique_first) == 1 and len(fonts) > 1:
        hard_violations.append(
            RefactoringUiViolation(
                principle=principle,
                rule="distinct_pairing",
                message="All font roles resolve to the same first font; pair distinct typefaces.",
                path="fontFamily",
            )
        )

    # Forbidden fonts and missing pairing are hard failures. Any forbidden font
    # drops the score below the 0.7 gate so the pipeline cannot proceed.
    if any(v.rule == "forbidden_font" for v in hard_violations):
        score = 0.0
    else:
        score = 1.0 - min(len(hard_violations) * 0.25, 1.0)
    return RefactoringUiScore(
        principle=principle,
        score=round(max(score, 0.0), 2),
        violations=hard_violations + warnings,
    )


# ---------------------------------------------------------------------------
# 6. States are part of the design (hover/focus/active/disabled)
# ---------------------------------------------------------------------------


def state_completeness_score(tokens: dict[str, Any]) -> RefactoringUiScore:
    """Interactive colors need explicit states, not afterthought opacity tweaks."""

    principle = "state_completeness"
    colors = tokens.get("color", {})
    if not isinstance(colors, dict):
        return RefactoringUiScore(principle=principle, score=1.0, violations=[])

    interactive_candidates = ["primary", "accent", "danger", "success"]
    required_states = ("hover", "focus", "active", "disabled")
    violations: list[RefactoringUiViolation] = []

    # States may live inline under a color group or in a separate `states` section.
    standalone_states = tokens.get("states", {})

    for candidate in interactive_candidates:
        if candidate not in colors:
            continue
        token = colors[candidate]
        if not isinstance(token, dict):
            continue
        inline_states = any(state in token for state in required_states)
        standalone = (
            isinstance(standalone_states, dict)
            and candidate in standalone_states
            and isinstance(standalone_states[candidate], dict)
            and any(state in standalone_states[candidate] for state in required_states)
        )
        if not inline_states and not standalone:
            violations.append(
                RefactoringUiViolation(
                    principle=principle,
                    rule="interactive_states_defined",
                    message=f"Interactive color '{candidate}' lacks explicit hover/focus/active/disabled states.",
                    path=f"color.{candidate}",
                )
            )

    # Missing states are a warning, not a hard blocker: many projects define
    # states at the component layer rather than the token layer.
    score = 1.0 - min(len(violations) * 0.1, 0.5)
    return RefactoringUiScore(principle=principle, score=round(max(score, 0.0), 2), violations=violations)


# ---------------------------------------------------------------------------
# Aggregate runner
# ---------------------------------------------------------------------------


def run_all_refactoring_ui_checks(tokens: dict[str, Any]) -> list[RefactoringUiScore]:
    """Run the full Refactoring UI check suite and return per-principle scores."""
    return [
        scale_contrast_score(tokens),
        palette_semantic_score(tokens),
        shadow_elevation_score(tokens),
        spacing_rhythm_score(tokens),
        type_pairing_score(tokens),
        state_completeness_score(tokens),
    ]


def aggregate_score(scores: list[RefactoringUiScore]) -> float:
    """Mean score across all Refactoring UI principles."""
    if not scores:
        return 0.0
    return round(sum(s.score for s in scores) / len(scores), 2)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _extract_typography_value(token: Any, key: str) -> float | None:
    """Extract a numeric px value from a typography token."""
    if not isinstance(token, dict):
        return None
    value = token.get("$value", {})
    if isinstance(value, dict):
        raw = value.get(key, "")
    else:
        raw = value
    match = re.search(r"(\d+(?:\.\d+)?)", str(raw))
    return float(match.group(1)) if match else None


def _dimension_px(token: Any) -> float:
    """Extract numeric px value from a dimension token."""
    if not isinstance(token, dict):
        return 0.0
    raw = token.get("$value", "0px")
    match = re.search(r"(\d+(?:\.\d+)?)", str(raw))
    return float(match.group(1)) if match else 0.0


def _color_value(token: Any) -> str | None:
    if not isinstance(token, dict):
        return None
    value = token.get("$value")
    return str(value) if isinstance(value, str) else None


def _is_flat_gray(value: str) -> bool:
    """Detect flat, uninspiring mid-gray colors such as #777777 or #808080.

    Slightly warm/cool grays like #6B6B75 are intentionally allowed because
    they carry enough temperature to avoid the flat-gray-on-white slop trap.
    """
    hex_val = value.strip().lstrip("#").upper()
    if len(hex_val) == 3:
        hex_val = "".join(c * 2 for c in hex_val)
    if len(hex_val) != 6:
        return False
    try:
        r = int(hex_val[0:2], 16)
        g = int(hex_val[2:4], 16)
        b = int(hex_val[4:6], 16)
    except ValueError:
        return False
    # Gray-ish only if channels are nearly identical and value sits in the
    # stale mid-gray band that Refactoring UI warns against.
    if max(r, g, b) - min(r, g, b) > 5:
        return False
    return 102 <= r <= 153
