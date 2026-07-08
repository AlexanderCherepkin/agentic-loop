from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .config import DesignTokenDocsConfig


@dataclass
class DesignTokenDocsResult:
    files_written: list[str] = field(default_factory=list)
    files_modified: list[str] = field(default_factory=list)
    errors: list[dict[str, Any]] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    sections_found: list[str] = field(default_factory=list)


class DesignTokenDocsEngine:
    def __init__(self, target_dir: Path | str, config: DesignTokenDocsConfig | None = None):
        self.target_dir = Path(target_dir).resolve()
        self.config = config or DesignTokenDocsConfig()
        self.config.target_dir = self.target_dir
        self.result = DesignTokenDocsResult()
        self._tokens: dict[str, Any] = {}
        self._registry: dict[str, Any] | None = None

    def run(self) -> DesignTokenDocsResult:
        validation_errors = self.config.validate()
        if validation_errors:
            for err in validation_errors:
                self.result.errors.append({"file": "", "reason": err})
            return self.result

        self._load_sources()
        if not self._tokens and not self.result.errors:
            self.result.errors.append(
                {"file": "", "reason": "no design_tokens.json found in any configured source path"}
            )
        if self.result.errors:
            return self.result

        self._determine_sections()
        self._write_artifacts()
        return self.result

    def _load_sources(self) -> None:
        token_path = self._find_first_existing(self.config.source_files)
        if token_path:
            try:
                self._tokens = json.loads(token_path.read_text(encoding="utf-8"))
                self.result.notes.append(f"loaded token registry from {self._rel(token_path)}")
            except Exception as exc:
                self.result.errors.append(
                    {"file": self._rel(token_path), "reason": f"failed to parse design tokens: {exc}"}
                )
                self._tokens = {}

        registry_path = self._find_first_existing(self.config.component_registry_files)
        if registry_path:
            try:
                self._registry = json.loads(registry_path.read_text(encoding="utf-8"))
                self.result.notes.append(
                    f"loaded component registry from {self._rel(registry_path)}"
                )
            except Exception as exc:
                self.result.notes.append(
                    f"component registry at {self._rel(registry_path)} could not be parsed: {exc}"
                )
                self._registry = None

    def _find_first_existing(self, candidates: list[str]) -> Path | None:
        for rel in candidates:
            path = self.target_dir / rel
            if path.exists():
                return path
        return None

    def _rel(self, path: Path) -> str:
        try:
            return str(path.relative_to(self.target_dir))
        except ValueError:
            return str(path)

    def _determine_sections(self) -> None:
        sections: set[str] = set()
        if self._tokens.get("colors") or self._tokens.get("color_by_hex"):
            sections.add("colors")
        if (
            self._tokens.get("fonts")
            or self._tokens.get("font_sizes")
            or self._tokens.get("font_weights")
            or self._tokens.get("line_heights")
        ):
            sections.add("typography")
        if self._registry is not None:
            sections.add("components")
        if sections:
            sections.add("usage")
        self.result.sections_found = sorted(sections)

    def _write_artifacts(self) -> None:
        out_dir = self.target_dir / self.config.output_dir
        out_dir.mkdir(parents=True, exist_ok=True)

        if "markdown" in self.config.formats:
            md = self._render_markdown()
            self._write_file(f"{self.config.output_dir}/{self.config.markdown_filename}", md)

        if "json" in self.config.formats:
            payload = self._render_json_payload()
            self._write_file(
                f"{self.config.output_dir}/{self.config.json_filename}",
                _stable_json(payload),
            )

        if "html" in self.config.formats:
            html = self._render_html()
            self._write_file(f"{self.config.output_dir}/{self.config.html_filename}", html)

    def _write_file(self, rel_path: str, content: str) -> None:
        full_path = self.target_dir / rel_path
        try:
            full_path.parent.mkdir(parents=True, exist_ok=True)
            full_path.write_text(content, encoding="utf-8")
            self.result.files_written.append(rel_path)
        except Exception as exc:
            self.result.errors.append({"file": rel_path, "reason": str(exc)})

    def _render_markdown(self) -> str:
        lines: list[str] = [
            f"# {self.config.title}",
            "",
            self.config.description,
            "",
            "> Auto-generated from Figma styles and variables. Edit the source design file, regenerate the site, and this document will update.",
            "",
        ]

        if "colors" in self.result.sections_found:
            lines.extend(self._markdown_colors())
        if "typography" in self.result.sections_found:
            lines.extend(self._markdown_typography())
        if "components" in self.result.sections_found:
            lines.extend(self._markdown_components())
        if "usage" in self.result.sections_found:
            lines.extend(self._markdown_usage())

        lines.extend(["", "---", "", f"*Generated by Agentic Loop DesignTokenDocsEngine on {self._timestamp()}.*"])
        return "\n".join(lines)

    def _markdown_colors(self) -> list[str]:
        colors = self._tokens.get("colors") or {}
        if not colors:
            return []
        lines = ["## Colors", "", "| Token | Hex | RGB | CSS variable | Contexts |", "|---|---|---|---|---|"]
        for name, token in colors.items():
            hex_val = token.get("hex", "")
            rgb = token.get("rgb", "")
            css_var = token.get("css_var", "")
            contexts = ", ".join(token.get("contexts", [])) or "—"
            preview = ""
            if self.config.include_color_preview and hex_val:
                preview = f" ![](https://via.placeholder.com/16/{_hex_for_preview(hex_val)}/000000?text=+)"
            lines.append(f"| `{name}` | {hex_val}{preview} | {rgb} | `{css_var}` | {contexts} |")
        return lines + [""]

    def _markdown_typography(self) -> list[str]:
        lines = ["## Typography", ""]
        fonts = self._tokens.get("fonts") or {}
        if fonts:
            lines.extend(["### Font families", ""])
            for family, fallback in fonts.items():
                lines.append(f"- **{family}** — fallback: `{fallback}`")
            lines.append("")

        font_sizes = self._tokens.get("font_sizes") or {}
        if font_sizes:
            lines.extend(["### Font sizes", "", "| PX | Tailwind class |", "|---|---|"])
            for px, cls in font_sizes.items():
                lines.append(f"| {px} | `{cls}` |")
            lines.append("")

        font_weights = self._tokens.get("font_weights") or {}
        if font_weights:
            lines.extend(["### Font weights", "", "| Weight | Tailwind class |", "|---|---|"])
            for weight, cls in font_weights.items():
                lines.append(f"| {weight} | `{cls}` |")
            lines.append("")

        line_heights = self._tokens.get("line_heights") or {}
        if line_heights:
            lines.extend(["### Line heights", "", "| Value | Tailwind class |", "|---|---|"])
            for value, cls in line_heights.items():
                lines.append(f"| {value} | `{cls}` |")
            lines.append("")
        return lines

    def _markdown_components(self) -> list[str]:
        if not self._registry:
            return []
        components = self._registry.get("components") or {}
        if not components:
            return []
        lines = ["## Components", "", "| Component | Figma name | Variants | Used by |", "|---|---|---|---|"]
        for comp_id, comp in components.items():
            name = comp.get("name", comp_id)
            variants = ", ".join(comp.get("variants", [])) or "—"
            used_by = ", ".join(comp.get("used_by", [])) or "—"
            lines.append(f"| `{comp_id}` | {name} | {variants} | {used_by} |")
        return lines + [""]

    def _markdown_usage(self) -> list[str]:
        style_map = self._tokens.get("style_token_map") or {}
        variable_map = self._tokens.get("variable_token_map") or {}
        exact_paths = self._tokens.get("exact_token_paths") or []
        if not style_map and not variable_map and not exact_paths:
            return []
        lines = ["## Token mapping", ""]
        if style_map:
            lines.extend(["### Figma styles → tokens", "", "| Style | Token |", "|---|---|"])
            for style, token in style_map.items():
                lines.append(f"| `{style}` | `{token}` |")
            lines.append("")
        if variable_map:
            lines.extend(["### Figma variables → tokens", "", "| Variable | Token |", "|---|---|"])
            for variable, token in variable_map.items():
                lines.append(f"| `{variable}` | `{token}` |")
            lines.append("")
        if exact_paths:
            lines.extend(["### Exact Tailwind token paths", "", "```", *exact_paths, "```", ""])
        return lines

    def _render_json_payload(self) -> dict[str, Any]:
        return {
            "title": self.config.title,
            "description": self.config.description,
            "sections": self.result.sections_found,
            "tokens": {
                "colors": self._tokens.get("colors", {}),
                "fonts": self._tokens.get("fonts", {}),
                "font_sizes": self._tokens.get("font_sizes", {}),
                "font_weights": self._tokens.get("font_weights", {}),
                "line_heights": self._tokens.get("line_heights", {}),
                "style_token_map": self._tokens.get("style_token_map", {}),
                "variable_token_map": self._tokens.get("variable_token_map", {}),
                "exact_token_paths": self._tokens.get("exact_token_paths", []),
            },
            "component_registry": bool(self._registry),
            "generated_at": self._timestamp(),
        }

    def _render_html(self) -> str:
        title = _escape_html(self.config.title)
        desc = _escape_html(self.config.description)
        body = [f"<h1>{title}</h1>", f"<p>{desc}</p>"]
        colors = self._tokens.get("colors") or {}
        if colors:
            body.append("<h2>Colors</h2><table><thead><tr><th>Token</th><th>Hex</th><th>RGB</th><th>CSS var</th><th>Contexts</th></tr></thead><tbody>")
            for name, token in colors.items():
                hex_val = token.get("hex", "")
                swatch = ""
                if hex_val:
                    swatch = f'<span style="display:inline-block;width:16px;height:16px;background:{_escape_html(hex_val)};border:1px solid #ccc;"></span> '
                body.append(
                    f"<tr><td><code>{_escape_html(name)}</code></td>"
                    f"<td>{swatch}{_escape_html(hex_val)}</td>"
                    f"<td>{_escape_html(token.get('rgb', ''))}</td>"
                    f"<td><code>{_escape_html(token.get('css_var', ''))}</code></td>"
                    f"<td>{_escape_html(', '.join(token.get('contexts', [])))}</td></tr>"
                )
            body.append("</tbody></table>")
        return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>{title}</title>
<style>body{{font-family:system-ui,sans-serif;max-width:960px;margin:2rem auto;line-height:1.6}}table{{border-collapse:collapse;width:100%}}th,td{{border:1px solid #ddd;padding:8px;text-align:left}}th{{background:#f5f5f5}}</style>
</head>
<body>
{''.join(body)}
</body>
</html>"""

    def _timestamp(self) -> str:
        from datetime import datetime, timezone
        return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _stable_json(data: Any) -> str:
    return json.dumps(data, indent=2, ensure_ascii=False, sort_keys=True)


def _hex_for_preview(hex_color: str) -> str:
    return hex_color.lstrip("#").lower()


def _escape_html(text: str) -> str:
    return (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )
