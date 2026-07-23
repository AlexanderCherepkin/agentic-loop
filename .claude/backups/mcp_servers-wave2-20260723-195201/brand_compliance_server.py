"""Brand Compliance MCP server.

Reads DESIGN.md and design_tokens.json as the single source of brand truth and
exposes deterministic checks for team-wide use: design-token drift, forbidden fonts,
generic shadows, layout animations, and PR slop audits.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from .base import MCPServer


class BrandComplianceMCPServer(MCPServer):
    """MCP server enforcing brand and anti-slop policies from DESIGN.md + tokens."""

    def __init__(self, workspace_root: str = "."):
        super().__init__(name="brand_compliance", version="1.0.0")
        self._initialized = True
        self.workspace = Path(workspace_root).resolve()
        self._tokens_path = self.workspace / "design_tokens.json"
        self._design_md_path = self.workspace / "DESIGN.md"
        self._register_tools()

    def _register_tools(self) -> None:
        s = self._schema
        self.register(
            "check_brand_policy",
            "Verify that DESIGN.md and design_tokens.json exist and align",
            s({"design_md_path?": "string", "tokens_path?": "string"}),
            self.check_brand_policy,
        )
        self.register(
            "check_design_tokens",
            "Run anti-slop checks on design_tokens.json",
            s({"tokens_path?": "string", "strict?": "bool"}),
            self.check_design_tokens,
        )
        self.register(
            "check_pr_slop",
            "Audit a file or diff for slop patterns",
            s({"path": "string", "patch_text?": "string"}),
            self.check_pr_slop,
        )

    @staticmethod
    def _schema(props: dict[str, str]) -> dict[str, Any]:
        required = [k for k in props if not k.endswith("?")]
        properties: dict[str, Any] = {}
        type_map = {
            "string": "string",
            "int": "integer",
            "bool": "boolean",
            "float": "number",
            "array": "array",
            "object": "object",
        }
        for k, v in props.items():
            name = k.rstrip("?")
            properties[name] = {
                "type": type_map.get(v, "string"),
                "description": f"The {name} parameter",
            }
        return {"type": "object", "properties": properties, "required": required}

    def _resolve_paths(
        self, tokens_path: str | None, design_md_path: str | None
    ) -> tuple[Path, Path]:
        tokens = Path(tokens_path) if tokens_path else self._tokens_path
        design_md = Path(design_md_path) if design_md_path else self._design_md_path
        return tokens.resolve(), design_md.resolve()

    def check_brand_policy(
        self,
        design_md_path: str = "",
        tokens_path: str = "",
    ) -> dict[str, Any]:
        tokens_path_p, design_md_path_p = self._resolve_paths(tokens_path, design_md_path)
        errors: list[str] = []
        if not design_md_path_p.exists():
            errors.append(f"DESIGN.md not found at {design_md_path_p}")
        if not tokens_path_p.exists():
            errors.append(f"design_tokens.json not found at {tokens_path_p}")

        result: dict[str, Any] = {
            "design_md_exists": design_md_path_p.exists(),
            "tokens_exists": tokens_path_p.exists(),
            "errors": errors,
        }
        if errors:
            return {"status": "error", "is_error": True, **result}

        try:
            tokens = json.loads(tokens_path_p.read_text(encoding="utf-8"))
        except Exception as exc:
            return {"status": "error", "is_error": True, "errors": [str(exc)]}

        design_text = design_md_path_p.read_text(encoding="utf-8")
        result["direction_match"] = self._check_direction_match(tokens, design_text)
        result["palette_match"] = self._check_palette_match(tokens, design_text)
        result["ok"] = not result["direction_match"]["mismatch"] and not result["palette_match"]["mismatch"]
        return {"status": "success", "is_error": False, **result}

    def check_design_tokens(
        self,
        tokens_path: str = "",
        strict: bool = True,
    ) -> dict[str, Any]:
        tokens_p, _ = self._resolve_paths(tokens_path, "")
        if not tokens_p.exists():
            return {"status": "error", "is_error": True, "errors": [f"Tokens not found: {tokens_p}"]}

        try:
            tokens = json.loads(tokens_p.read_text(encoding="utf-8"))
        except Exception as exc:
            return {"status": "error", "is_error": True, "errors": [str(exc)]}

        violations = self._audit_tokens(tokens)
        result: dict[str, Any] = {
            "violations": violations,
            "violation_count": len(violations),
            "ok": not (strict and violations),
        }
        return {"status": "success", "is_error": False, **result}

    def check_pr_slop(
        self,
        path: str,
        patch_text: str = "",
    ) -> dict[str, Any]:
        """Audit a file path or patch text for common slop patterns."""
        text = patch_text
        if not text and path:
            p = Path(path).resolve()
            if p.exists():
                text = p.read_text(encoding="utf-8")

        violations: list[dict[str, Any]] = []
        if re.search(r"\bfont-['\"]?(Inter|Roboto|Open\sSans|Helvetica|Arial)\b", text, re.IGNORECASE):
            violations.append({"rule": "default_font", "message": "Default font detected"})
        if re.search(r"\bshadow-(md|lg|xl)\b", text):
            violations.append({"rule": "generic_shadow", "message": "Generic Tailwind shadow class"})
        if re.search(r"\btransition-(all|width|height|margin|padding)\b", text):
            violations.append({"rule": "layout_transition", "message": "Transition targets layout properties"})
        if re.search(r"\btext-(gray|neutral|zinc)-(400|500|600)\b", text):
            violations.append({"rule": "flat_gray_text", "message": "Flat gray text utility"})
        if re.search(r"\bw-[\d]+px\b|\bp-[\d]+px\b|\bh-[\d]+px\b", text):
            violations.append({"rule": "magic_inline", "message": "Magic inline Tailwind value"})

        return {
            "status": "success",
            "is_error": False,
            "violations": violations,
            "violation_count": len(violations),
            "ok": not violations,
        }

    def _check_direction_match(self, tokens: dict[str, Any], design_text: str) -> dict[str, Any]:
        token_direction = tokens.get("direction", {}).get("$value", "")
        design_direction = ""
        for line in design_text.splitlines():
            if "direction" in line.lower() and ":" in line:
                design_direction = line.split(":", 1)[1].strip().lower()
                break
        if not design_direction or not token_direction:
            return {"mismatch": False, "token": token_direction, "design": design_direction}
        return {
            "mismatch": design_direction not in token_direction.lower() and token_direction not in design_direction,
            "token": token_direction,
            "design": design_direction,
        }

    def _check_palette_match(self, tokens: dict[str, Any], design_text: str) -> dict[str, Any]:
        colors = tokens.get("color", {})
        mismatches: list[str] = []
        for name, token in colors.items():
            if not isinstance(token, dict) or token.get("$type") != "color":
                continue
            value = token.get("$value", "").lower()
            if value and value not in design_text.lower():
                mismatches.append(name)
        return {"mismatch": bool(mismatches), "missing_in_design_md": mismatches}

    def _audit_tokens(self, tokens: dict[str, Any]) -> list[dict[str, Any]]:
        violations: list[dict[str, Any]] = []

        forbidden = {
            "comic sans ms", "papyrus", "curlz mt", "arial", "courier new",
            "times new roman", "bradel hand itc", "vivaldi", "kristen itc",
            "viner hand", "mistral", "impact", "symbol", "stencil",
            "broad latin", "extended latin", "inter", "roboto", "open sans",
            "helvetica", "segoe ui", "san francisco", "myriad pro", "calibri",
            "verdana", "century gothic", "space grotesk",
        }
        fonts = tokens.get("fontFamily", {})
        for role, token in fonts.items():
            value = token.get("$value", "") if isinstance(token, dict) else str(token)
            for family in re.split(r"[,;]", value):
                clean = family.strip().strip("'\"").lower()
                if clean in forbidden:
                    violations.append({"rule": "forbidden_font", "role": role, "family": clean})

        colors = tokens.get("color", {})
        if isinstance(colors, dict):
            muted = colors.get("muted", {}).get("$value", "")
            if muted and muted.lower() in ("#777777", "#808080", "#888888", "#999999"):
                violations.append({"rule": "flat_gray_muted", "token": "color.muted"})

        shadows = tokens.get("shadow", {})
        generic = re.compile(
            r"0\s+4px\s+6px|0\s+10px\s+15px|0\s+20px\s+25px|shadow-md|shadow-lg",
            re.IGNORECASE,
        )
        for name, token in shadows.items():
            value = token.get("$value", "") if isinstance(token, dict) else str(token)
            if generic.search(value):
                violations.append({"rule": "generic_shadow", "token": f"shadow.{name}"})

        motion = tokens.get("motion", {})
        if isinstance(motion, dict):
            allowed = motion.get("allowed_properties", {}).get("$value", [])
            for prop in ("width", "height", "margin", "padding", "top", "left"):
                if prop in allowed:
                    violations.append({"rule": "layout_animation", "property": prop})

        return violations

    async def ping(self) -> bool:
        return True
