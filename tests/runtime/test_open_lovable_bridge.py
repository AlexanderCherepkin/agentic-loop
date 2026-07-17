"""pytest tests for the Open Lovable self-hosted bridge.

Uses monkeypatch on subprocess.run so no real `npx open-lovable` is invoked.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import pytest

from runtime.premium_design.open_lovable_bridge import OpenLovableBridge, OpenLovableBridgeResult


@pytest.fixture
def bridge(tmp_path: Path) -> OpenLovableBridge:
    return OpenLovableBridge(workspace_root=tmp_path, runner_dir=tmp_path / "open-lovable")


def test_run_from_design_md_missing_file(bridge: OpenLovableBridge) -> None:
    result = bridge.run_from_design_md("/nonexistent/DESIGN.md")
    assert result.ok is False
    assert "DESIGN.md not found" in result.errors[0]


def test_run_from_design_md_missing_sections(bridge: OpenLovableBridge, tmp_path: Path) -> None:
    design_md = tmp_path / "DESIGN.md"
    design_md.write_text("# Brand Core\nNo anti-slop sections.\n")
    result = bridge.run_from_design_md(str(design_md))
    assert result.ok is False
    assert result.violations_before
    assert "DESIGN.md missing required anti-slop sections" in result.errors[0]


def test_run_from_design_md_success(bridge: OpenLovableBridge, tmp_path: Path, monkeypatch: Any) -> None:
    design_md = tmp_path / "DESIGN.md"
    design_md.write_text("Color System\nTypography\nAnti-Slop Gates\n")

    out = tmp_path / "open-lovable-output"
    out.mkdir(parents=True)
    component = out / "Button.tsx"
    component.write_text('export const Button = () => <button className="font-Manrope">OK</button>;')

    class CompletedProcess:
        returncode = 0
        stdout = "generated 1 components"
        stderr = ""

    monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs: CompletedProcess())

    result = bridge.run_from_design_md(str(design_md))
    assert result.ok is True
    assert result.output_dir == out
    assert component in result.component_paths


def test_run_from_figma_json_missing_file(bridge: OpenLovableBridge) -> None:
    result = bridge.run_from_figma_json("/nonexistent/figma.json")
    assert result.ok is False
    assert "Figma JSON not found" in result.errors[0]


def test_run_from_figma_json_success(bridge: OpenLovableBridge, tmp_path: Path, monkeypatch: Any) -> None:
    figma_json = tmp_path / "figma.json"
    figma_json.write_text('{"document": {"children": []}}')

    out = tmp_path / "open-lovable-output"
    out.mkdir(parents=True)

    class CompletedProcess:
        returncode = 0
        stdout = ""
        stderr = ""

    monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs: CompletedProcess())

    result = bridge.run_from_figma_json(str(figma_json))
    assert result.ok is True
    assert result.output_dir == out


def test_audit_output_detects_slop(bridge: OpenLovableBridge, tmp_path: Path) -> None:
    out = tmp_path / "open-lovable-output"
    out.mkdir(parents=True)
    bad = out / "Card.tsx"
    bad.write_text('<div className="shadow-md transition-all font-Inter text-gray-500"></div>')

    result = OpenLovableBridgeResult(ok=True, output_dir=out, component_paths=[bad], files=[bad])
    audited = bridge.audit_output(result)
    rules = {v["rule"] for v in audited.violations_after}
    assert "generic_shadow" in rules
    assert "layout_transition" in rules
    assert "default_font" in rules
    assert "flat_gray_text" in rules
    assert audited.ok is False


def test_audit_output_clean(bridge: OpenLovableBridge, tmp_path: Path) -> None:
    out = tmp_path / "open-lovable-output"
    out.mkdir(parents=True)
    good = out / "Card.tsx"
    good.write_text('<div className="shadow-elevation transition-colors font-sans text-surface-900"></div>')

    result = OpenLovableBridgeResult(ok=True, output_dir=out, component_paths=[good], files=[good])
    audited = bridge.audit_output(result)
    assert audited.violations_after == []
    assert audited.ok is True
