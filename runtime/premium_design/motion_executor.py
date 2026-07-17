"""Motion executor: materialize DTCG motion tokens into code.

Outputs three representations so callers can pick the one that fits their stack:
- Framer Motion / motion.dev JSON variants
- CSS transitions keyed by token name
- Tailwind-compatible custom properties extension

Respects prefers-reduced-motion and never emits width/height/top/left/margin/padding
animations.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class MotionExecutorResult:
    ok: bool = True
    motion_level: float = 0.0
    allowed_properties: list[str] = field(default_factory=list)
    framer_motion_variants: dict[str, Any] = field(default_factory=dict)
    css_transitions: dict[str, str] = field(default_factory=dict)
    tailwind_extend: dict[str, Any] = field(default_factory=dict)
    violations: list[dict[str, Any]] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


class MotionExecutor:
    """Convert DTCG motion tokens into compositor-friendly code."""

    FORBIDDEN_LAYOUT_PROPERTIES: tuple[str, ...] = (
        "width",
        "height",
        "margin",
        "padding",
        "top",
        "left",
        "right",
        "bottom",
    )

    def __init__(self, tokens: dict[str, Any] | None = None):
        self.tokens = tokens or {}

    def execute(self) -> MotionExecutorResult:
        motion = self.tokens.get("motion", {})
        if not isinstance(motion, dict):
            return MotionExecutorResult(
                ok=False,
                violations=[{"rule": "missing_motion_section", "message": "No motion tokens found"}],
            )

        allowed = motion.get("allowed_properties", {}).get("$value", [])
        if not isinstance(allowed, list):
            allowed = []

        duration_tokens = motion.get("duration", {})
        easing_tokens = motion.get("easing", {})

        durations = self._extract_durations(duration_tokens)
        easings = self._extract_easings(easing_tokens)

        violations: list[dict[str, Any]] = []
        for prop in self.FORBIDDEN_LAYOUT_PROPERTIES:
            if prop in allowed:
                violations.append(
                    {"rule": "layout_animation", "property": prop, "message": f"Forbidden property '{prop}' in allowed_properties"}
                )

        result = MotionExecutorResult(
            motion_level=self._infer_motion_level(durations),
            allowed_properties=allowed,
            framer_motion_variants={},
            css_transitions={},
            tailwind_extend={},
            violations=violations,
        )

        if violations:
            result.ok = False
            return result

        product_easing = easings.get("product", "cubic-bezier(0.16, 1, 0.3, 1)")
        exit_easing = easings.get("exit", "cubic-bezier(0.4, 0, 1, 1)")

        # Framer Motion variants: fade, slide-up, scale, focus
        base = durations.get("base", "0.25s").replace("s", "")
        try:
            base_seconds = float(base)
        except ValueError:
            base_seconds = 0.25

        result.framer_motion_variants = {
            "fade": {
                "initial": {"opacity": 0},
                "animate": {"opacity": 1},
                "exit": {"opacity": 0},
                "transition": {"duration": base_seconds, "ease": self._css_to_framer_ease(product_easing)},
            },
            "slideUp": {
                "initial": {"opacity": 0, "y": 24},
                "animate": {"opacity": 1, "y": 0},
                "exit": {"opacity": 0, "y": -12},
                "transition": {"duration": base_seconds, "ease": self._css_to_framer_ease(product_easing)},
            },
            "scaleIn": {
                "initial": {"opacity": 0, "scale": 0.96},
                "animate": {"opacity": 1, "scale": 1},
                "exit": {"opacity": 0, "scale": 0.98},
                "transition": {"duration": base_seconds, "ease": self._css_to_framer_ease(product_easing)},
            },
        }

        # CSS transitions by token name
        for name, duration in durations.items():
            result.css_transitions[name] = f"{duration} {product_easing}"
        result.css_transitions["exit"] = f"{durations.get('fast', '0.15s')} {exit_easing}"

        # Tailwind extend for transitionDuration and transitionTimingFunction
        result.tailwind_extend = {
            "transitionDuration": {name: duration for name, duration in durations.items()},
            "transitionTimingFunction": {
                "product": product_easing,
                "exit": exit_easing,
            },
        }

        result.notes.append(f"generated {len(result.framer_motion_variants)} framer variants")
        result.notes.append(f"allowed_properties={allowed}")
        return result

    def write_artifacts(
        self,
        result: MotionExecutorResult,
        target_dir: Path | str,
        prefix: str = "motion",
    ) -> dict[str, Path]:
        """Write motion.ts (Framer), motion.css, and tailwind-motion-patch.json."""
        target = Path(target_dir).resolve()
        target.mkdir(parents=True, exist_ok=True)
        paths: dict[str, Path] = {}

        fm_path = target / f"{prefix}.ts"
        fm_path.write_text(self._render_framer_ts(result), encoding="utf-8")
        paths["framer_motion"] = fm_path

        css_path = target / f"{prefix}.css"
        css_path.write_text(self._render_css(result), encoding="utf-8")
        paths["css"] = css_path

        tw_path = target / f"{prefix}-tailwind-extend.json"
        tw_path.write_text(json.dumps(result.tailwind_extend, indent=2, ensure_ascii=False), encoding="utf-8")
        paths["tailwind_extend"] = tw_path

        return paths

    def _extract_durations(self, duration_tokens: Any) -> dict[str, str]:
        if not isinstance(duration_tokens, dict):
            return {}
        out: dict[str, str] = {}
        for name, token in duration_tokens.items():
            if isinstance(token, dict) and token.get("$type") == "duration":
                out[name] = str(token.get("$value", ""))
        return out

    def _extract_easings(self, easing_tokens: Any) -> dict[str, str]:
        if not isinstance(easing_tokens, dict):
            return {}
        out: dict[str, str] = {}
        for name, token in easing_tokens.items():
            if not isinstance(token, dict):
                continue
            value = token.get("$value")
            if token.get("$type") == "cubicBezier" and isinstance(value, list) and len(value) == 4:
                out[name] = f"cubic-bezier({', '.join(str(v) for v in value)})"
            elif isinstance(value, str):
                out[name] = value
        return out

    def _infer_motion_level(self, durations: dict[str, str]) -> float:
        base = durations.get("base", "0.25s").replace("s", "")
        try:
            return round((float(base) - 0.15) / 0.5, 2)
        except ValueError:
            return 0.0

    def _css_to_framer_ease(self, css_ease: str) -> list[float] | str:
        """Convert CSS cubic-bezier(...) to Framer Motion [x1, y1, x2, y2]."""
        match = css_ease.strip().lower()
        if match.startswith("cubic-bezier("):
            inner = match[len("cubic-bezier(") :].rstrip(")")
            try:
                values = [float(v.strip()) for v in inner.split(",")]
                if len(values) == 4:
                    return values
            except ValueError:
                pass
        return css_ease

    def _render_framer_ts(self, result: MotionExecutorResult) -> str:
        lines = [
            "// Generated by premium-design motion executor from DTCG tokens.",
            "// Respects prefers-reduced-motion.",
            "",
            'import { Variants } from "framer-motion";',
            "",
            "const prefersReducedMotion =",
            '  typeof window !== "undefined" &&',
            '  window.matchMedia("(prefers-reduced-motion: reduce)").matches;',
            "",
        ]
        for name, variant in result.framer_motion_variants.items():
            lines.append(f"export const {name}Variants: Variants = {json.dumps(variant, indent=2)};")
            lines.append("")

        lines.extend([
            "export function safeTransition(variants: Variants): Variants {",
            "  if (prefersReducedMotion) {",
            "    return { initial: {}, animate: {}, exit: {} };",
            "  }",
            "  return variants;",
            "}",
            "",
        ])
        return "\n".join(lines)

    def _render_css(self, result: MotionExecutorResult) -> str:
        lines = [
            "/* Generated by premium-design motion executor from DTCG tokens. */",
            "/* Allowed animated properties: " + ", ".join(result.allowed_properties) + " */",
            "",
            "@media (prefers-reduced-motion: no-preference) {",
        ]
        for name, transition in result.css_transitions.items():
            lines.append(f"  .transition-{name.replace('_', '-').lower()} {{ transition: {transition}; }}")
        lines.extend(["}", ""])
        return "\n".join(lines)
