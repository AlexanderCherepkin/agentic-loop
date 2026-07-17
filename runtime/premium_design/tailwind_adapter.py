"""Tailwind CSS config adapter for premium DTCG tokens.

Reads a W3C DTCG ``design_tokens.json`` and emits a TypeScript Tailwind config
plus a CSS variables file. This bridges the design-token handoff into actual
utility classes without letting default Tailwind values leak back in.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .dtcg_engine import DEFAULT_ALLOWED_FONTS, DEFAULT_FORBIDDEN_FONTS, detect_slop_tokens


# ---------------------------------------------------------------------------
# DTCG → Tailwind type mapping
# ---------------------------------------------------------------------------

TAILWIND_TOKEN_GROUPS: dict[str, str] = {
    "color": "colors",
    "fontFamily": "fontFamily",
    "fontSize": "fontSize",
    "spacing": "spacing",
    "shadow": "boxShadow",
    "borderRadius": "borderRadius",
    "duration": "transitionDuration",
}


@dataclass
class TailwindAdapterResult:
    tailwind_path: Path | None = None
    css_path: Path | None = None
    violations: list[dict[str, Any]] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.violations


class TailwindConfigAdapter:
    """Convert DTCG tokens into Tailwind v3 configuration and CSS variables."""

    def __init__(
        self,
        tokens: dict[str, Any] | None = None,
        tokens_path: Path | str | None = None,
        forbidden_fonts: list[str] | None = None,
        allowed_fonts: list[str] | None = None,
    ):
        if tokens is not None and tokens_path is not None:
            raise ValueError("Provide either tokens or tokens_path, not both")
        if tokens is None and tokens_path is None:
            raise ValueError("Provide tokens or tokens_path")

        self._tokens = tokens
        self._tokens_path = Path(tokens_path) if tokens_path else None
        self.forbidden_fonts = forbidden_fonts or DEFAULT_FORBIDDEN_FONTS
        self.allowed_fonts = allowed_fonts or DEFAULT_ALLOWED_FONTS

    def _load_tokens(self) -> dict[str, Any]:
        if self._tokens is not None:
            return self._tokens
        path = self._tokens_path
        assert path is not None
        text = path.read_text(encoding="utf-8")
        return json.loads(text)

    def generate(
        self,
        *,
        tailwind_output: Path | str | None = None,
        css_output: Path | str | None = None,
        patch_existing: bool = False,
        strict: bool = True,
    ) -> TailwindAdapterResult:
        """Generate Tailwind config and CSS variables from DTCG tokens."""

        tokens = self._load_tokens()
        result = TailwindAdapterResult()

        # Anti-slop gate
        result.violations = detect_slop_tokens(tokens)
        if result.violations:
            result.notes.append(
                f"detected {len(result.violations)} slop violation(s) in tokens"
            )
            if strict:
                return result

        css_vars = self._build_css_variables(tokens)
        theme_extend = self._build_theme_extend(tokens)

        if css_output:
            css_path = Path(css_output)
            css_path.parent.mkdir(parents=True, exist_ok=True)
            css_path.write_text(self._render_globals_css(css_vars), encoding="utf-8")
            result.css_path = css_path
            result.notes.append(f"wrote CSS variables to {css_path}")

        if tailwind_output:
            tw_path = Path(tailwind_output)
            tw_path.parent.mkdir(parents=True, exist_ok=True)

            if patch_existing and tw_path.exists():
                existing = tw_path.read_text(encoding="utf-8")
                rendered = self._patch_existing_config(existing, theme_extend)
                result.notes.append(f"patched existing Tailwind config at {tw_path}")
            else:
                rendered = self._render_tailwind_config(theme_extend)
                if patch_existing:
                    result.notes.append(
                        f"--patch ignored: {tw_path} does not exist; generated fresh config"
                    )
                else:
                    result.notes.append(f"generated fresh Tailwind config at {tw_path}")

            tw_path.write_text(rendered, encoding="utf-8")
            result.tailwind_path = tw_path

        return result

    def _build_css_variables(self, tokens: dict[str, Any]) -> dict[str, str]:
        """Flatten DTCG tokens into CSS custom property names and values."""
        variables: dict[str, str] = {}

        # Colors
        for name, token in tokens.get("color", {}).items():
            if isinstance(token, dict) and token.get("$type") == "color":
                variables[f"--color-{self._kebab(name)}"] = token["$value"]

        # Font families
        for name, token in tokens.get("fontFamily", {}).items():
            if isinstance(token, dict) and token.get("$type") == "fontFamily":
                variables[f"--font-{self._kebab(name)}"] = token["$value"]

        # Typography (size/lineHeight/letterSpacing)
        for name, token in tokens.get("fontSize", {}).items():
            if isinstance(token, dict) and token.get("$type") == "typography":
                value = token["$value"]
                prefix = f"--font-size-{self._kebab(name)}"
                if isinstance(value, dict):
                    for sub_key, sub_value in value.items():
                        variables[f"{prefix}-{self._kebab(sub_key)}"] = str(sub_value)
                else:
                    variables[prefix] = str(value)

        # Spacing
        for name, token in tokens.get("spacing", {}).items():
            if isinstance(token, dict) and token.get("$type") == "dimension":
                variables[f"--spacing-{self._kebab(name)}"] = token["$value"]

        # Shadows
        for name, token in tokens.get("shadow", {}).items():
            if isinstance(token, dict) and token.get("$type") == "shadow":
                variables[f"--shadow-{self._kebab(name)}"] = token["$value"]

        # Border radius
        for name, token in tokens.get("borderRadius", {}).items():
            if isinstance(token, dict) and token.get("$type") == "dimension":
                variables[f"--radius-{self._kebab(name)}"] = token["$value"]

        # Motion durations
        for name, token in tokens.get("motion", {}).get("duration", {}).items():
            if isinstance(token, dict) and token.get("$type") == "duration":
                variables[f"--duration-{self._kebab(name)}"] = token["$value"]

        return variables

    def _build_theme_extend(self, tokens: dict[str, Any]) -> dict[str, Any]:
        """Build Tailwind theme.extend object referencing CSS variables."""
        extend: dict[str, Any] = {}

        colors = {
            name: f"var(--color-{self._kebab(name)})"
            for name, token in tokens.get("color", {}).items()
            if isinstance(token, dict) and token.get("$type") == "color"
        }
        if colors:
            extend["colors"] = colors

        fonts = {
            name: f"var(--font-{self._kebab(name)})"
            for name, token in tokens.get("fontFamily", {}).items()
            if isinstance(token, dict) and token.get("$type") == "fontFamily"
        }
        if fonts:
            extend["fontFamily"] = fonts

        font_sizes: dict[str, str | list[str]] = {}
        for name, token in tokens.get("fontSize", {}).items():
            if isinstance(token, dict) and token.get("$type") == "typography":
                value = token["$value"]
                prefix = f"var(--font-size-{self._kebab(name)}"
                if isinstance(value, dict):
                    parts = [
                        f"{prefix}-font-size)",
                        f"{prefix}-line-height)",
                    ]
                    if f"{prefix}-letter-spacing)" in str(value):
                        parts.append(f"{prefix}-letter-spacing)")
                    font_sizes[name] = parts
                else:
                    font_sizes[name] = f"{prefix})"
        if font_sizes:
            extend["fontSize"] = font_sizes

        spacing = {
            name: f"var(--spacing-{self._kebab(name)})"
            for name, token in tokens.get("spacing", {}).items()
            if isinstance(token, dict) and token.get("$type") == "dimension"
        }
        if spacing:
            extend["spacing"] = spacing

        shadows = {
            name: f"var(--shadow-{self._kebab(name)})"
            for name, token in tokens.get("shadow", {}).items()
            if isinstance(token, dict) and token.get("$type") == "shadow"
        }
        if shadows:
            extend["boxShadow"] = shadows

        radius = {
            name: f"var(--radius-{self._kebab(name)})"
            for name, token in tokens.get("borderRadius", {}).items()
            if isinstance(token, dict) and token.get("$type") == "dimension"
        }
        if radius:
            extend["borderRadius"] = radius

        durations = {
            name: f"var(--duration-{self._kebab(name)})"
            for name, token in tokens.get("motion", {}).get("duration", {}).items()
            if isinstance(token, dict) and token.get("$type") == "duration"
        }
        if durations:
            extend["transitionDuration"] = durations

        return extend

    @staticmethod
    def _kebab(name: str) -> str:
        """Convert camelCase or snake_case to kebab-case."""
        name = re.sub(r"([a-z0-9])([A-Z])", r"\1-\2", name)
        return name.lower().replace("_", "-").replace(" ", "-")

    @staticmethod
    def _render_globals_css(variables: dict[str, str]) -> str:
        """Render a CSS file with all design tokens as custom properties."""
        lines = [
            "/* Generated by premium-design Tailwind adapter from DTCG tokens.",
            "   Do not hand-edit; regenerate when design_tokens.json changes. */",
            "",
            ":root {",
        ]
        for name in sorted(variables):
            value = variables[name]
            lines.append(f"  {name}: {value};")
        lines.extend(["}", ""])
        return "\n".join(lines)

    @staticmethod
    def _render_tailwind_config(theme_extend: dict[str, Any]) -> str:
        """Render a complete tailwind.config.ts from the theme extend map."""
        extend_json = json.dumps(theme_extend, indent=2, ensure_ascii=False)
        # Convert JSON booleans/numbers to TS literals where needed, but strings stay quoted.
        # For our use case values are all strings referencing CSS vars, so JSON is valid TS.
        return f'''import type {{ Config }} from "tailwindcss";

const config: Config = {{
  content: [
    "./src/app/**/*.{{js,ts,jsx,tsx}}",
    "./src/components/**/*.{{js,ts,jsx,tsx}}",
    "./src/pages/**/*.{{js,ts,jsx,tsx}}",
  ],
  theme: {{
    extend: {extend_json},
  }},
  plugins: [],
}};

export default config;
'''

    def _patch_existing_config(self, existing: str, theme_extend: dict[str, Any]) -> str:
        """Merge theme.extend keys into an existing tailwind.config.ts."""
        import re as _re

        extend_match = _re.search(
            r"extend\s*:\s*(\{[\s\S]*?\})\s*,?\s*(?=plugins|presets|\})",
            existing,
        )

        if extend_match:
            extend_text = extend_match.group(1)
            for key, value in theme_extend.items():
                block_pattern = rf"{key}\s*:\s*(\{{[\s\S]*?\}})"
                block_match = _re.search(block_pattern, extend_text)
                if block_match:
                    # Merge missing entries into existing nested object.
                    nested_text = block_match.group(1)
                    new_lines = []
                    for sub_key, sub_value in value.items():
                        if sub_key not in nested_text:
                            serialized = json.dumps(sub_value, indent=6, ensure_ascii=False)
                            new_lines.append(f"      {json.dumps(sub_key)}: {serialized},")
                    if new_lines:
                        insert_at = block_match.start(1) + len(nested_text) - 1  # before closing }
                        extend_text = (
                            extend_text[:insert_at]
                            + "\n"
                            + "\n".join(new_lines)
                            + extend_text[insert_at:]
                        )
                elif key not in extend_text:
                    # Append whole new top-level key.
                    serialized = json.dumps(value, indent=4, ensure_ascii=False)
                    insert_at = extend_text.rfind("}")
                    prefix = "," if not extend_text[:insert_at].rstrip().endswith(",") else ""
                    extend_text = (
                        extend_text[:insert_at]
                        + prefix
                        + f"\n    {json.dumps(key)}: {serialized},"
                        + extend_text[insert_at:]
                    )

            existing = existing[: extend_match.start(1)] + extend_text + existing[extend_match.end(1):]
            return existing

        # No extend block found: insert one inside theme object
        theme_match = _re.search(r"theme\s*:\s*\{", existing)
        if theme_match:
            insert_at = theme_match.end()
            extend_json = json.dumps(theme_extend, indent=4, ensure_ascii=False)
            block = f"\n    extend: {extend_json},"
            return existing[:insert_at] + block + existing[insert_at:]

        # Fallback: return fresh config
        return self._render_tailwind_config(theme_extend)


# ---------------------------------------------------------------------------
# CLI helpers
# ---------------------------------------------------------------------------

def generate_tailwind_from_tokens(
    tokens_path: Path | str,
    tailwind_output: Path | str,
    css_output: Path | str | None = None,
    *,
    patch_existing: bool = False,
    strict: bool = True,
    allowed_fonts: list[str] | None = None,
    forbidden_fonts: list[str] | None = None,
) -> TailwindAdapterResult:
    """Convenience wrapper for one-shot CLI/script usage."""
    adapter = TailwindConfigAdapter(
        tokens_path=tokens_path,
        allowed_fonts=allowed_fonts,
        forbidden_fonts=forbidden_fonts,
    )
    return adapter.generate(
        tailwind_output=tailwind_output,
        css_output=css_output,
        patch_existing=patch_existing,
        strict=strict,
    )
