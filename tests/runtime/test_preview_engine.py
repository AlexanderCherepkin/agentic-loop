"""Tests for runtime/preview engine and config."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from runtime.preview import PreviewConfig, PreviewEngine


pytestmark = [pytest.mark.core, pytest.mark.runtime]


def _make_preview_module(tmp_path: Path) -> None:
    module_dir = tmp_path / "figma-agent-core"
    module_dir.mkdir(parents=True, exist_ok=True)
    module_dir.joinpath("preview_workflow.py").write_text(
        "def run_preview_workflow(**kwargs):\n"
        "    return {\n"
        "        'status': 'approved',\n"
        "        'page_url': 'http://localhost:3000',\n"
        "        'screenshot_path': 'shot.png',\n"
        "        'preview_html_path': 'preview.html',\n"
        "        'feedback_file_path': None,\n"
        "        'approved': True,\n"
        "        'can_refine': False,\n"
        "        'refinement_hints': [],\n"
        "    }\n",
        encoding="utf-8",
    )


def test_config_from_dict_defaults():
    cfg = PreviewConfig.from_dict({})
    assert cfg.site_dir == "."
    assert cfg.dev_command == "pnpm dev"
    assert cfg.viewport == "1280x720"


def test_config_validation_requires_existing_target(tmp_path):
    cfg = PreviewConfig(target_dir=tmp_path / "missing")
    errors = cfg.validate()
    assert any("target_dir" in e for e in errors)


def test_engine_loads_preview_module_and_maps_report(tmp_path):
    _make_preview_module(tmp_path)
    cfg = PreviewConfig(target_dir=tmp_path, site_dir=".", page_url="http://localhost:3000")
    result = PreviewEngine(tmp_path, cfg).run()
    assert not result.errors
    assert result.status == "approved"
    assert result.approved is True
    assert result.page_url == "http://localhost:3000"
    assert result.screenshot_path == "shot.png"


def test_engine_reports_missing_preview_module(tmp_path):
    cfg = PreviewConfig(target_dir=tmp_path)
    result = PreviewEngine(tmp_path, cfg).run()
    assert result.errors
    assert any("preview workflow" in e["reason"].lower() or "could not load" in e["reason"].lower() for e in result.errors)
