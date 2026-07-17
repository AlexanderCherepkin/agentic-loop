"""Open Pencil MCP bridge.

Exposes the open-source design-to-code engine behind Open Pencil as an MCP
category `open_pencil`. The server is intentionally thin: it normalizes inputs,
runs the local Open Pencil runner, and enforces anti-slop policies before/after
generation. It degrades gracefully when the Open Pencil runner is not installed.
"""

from __future__ import annotations

import json
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .base import MCPServer


@dataclass
class OpenPencilViolation:
    rule: str
    message: str
    file: str = ""


@dataclass
class OpenPencilResult:
    ok: bool = False
    output_dir: Path | None = None
    files: list[Path] = field(default_factory=list)
    component_paths: list[Path] = field(default_factory=list)
    violations_before: list[OpenPencilViolation] = field(default_factory=list)
    violations_after: list[OpenPencilViolation] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


class OpenPencilMCPServer(MCPServer):
    """MCP server for the Open Pencil open-source design-to-code runner."""

    FORBIDDEN_PATTERNS: dict[str, str] = {
        "shadow-md": "generic_shadow",
        "shadow-lg": "generic_shadow",
        "transition-all": "layout_transition",
        "transition-width": "layout_transition",
        "transition-height": "layout_transition",
        "font-Inter": "default_font",
        "font-Roboto": "default_font",
        "font-Arial": "default_font",
        "text-gray-500": "flat_gray_text",
        "text-gray-400": "flat_gray_text",
        "text-gray-600": "flat_gray_text",
        "bg-gray-100": "flat_gray_surface",
    }

    REQUIRED_DESIGN_SECTIONS = (
        "Color System",
        "Typography",
        "Anti-Slop Gates",
    )

    def __init__(self, workspace_root: str = "."):
        super().__init__(name="open_pencil", version="1.0.0")
        self._initialized = True
        self.workspace = Path(workspace_root).resolve()
        self.runner_command = "npx"
        self.runner_name = "open-pencil"
        self._degraded_reason: str | None = None
        self._runner_available: bool | None = None
        self._register_tools()

    def _register_tools(self) -> None:
        s = self._schema
        self.register(
            "openpencil_from_design_md",
            "Run Open Pencil from a DESIGN.md brief",
            s({"design_md_path": "string", "output_dir?": "string", "extra_args?": "array"}),
            self.openpencil_from_design_md,
        )
        self.register(
            "openpencil_from_figma_json",
            "Run Open Pencil from a Figma JSON tree",
            s({"figma_json_path": "string", "output_dir?": "string", "extra_args?": "array"}),
            self.openpencil_from_figma_json,
        )
        self.register(
            "openpencil_audit_output",
            "Audit generated components for slop patterns",
            s({"output_dir": "string", "tokens_path?": "string"}),
            self.openpencil_audit_output,
        )
        self.register(
            "openpencil_check_runner",
            "Check whether the Open Pencil runner is available",
            s({}),
            self.openpencil_check_runner,
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

    def _check_runner(self) -> bool:
        if self._runner_available is not None:
            return self._runner_available
        try:
            proc = subprocess.run(
                [self.runner_command, "which", self.runner_name],
                cwd=str(self.workspace),
                capture_output=True,
                text=True,
                timeout=10,
            )
            available = proc.returncode == 0
        except Exception as exc:
            available = False
            self._degraded_reason = f"runner check failed: {exc}"
        self._runner_available = available
        return available

    def _preflight_design_md(self, design_md_path: Path, result: OpenPencilResult) -> bool:
        if not design_md_path.exists():
            result.errors.append(f"DESIGN.md not found: {design_md_path}")
            return False

        text = design_md_path.read_text(encoding="utf-8")
        for section in self.REQUIRED_DESIGN_SECTIONS:
            if section not in text:
                result.violations_before.append(
                    OpenPencilViolation(
                        rule="missing_design_section",
                        message=f"Required section '{section}' not found in DESIGN.md",
                    )
                )

        if result.violations_before:
            result.errors.append("DESIGN.md missing required anti-slop sections")
            return False
        return True

    def _run_subprocess(
        self,
        args: list[str],
        result: OpenPencilResult,
    ) -> OpenPencilResult:
        if not self._check_runner():
            result.errors.append(
                f"Open Pencil runner '{self.runner_name}' is not available via {self.runner_command}"
            )
            result.notes.append(
                "Install the runner or set a custom command with the runner_command parameter."
            )
            return result

        try:
            proc = subprocess.run(
                args,
                cwd=str(self.workspace),
                capture_output=True,
                text=True,
                timeout=600,
            )
            result.notes.append(f"Open Pencil exit code: {proc.returncode}")
            if proc.stdout:
                result.notes.append(proc.stdout[:2000])
            if proc.returncode != 0:
                result.errors.append(proc.stderr[:2000] if proc.stderr else "Open Pencil runner failed")
                return result

            if result.output_dir:
                result.files = sorted(result.output_dir.rglob("*"))
                result.component_paths = [p for p in result.files if p.suffix in (".tsx", ".jsx", ".vue", ".svelte")]
                result.notes.append(f"generated {len(result.component_paths)} components")

            result.ok = True
        except subprocess.TimeoutExpired as exc:
            result.errors.append(f"Open Pencil timed out: {exc}")
        except Exception as exc:
            result.errors.append(f"Open Pencil runner error: {exc}")

        return result

    def openpencil_from_design_md(
        self,
        design_md_path: str,
        output_dir: str = "",
        extra_args: list[str] | None = None,
    ) -> dict[str, Any]:
        design_md_path_p = Path(design_md_path).resolve()
        result = OpenPencilResult()

        if not self._preflight_design_md(design_md_path_p, result):
            return self._result_to_dict(result)

        out = Path(output_dir).resolve() if output_dir else self.workspace / "open-pencil-output"
        out.mkdir(parents=True, exist_ok=True)
        result.output_dir = out

        args = [
            self.runner_command,
            self.runner_name,
            "--brief", str(design_md_path_p),
            "--output", str(out),
        ] + (extra_args or [])

        result = self._run_subprocess(args, result)
        return self._result_to_dict(result)

    def openpencil_from_figma_json(
        self,
        figma_json_path: str,
        output_dir: str = "",
        extra_args: list[str] | None = None,
    ) -> dict[str, Any]:
        figma_json_path_p = Path(figma_json_path).resolve()
        result = OpenPencilResult()

        if not figma_json_path_p.exists():
            result.errors.append(f"Figma JSON not found: {figma_json_path_p}")
            return self._result_to_dict(result)

        out = Path(output_dir).resolve() if output_dir else self.workspace / "open-pencil-output"
        out.mkdir(parents=True, exist_ok=True)
        result.output_dir = out

        args = [
            self.runner_command,
            self.runner_name,
            "--figma-json", str(figma_json_path_p),
            "--output", str(out),
        ] + (extra_args or [])

        result = self._run_subprocess(args, result)
        return self._result_to_dict(result)

    def openpencil_audit_output(
        self,
        output_dir: str,
        tokens_path: str = "",
    ) -> dict[str, Any]:
        result = OpenPencilResult()
        out = Path(output_dir).resolve()
        if not out.exists():
            result.errors.append(f"Output directory not found: {out}")
            return self._result_to_dict(result)

        result.output_dir = out
        result.files = sorted(out.rglob("*"))
        result.component_paths = [p for p in result.files if p.suffix in (".tsx", ".jsx", ".vue", ".svelte")]

        # Audit against tokens if provided.
        if tokens_path:
            tokens_p = Path(tokens_path).resolve()
            if tokens_p.exists():
                try:
                    tokens = json.loads(tokens_p.read_text(encoding="utf-8"))
                    result.violations_after.extend(self._audit_tokens(tokens))
                except Exception as exc:
                    result.errors.append(f"Could not audit tokens: {exc}")

        # Audit component source for forbidden patterns.
        for component in result.component_paths:
            text = component.read_text(encoding="utf-8", errors="ignore")
            for literal, rule in self.FORBIDDEN_PATTERNS.items():
                if literal in text:
                    result.violations_after.append(
                        OpenPencilViolation(
                            rule=rule,
                            message=f"Forbidden pattern '{literal}' found",
                            file=str(component),
                        )
                    )

        result.ok = not result.violations_after and not result.errors
        return self._result_to_dict(result)

    def openpencil_check_runner(self) -> dict[str, Any]:
        available = self._check_runner()
        return {
            "status": "success" if available else "degraded",
            "is_error": False,
            "available": available,
            "degraded_reason": self._degraded_reason,
        }

    def _audit_tokens(self, tokens: dict[str, Any]) -> list[OpenPencilViolation]:
        violations: list[OpenPencilViolation] = []

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
                    violations.append(
                        OpenPencilViolation(
                            rule="forbidden_font",
                            message=f"Forbidden font '{clean}' in role '{role}'",
                        )
                    )

        colors = tokens.get("color", {})
        if isinstance(colors, dict):
            muted = colors.get("muted", {}).get("$value", "")
            if muted and muted.lower() in ("#777777", "#808080", "#888888", "#999999"):
                violations.append(
                    OpenPencilViolation(rule="flat_gray_muted", message="Flat gray muted color")
                )

        shadows = tokens.get("shadow", {})
        generic = re.compile(
            r"0\s+4px\s+6px|0\s+10px\s+15px|0\s+20px\s+25px|shadow-md|shadow-lg",
            re.IGNORECASE,
        )
        for name, token in shadows.items():
            value = token.get("$value", "") if isinstance(token, dict) else str(token)
            if generic.search(value):
                violations.append(
                    OpenPencilViolation(
                        rule="generic_shadow",
                        message=f"Generic shadow in token 'shadow.{name}'",
                    )
                )

        motion = tokens.get("motion", {})
        if isinstance(motion, dict):
            allowed = motion.get("allowed_properties", {}).get("$value", [])
            for prop in ("width", "height", "margin", "padding", "top", "left"):
                if prop in allowed:
                    violations.append(
                        OpenPencilViolation(
                            rule="layout_animation",
                            message=f"Forbidden animated property '{prop}'",
                        )
                    )

        return violations

    def _result_to_dict(self, result: OpenPencilResult) -> dict[str, Any]:
        return {
            "status": "success" if result.ok else ("degraded" if self._degraded_reason and not result.errors else "error"),
            "is_error": not result.ok,
            "ok": result.ok,
            "output_dir": str(result.output_dir) if result.output_dir else None,
            "file_count": len(result.files),
            "component_count": len(result.component_paths),
            "files": [str(p) for p in result.files],
            "component_paths": [str(p) for p in result.component_paths],
            "violations_before": [
                {"rule": v.rule, "message": v.message, "file": v.file}
                for v in result.violations_before
            ],
            "violations_after": [
                {"rule": v.rule, "message": v.message, "file": v.file}
                for v in result.violations_after
            ],
            "notes": result.notes,
            "errors": result.errors,
            "degraded_reason": self._degraded_reason,
        }

    async def ping(self) -> bool:
        return True
