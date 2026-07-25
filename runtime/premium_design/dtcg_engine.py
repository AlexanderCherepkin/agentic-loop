"""DTCG (W3C Design Tokens Community Group) token generator for premium design.

Converts a textual brief + variance/density/motion knobs into a structured,
anti-slop design-token document. Output follows DTCG v9 draft conventions:
every token carries ``$value`` and ``$type``.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .config import DEFAULT_ALLOWED_FONTS, DEFAULT_FORBIDDEN_FONTS, PremiumDesignConfig
from .motion_executor import MotionExecutor
from .refactoring_ui_rules import aggregate_score, run_all_refactoring_ui_checks


# ---------------------------------------------------------------------------
# DTCG token primitives
# ---------------------------------------------------------------------------

def _color(value: str) -> dict[str, str]:
    return {"$value": value, "$type": "color"}


def _font_family(value: str) -> dict[str, str]:
    return {"$value": value, "$type": "fontFamily"}


def _dimension(value: str | float | int) -> dict[str, str]:
    return {"$value": str(value), "$type": "dimension"}


def _shadow(value: str) -> dict[str, str]:
    return {"$value": value, "$type": "shadow"}


def _duration(value: str | float | int) -> dict[str, str]:
    return {"$value": str(value), "$type": "duration"}


def _cubic_bezier(value: list[float]) -> dict[str, Any]:
    return {"$value": value, "$type": "cubicBezier"}


# ---------------------------------------------------------------------------
# Anti-slop presets
# ---------------------------------------------------------------------------

DIRECTION_PRESETS: dict[str, dict[str, Any]] = {
    "editorial": {
        "fonts": {
            "display": _font_family("'Playfair Display', 'Tiempos Headline', serif"),
            "body": _font_family("'Plus Jakarta Sans', 'Suisse Int\\'l', sans-serif"),
            "mono": _font_family("'JetBrains Mono', 'Fira Code', monospace"),
        },
        "colors": {
            "primary": _color("#1A1A17"),
            "background": _color("#FCFCF9"),
            "surface": _color("#FFFFFF"),
            "text": _color("#1A1A17"),
            "border": _color("#E8E8E6"),
            "accent": _color("#8B3A3A"),
            "muted": _color("#73736E"),
        },
        "shadow": _shadow("0 24px 48px -12px rgba(26, 26, 23, 0.08)"),
        "motion_curve": _cubic_bezier([0.16, 1, 0.3, 1]),
    },
    "swiss_minimal": {
        "fonts": {
            "display": _font_family("'Helvetica Now Display', 'Neue Haas Grotesk', sans-serif"),
            "body": _font_family("'Geist Mono', 'SF Mono', monospace"),
            "mono": _font_family("'Geist Mono', monospace"),
        },
        "colors": {
            "primary": _color("#0A0A0B"),
            "background": _color("#FAFAFA"),
            "surface": _color("#FFFFFF"),
            "text": _color("#0A0A0B"),
            "border": _color("#E5E5E8"),
            "accent": _color("#0055FF"),
            "muted": _color("#6B6B75"),
        },
        "shadow": _shadow("0 4px 24px -4px rgba(10, 10, 11, 0.04)"),
        "motion_curve": _cubic_bezier([0.25, 0.1, 0.25, 1.0]),
    },
    "minimal_tech": {
        "fonts": {
            "display": _font_family("'Clash Display', 'Nextron', sans-serif"),
            "body": _font_family("'Satoshi', 'Adisan Richard', sans-serif"),
            "mono": _font_family("'JetBrains Mono', 'SF Mono', monospace"),
        },
        "colors": {
            "primary": _color("#E2E8F0"),
            "background": _color("#020617"),
            "surface": _color("#0F172A"),
            "text": _color("#E2E8F0"),
            "border": _color("#1E293B"),
            "accent": _color("#10B981"),
            "muted": _color("#94A3B8"),
        },
        "shadow": _shadow("0 0 40px -10px rgba(16, 185, 129, 0.15)"),
        "motion_curve": _cubic_bezier([0.33, 1, 0.68, 1]),
    },
    "brutalist": {
        "fonts": {
            "display": _font_family("'Druk Wide', 'Thunder', 'Arial Black', sans-serif"),
            "body": _font_family("'Neue Montreal', 'Helvetica Now', sans-serif"),
            "mono": _font_family("'SF Mono', 'Inconsolata', monospace"),
        },
        "colors": {
            "primary": _color("#000000"),
            "background": _color("#FFFFFF"),
            "surface": _color("#F3F3F3"),
            "text": _color("#000000"),
            "border": _color("#E5E5E5"),
            "accent": _color("#FF2A00"),
            "muted": _color("#333333"),
        },
        "shadow": _shadow("4px 4px 0px 0px #000000"),
        "motion_curve": _cubic_bezier([0.87, 0, 0.13, 1]),
    },
    "retro_futuristic": {
        "fonts": {
            "display": _font_family("'Nextron', 'Neuroxa', 'Orbitron', sans-serif"),
            "body": _font_family("'Satoshi', 'Adisan Richard', sans-serif"),
            "mono": _font_family("'Geist Mono', 'Fira Code', monospace"),
        },
        "colors": {
            "primary": _color("#F0F0FF"),
            "background": _color("#050510"),
            "surface": _color("#0A0A1A"),
            "text": _color("#F0F0FF"),
            "border": _color("#1A1A2E"),
            "accent": _color("#00F0FF"),
            "muted": _color("#8A8AB0"),
        },
        "shadow": _shadow("0 0 60px -12px rgba(0, 240, 255, 0.25)"),
        "motion_curve": _cubic_bezier([0.22, 1, 0.36, 1]),
    },
}


# ---------------------------------------------------------------------------
# Brief analyzer
# ---------------------------------------------------------------------------

_TECH_KEYWORDS = (
    "saas", "код", "дашборд", "dashboard", "api", "tech", "ai", "мл",
    "machine learning", "платформа", "platform", "data",
)
_EDITORIAL_KEYWORDS = (
    "медиа", "фэшн", "архитектура", "блог", "статья", "журнал", "editorial",
    "fashion", "architecture", "magazine", "publication",
)
_BRUTALIST_KEYWORDS = (
    "брутализм", "brutalist", "raw", "агрессивно", "контраст", "постер",
)
_RETRO_KEYWORDS = (
    "ретро", "retro", "футуризм", "futuristic", "cyber", "неон", "neon",
    "sci-fi", "темная тема", "dark mode",
)


def _analyze_direction(brief: str) -> str:
    """Map a brief to one of the premium directions."""
    text = brief.lower()

    if any(kw in text for kw in _RETRO_KEYWORDS):
        return "retro_futuristic"
    if any(kw in text for kw in _BRUTALIST_KEYWORDS):
        return "brutalist"
    if any(kw in text for kw in _EDITORIAL_KEYWORDS):
        return "editorial"
    if any(kw in text for kw in _TECH_KEYWORDS):
        return "minimal_tech"

    return "swiss_minimal"


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------

@dataclass
class DtcgGenerationResult:
    direction: str
    tokens: dict[str, Any]
    tailwind_config_patch: dict[str, Any] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)
    refactoring_ui_scores: list[dict[str, Any]] = field(default_factory=list)
    refactoring_ui_aggregate: float = 0.0
    refactoring_ui_passed: bool = True


class DtcgTokenEngine:
    """Generate DTCG design tokens from a textual brief and variance knobs."""

    def __init__(
        self,
        config: PremiumDesignConfig | None = None,
        allowed_fonts: list[str] | None = None,
        forbidden_fonts: list[str] | None = None,
    ):
        self.config = config or PremiumDesignConfig()
        self.allowed_fonts = allowed_fonts or DEFAULT_ALLOWED_FONTS
        self.forbidden_fonts = forbidden_fonts or DEFAULT_FORBIDDEN_FONTS

    def generate(
        self,
        brief: str,
        *,
        variance: float = 0.5,
        density: float = 0.0,
        motion: float = 0.0,
        direction_override: str | None = None,
    ) -> DtcgGenerationResult:
        """Return DTCG tokens + Tailwind patch for the given brief."""

        if not isinstance(brief, str) or not brief.strip():
            raise ValueError("brief must be a non-empty string")

        direction = direction_override or _analyze_direction(brief)
        preset = DIRECTION_PRESETS.get(direction, DIRECTION_PRESETS["swiss_minimal"])

        notes: list[str] = [f"direction={direction} inferred from brief"]
        if direction_override:
            notes.append("direction overridden by caller")

        # Ensure no forbidden font leaked into the chosen fallback stack.
        sanitized_fonts = self._sanitize_fonts(preset["fonts"], direction)

        # Dynamic spacing scale: anti-slop rule #15 — outer spacing grows faster.
        base_spacing = 4 * (1 + variance * 0.5)
        spacing_scale = self._build_spacing_scale(base_spacing, density)

        # Typography scale with intentional tracking/leading variety.
        typography_scale = self._build_typography_scale(density)

        # Motion scale constrained to transform/opacity-friendly properties.
        motion_scale = self._build_motion_scale(motion, preset["motion_curve"])

        # Border radius: inner < outer per anti-slop rule #22.
        radius_scale = self._build_radius_scale(variance)

        tokens: dict[str, Any] = {
            "$description": f"Anti-Slop design tokens for direction: {direction}",
            "direction": {"$value": direction, "$type": "string"},
            "anti_slop": {
                "version": {"$value": "1.0.0", "$type": "string"},
                "forbidden_fonts": {
                    "$value": self.forbidden_fonts,
                    "$type": "stringArray",
                },
                "allowed_properties": {
                    "$value": ["transform", "opacity", "filter", "clip-path"],
                    "$type": "stringArray",
                },
            },
            "color": {
                **preset["colors"],
                "warning": _color("#D97706"),
                "success": _color("#059669"),
                "danger": _color("#DC2626"),
            },
            "fontFamily": sanitized_fonts,
            "fontSize": typography_scale,
            "spacing": spacing_scale,
            "shadow": {
                "soft": preset["shadow"],
                "hard": _shadow("0 1px 2px 0 rgba(0, 0, 0, 0.12)"),
            },
            "motion": motion_scale,
            "borderRadius": radius_scale,
            "states": self._build_state_colors(preset["colors"]),
        }

        # Refactoring UI hard gate: deterministic checks before handoff.
        refactoring_scores = run_all_refactoring_ui_checks(tokens)
        refactoring_aggregate = aggregate_score(refactoring_scores)
        threshold = self.config.refactoring_ui_threshold
        passed = refactoring_aggregate >= threshold

        if not passed and self.config.strict_refactoring_ui:
            failed = [
                f"{s.principle}={s.score}"
                for s in refactoring_scores
                if s.score < threshold
            ]
            raise ValueError(
                f"Refactoring UI gate failed (aggregate={refactoring_aggregate}, "
                f"threshold={threshold}). Low scores: {', '.join(failed)}"
            )

        # Embed scores in tokens for audit trail.
        tokens["refactoring_ui_scores"] = {
            "aggregate": refactoring_aggregate,
            "threshold": threshold,
            "passed": passed,
            "principles": [
                {
                    "principle": s.principle,
                    "score": s.score,
                    "violations": [
                        {"rule": v.rule, "message": v.message, "path": v.path}
                        for v in s.violations
                    ],
                }
                for s in refactoring_scores
            ],
        }

        tailwind_patch = self._to_tailwind_patch(tokens)
        notes.append(f"refactoring_ui_aggregate={refactoring_aggregate} (threshold={threshold})")

        return DtcgGenerationResult(
            direction=direction,
            tokens=tokens,
            tailwind_config_patch=tailwind_patch,
            notes=notes,
            refactoring_ui_scores=tokens["refactoring_ui_scores"]["principles"],
            refactoring_ui_aggregate=refactoring_aggregate,
            refactoring_ui_passed=passed,
        )

    def _sanitize_fonts(
        self, fonts: dict[str, Any], direction: str
    ) -> dict[str, Any]:
        """Replace forbidden fonts in fallback stacks with allowed alternatives."""
        cleaned: dict[str, Any] = {}
        for role, token in fonts.items():
            stack = token["$value"]
            families = [f.strip().strip("'\"") for f in stack.split(",")]
            safe_families: list[str] = []
            for family in families:
                if family.lower() in {f.lower() for f in self.forbidden_fonts}:
                    # Replace with a safe allowed font that is not forbidden.
                    replacement = self._pick_allowed_replacement(family, direction)
                    safe_families.append(replacement)
                else:
                    safe_families.append(family)
            # Deduplicate while preserving order.
            seen: set[str] = set()
            unique: list[str] = []
            for f in safe_families:
                if f.lower() not in seen:
                    seen.add(f.lower())
                    unique.append(f)
            cleaned[role] = _font_family(
                ", ".join(f"'{f}'" if " " in f else f for f in unique)
            )
        return cleaned

    def _pick_allowed_replacement(self, forbidden_family: str, direction: str) -> str:
        """Return an allowed font matching the direction as closely as possible."""
        fallback_map: dict[str, str] = {
            "editorial": "Playfair Display",
            "swiss_minimal": "Neue Haas Grotesk",
            "minimal_tech": "Nextron",
            "brutalist": "Druk Wide",
            "retro_futuristic": "Neuroxa",
        }
        preferred = fallback_map.get(direction, "Plus Jakarta Sans")
        allowed_lower = {f.lower() for f in self.allowed_fonts}
        if preferred.lower() in allowed_lower:
            return preferred
        if self.allowed_fonts:
            return self.allowed_fonts[0]
        return "system-ui"

    def _build_spacing_scale(self, base: float, density: float) -> dict[str, Any]:
        """Build a non-generic spacing scale (anti-slop rule #15)."""
        # Low density → bigger jumps; high density → tighter increments.
        multiplier = 1.0 + (1.0 - density) * 0.5
        return {
            "xs": _dimension(f"{base:.0f}px"),
            "sm": _dimension(f"{base * 2:.0f}px"),
            "md": _dimension(f"{base * 3:.0f}px"),
            "lg": _dimension(f"{base * 5 * multiplier:.0f}px"),
            "xl": _dimension(f"{base * 8 * multiplier:.0f}px"),
            "2xl": _dimension(f"{base * 13 * multiplier:.0f}px"),
        }

    def _build_typography_scale(self, density: float) -> dict[str, Any]:
        """Return a fluid-ready type scale with tight display leading."""
        # Density 0 → bigger display sizes; density 1 → compact dashboard sizes.
        sizes = {
            "xs": [12, 1.5],
            "sm": [14, 1.5],
            "base": [16, 1.6],
            "lg": [20, 1.45],
            "xl": [24, 1.25],
            "2xl": [32 - int(density * 4), 1.1],
            "3xl": [48 - int(density * 8), 1.0],
            "4xl": [72 - int(density * 16), 0.95],
        }
        return {
            name: {
                "$value": {
                    "fontSize": f"{size}px",
                    "lineHeight": str(line),
                    "letterSpacing": "-0.02em" if name in ("3xl", "4xl") else "0em",
                },
                "$type": "typography",
            }
            for name, (size, line) in sizes.items()
        }

    def _build_motion_scale(
        self, motion: float, curve_token: dict[str, Any]
    ) -> dict[str, Any]:
        """Build a motion scale that respects prefers-reduced-motion."""
        return {
            "disabled": {"$value": True, "$type": "boolean"},
            "duration": {
                "fast": _duration(f"{0.15 + motion * 0.05:.2f}s"),
                "base": _duration(f"{0.25 + motion * 0.15:.2f}s"),
                "slow": _duration(f"{0.45 + motion * 0.25:.2f}s"),
            },
            "easing": {
                "product": curve_token,
                "exit": _cubic_bezier([0.4, 0, 1, 1]),
            },
            "allowed_properties": {
                "$value": ["transform", "opacity", "filter", "clip-path"],
                "$type": "stringArray",
            },
        }

    def _build_radius_scale(self, variance: float) -> dict[str, Any]:
        """Inner radius must be smaller than outer (anti-slop rule #22)."""
        base = 4 + int(variance * 8)  # 4–12 px
        return {
            "inner": _dimension(f"{max(base // 2, 2)}px"),
            "base": _dimension(f"{base}px"),
            "outer": _dimension(f"{base * 2}px"),
            "pill": _dimension("9999px"),
        }

    def _build_state_colors(self, colors: dict[str, Any]) -> dict[str, Any]:
        """Generate explicit interactive-state tokens for premium Refactoring UI compliance."""
        primary = _color_value(colors.get("primary")) or "#0A0A0B"
        accent = _color_value(colors.get("accent")) or "#0055FF"
        muted = _color_value(colors.get("muted")) or "#6B6B75"
        surface = _color_value(colors.get("surface")) or "#FFFFFF"
        return {
            "primary": {
                "hover": _color(_adjust_hex(primary, 0.15)),
                "focus": _color(accent),
                "active": _color(_adjust_hex(primary, -0.15)),
                "disabled": _color(muted),
            },
            "accent": {
                "hover": _color(_adjust_hex(accent, 0.15)),
                "focus": _color(surface),
                "active": _color(_adjust_hex(accent, -0.15)),
                "disabled": _color(muted),
            },
        }

    def _to_tailwind_patch(self, tokens: dict[str, Any]) -> dict[str, Any]:
        """Flatten DTCG tokens into a Tailwind CSS config patch."""
        patch: dict[str, Any] = {"theme": {"extend": {}}}

        colors = tokens.get("color", {})
        if colors:
            patch["theme"]["extend"]["colors"] = {
                name: token["$value"]
                for name, token in colors.items()
                if token.get("$type") == "color"
            }

        fonts = tokens.get("fontFamily", {})
        if fonts:
            patch["theme"]["extend"]["fontFamily"] = {
                name: token["$value"]
                for name, token in fonts.items()
                if token.get("$type") == "fontFamily"
            }

        spacing = tokens.get("spacing", {})
        if spacing:
            patch["theme"]["extend"]["spacing"] = {
                name: token["$value"]
                for name, token in spacing.items()
                if token.get("$type") == "dimension"
            }

        shadows = tokens.get("shadow", {})
        if shadows:
            patch["theme"]["extend"]["boxShadow"] = {
                name: token["$value"]
                for name, token in shadows.items()
                if token.get("$type") == "shadow"
            }

        radius = tokens.get("borderRadius", {})
        if radius:
            patch["theme"]["extend"]["borderRadius"] = {
                name: token["$value"]
                for name, token in radius.items()
                if token.get("$type") == "dimension"
            }

        return patch

    def generate_motion_artifacts(
        self,
        tokens: dict[str, Any],
        target_dir: Path | str,
        prefix: str = "motion",
    ) -> dict[str, Path]:
        """Materialize DTCG motion tokens into Framer Motion, CSS and Tailwind code."""
        executor = MotionExecutor(tokens)
        result = executor.execute()
        if not result.ok:
            raise ValueError(
                f"Motion executor failed: {result.violations}"
            )
        return executor.write_artifacts(result, target_dir, prefix=prefix)

    def write_artifacts(
        self,
        result: DtcgGenerationResult,
        target_dir: Path | str,
        design_md_content: str | None = None,
        include_motion: bool = True,
    ) -> dict[str, Path]:
        """Write design_tokens.json, optional DESIGN.md and motion code to disk."""
        target = Path(target_dir).resolve()
        target.mkdir(parents=True, exist_ok=True)

        tokens_path = target / "design_tokens.json"
        tokens_path.write_text(
            json.dumps(result.tokens, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

        paths: dict[str, Path] = {"design_tokens": tokens_path}

        if design_md_content:
            design_path = target / "DESIGN.md"
            design_path.write_text(design_md_content, encoding="utf-8")
            paths["design_md"] = design_path

        if include_motion:
            try:
                motion_paths = self.generate_motion_artifacts(result.tokens, target, prefix="motion")
                paths.update(motion_paths)
            except Exception as exc:
                paths["motion_error"] = Path(str(exc))

        return paths


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def detect_slop_tokens(tokens: dict[str, Any]) -> list[dict[str, Any]]:
    """Return a list of slop violations found in DTCG tokens.

    Lightweight deterministic check intended for fast QA before code handoff.
    """
    violations: list[dict[str, Any]] = []

    forbidden = {f.lower() for f in DEFAULT_FORBIDDEN_FONTS}

    fonts_section = tokens.get("fontFamily", {})
    if isinstance(fonts_section, dict):
        for role, token in fonts_section.items():
            value = token.get("$value", "") if isinstance(token, dict) else str(token)
            for family in re.split(r"[,;]", value):
                clean = family.strip().strip("'\"").lower()
                if clean in forbidden:
                    violations.append(
                        {"rule": "forbidden_font", "role": role, "family": clean}
                    )

    colors = tokens.get("color", {})
    if isinstance(colors, dict):
        muted = colors.get("muted", {}).get("$value", "")
        if muted and muted.lower() in ("#666666", "#777777", "#808080", "#888888", "#999999"):
            violations.append({"rule": "flat_gray_on_white", "token": "color.muted"})

        # Decorative gradient blobs inside color tokens.
        gradient_blob_re = re.compile(
            r"(?:radial-gradient\s*\([^)]*ellipse[^)]*\)|linear-gradient\s*\([^)]*deg[^)]*\))",
            re.IGNORECASE,
        )
        for name, token in colors.items():
            value = token.get("$value", "") if isinstance(token, dict) else str(token)
            if gradient_blob_re.search(str(value)):
                violations.append({"rule": "gradient_blob", "token": f"color.{name}"})

    shadows = tokens.get("shadow", {})
    generic_shadows = re.compile(
        r"0\s+4px\s+6px|0\s+8px\s+.*px|0\s+10px\s+15px|0\s+20px\s+25px|shadow-sm|shadow-md|shadow-lg",
        re.IGNORECASE,
    )
    for name, token in shadows.items():
        value = token.get("$value", "") if isinstance(token, dict) else str(token)
        if generic_shadows.search(value):
            violations.append({"rule": "generic_shadow", "token": f"shadow.{name}"})

    spacing = tokens.get("spacing", {})
    if isinstance(spacing, dict) and len(spacing) >= 2:
        values = [
            _token_dimension_px(token)
            for token in spacing.values()
            if isinstance(token, dict)
        ]
        if values and max(values) - min(values) < 24:
            violations.append({"rule": "uniform_padding", "token": "spacing"})

    motion = tokens.get("motion", {})
    if isinstance(motion, dict):
        allowed = motion.get("allowed_properties", {}).get("$value", [])
        for prop in ("width", "height", "margin", "padding", "top", "left"):
            if prop in allowed:
                violations.append({"rule": "layout_animation", "property": prop})

    return violations


def _token_dimension_px(token: dict[str, Any]) -> float:
    """Extract numeric px value from a dimension token."""
    raw = token.get("$value", "0px")
    match = re.search(r"(\d+(?:\.\d+)?)", str(raw))
    return float(match.group(1)) if match else 0.0


def _color_value(token: Any) -> str | None:
    """Extract the hex string from a DTCG color token."""
    if not isinstance(token, dict):
        return None
    value = token.get("$value")
    return str(value) if isinstance(value, str) else None


def _adjust_hex(value: str, factor: float) -> str:
    """Lighten (factor > 0) or darken (factor < 0) a hex color.

    Clamps each channel to [0, 255] and returns a 6-digit hex string.
    """
    hex_val = value.strip().lstrip("#")
    if len(hex_val) == 3:
        hex_val = "".join(c * 2 for c in hex_val)
    if len(hex_val) != 6:
        return value
    try:
        r = int(hex_val[0:2], 16)
        g = int(hex_val[2:4], 16)
        b = int(hex_val[4:6], 16)
    except ValueError:
        return value

    def _blend(channel: int, factor: float) -> int:
        if factor > 0:
            return int(channel + (255 - channel) * factor)
        return int(channel * (1 + factor))

    r = max(0, min(255, _blend(r, factor)))
    g = max(0, min(255, _blend(g, factor)))
    b = max(0, min(255, _blend(b, factor)))
    return f"#{r:02x}{g:02x}{b:02x}"
