"""Open Lovable self-hosted bridge.

Wraps a local Open Lovable / Firecrawl-based Design-to-Code runner so the
Agentic Loop can hand off a Figma JSON tree or a DESIGN.md brief and receive a
set of generated React components. The bridge is intentionally thin: it does
not reimplement generation, only normalizes inputs/outputs and enforces the
anti-slop contract before/after generation.
"""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class OpenLovableBridgeResult:
    ok: bool = False
    output_dir: Path | None = None
    files: list[Path] = field(default_factory=list)
    component_paths: list[Path] = field(default_factory=list)
    violations_before: list[dict[str, Any]] = field(default_factory=list)
    violations_after: list[dict[str, Any]] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


class OpenLovableBridge:
    """Adapter to a self-hosted Open Lovable / Firecrawl Next.js generator."""

    def __init__(
        self,
        workspace_root: Path | str = ".",
        runner_command: str | None = None,
        runner_dir: Path | str | None = None,
    ):
        self.workspace = Path(workspace_root).resolve()
        self.runner_command = runner_command or "npx"
        self.runner_dir = Path(runner_dir) if runner_dir else self.workspace / "open-lovable"

    def run_from_design_md(
        self,
        design_md_path: Path | str,
        output_dir: Path | str | None = None,
        extra_args: list[str] | None = None,
    ) -> OpenLovableBridgeResult:
        """Run Open Lovable from a DESIGN.md brief."""
        result = OpenLovableBridgeResult()
        design_md_path = Path(design_md_path).resolve()
        if not design_md_path.exists():
            result.errors.append(f"DESIGN.md not found: {design_md_path}")
            return result

        out = Path(output_dir).resolve() if output_dir else self.workspace / "open-lovable-output"
        out.mkdir(parents=True, exist_ok=True)
        result.output_dir = out

        # Pre-flight: ensure DESIGN.md contains anti-slop contract
        design_text = design_md_path.read_text(encoding="utf-8")
        required_sections = ("Color System", "Typography", "Anti-Slop Gates")
        for section in required_sections:
            if section not in design_text:
                result.violations_before.append(
                    {"rule": "missing_design_section", "section": section}
                )

        if result.violations_before:
            result.errors.append("DESIGN.md missing required anti-slop sections")
            return result

        args = [
            self.runner_command,
            "open-lovable",
            "--brief", str(design_md_path),
            "--output", str(out),
        ] + (extra_args or [])

        return self._run_subprocess(args, result)

    def run_from_figma_json(
        self,
        figma_json_path: Path | str,
        output_dir: Path | str | None = None,
        extra_args: list[str] | None = None,
    ) -> OpenLovableBridgeResult:
        """Run Open Lovable from a Figma JSON tree exported by figma-agent-core."""
        result = OpenLovableBridgeResult()
        figma_json_path = Path(figma_json_path).resolve()
        if not figma_json_path.exists():
            result.errors.append(f"Figma JSON not found: {figma_json_path}")
            return result

        out = Path(output_dir).resolve() if output_dir else self.workspace / "open-lovable-output"
        out.mkdir(parents=True, exist_ok=True)
        result.output_dir = out

        args = [
            self.runner_command,
            "open-lovable",
            "--figma-json", str(figma_json_path),
            "--output", str(out),
        ] + (extra_args or [])

        return self._run_subprocess(args, result)

    def _run_subprocess(
        self,
        args: list[str],
        result: OpenLovableBridgeResult,
    ) -> OpenLovableBridgeResult:
        try:
            proc = subprocess.run(
                args,
                cwd=str(self.runner_dir) if self.runner_dir.exists() else str(self.workspace),
                capture_output=True,
                text=True,
                timeout=600,
            )
            result.notes.append(f"Open Lovable exit code: {proc.returncode}")
            if proc.stdout:
                result.notes.append(proc.stdout[:2000])
            if proc.returncode != 0:
                result.errors.append(proc.stderr[:2000] if proc.stderr else "Open Lovable runner failed")
                return result

            # Collect generated files
            if result.output_dir:
                result.files = sorted(result.output_dir.rglob("*"))
                result.component_paths = [p for p in result.files if p.suffix in (".tsx", ".jsx")]
                result.notes.append(f"generated {len(result.component_paths)} components")

            result.ok = True
        except subprocess.TimeoutExpired as exc:
            result.errors.append(f"Open Lovable timed out: {exc}")
        except Exception as exc:
            result.errors.append(f"Open Lovable runner error: {exc}")

        return result

    def audit_output(
        self,
        result: OpenLovableBridgeResult,
        tokens_path: Path | str | None = None,
    ) -> OpenLovableBridgeResult:
        """Run post-generation anti-slop audit on generated components."""
        if tokens_path:
            tokens_path = Path(tokens_path).resolve()
            if tokens_path.exists():
                tokens = json.loads(tokens_path.read_text(encoding="utf-8"))
                from .dtcg_engine import detect_slop_tokens
                result.violations_after = detect_slop_tokens(tokens)

        forbidden_patterns = {
            "shadow-md": "generic_shadow",
            "shadow-lg": "generic_shadow",
            "transition-all": "layout_transition",
            "font-Inter": "default_font",
            "font-Roboto": "default_font",
            "text-gray-500": "flat_gray_text",
        }

        for component in result.component_paths:
            text = component.read_text(encoding="utf-8", errors="ignore")
            for literal, rule in forbidden_patterns.items():
                if literal in text:
                    result.violations_after.append({"rule": rule, "file": str(component)})

        if result.violations_after:
            result.ok = False
        return result
