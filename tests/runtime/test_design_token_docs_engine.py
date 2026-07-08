"""Tests for runtime/design_token_docs engine and config."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from runtime.design_token_docs.config import DesignTokenDocsConfig
from runtime.design_token_docs.engine import DesignTokenDocsEngine


pytestmark = [pytest.mark.core, pytest.mark.runtime]


def _make_project(tmp_path: Path) -> Path:
    (tmp_path / "src").mkdir(parents=True, exist_ok=True)
    return tmp_path


def _sample_tokens() -> dict:
    return {
        "colors": {
            "background": {
                "hex": "#0d0d14",
                "rgb": "rgb(13, 13, 20)",
                "css_var": "--background",
                "contexts": ["BlockchainSection"],
                "is_alpha": False,
            },
            "primary": {
                "hex": "#3b82f6",
                "rgb": "rgb(59, 130, 246)",
                "css_var": "--primary",
                "contexts": ["CtaButton", "Link"],
                "is_alpha": False,
            },
        },
        "fonts": {"Inter": "sans"},
        "font_sizes": {"16": "base", "48": "5xl"},
        "font_weights": {"400": "normal", "700": "bold"},
        "line_heights": {},
        "style_token_map": {"Fill/Brand": "primary"},
        "variable_token_map": {"Color/Background": "background"},
        "exact_token_paths": ["colors.background", "colors.primary"],
    }


def test_config_from_dict_defaults():
    cfg = DesignTokenDocsConfig.from_dict({})
    assert cfg.title == "Design Tokens"
    assert cfg.formats == ["markdown", "json"]
    assert cfg.markdown_filename == "DESIGN_TOKENS.md"


def test_config_validation_errors(tmp_path):
    cfg = DesignTokenDocsConfig.from_dict(
        {"target_dir": str(tmp_path / "missing"), "markdown_filename": "tokens.txt"}
    )
    errors = cfg.validate()
    assert any("target_dir" in e for e in errors)
    assert any("markdown_filename" in e for e in errors)


def test_engine_writes_markdown_and_json(tmp_path):
    root = _make_project(tmp_path)
    (root / "src" / "design_tokens.json").write_text(
        json.dumps(_sample_tokens()), encoding="utf-8"
    )
    cfg = DesignTokenDocsConfig.from_dict({"formats": ["markdown", "json"]})
    result = DesignTokenDocsEngine(root, cfg).run()
    assert not result.errors
    assert any("docs/DESIGN_TOKENS.md" in f for f in result.files_written)
    assert any("docs/design_tokens.docs.json" in f for f in result.files_written)

    md = (root / "docs" / "DESIGN_TOKENS.md").read_text(encoding="utf-8")
    assert "# Design Tokens" in md
    assert "| `background` |" in md
    assert "| `primary` |" in md
    assert "### Font sizes" in md

    payload = json.loads((root / "docs" / "design_tokens.docs.json").read_text(encoding="utf-8"))
    assert payload["title"] == "Design Tokens"
    assert "colors" in payload["sections"]
    assert "typography" in payload["sections"]


def test_engine_includes_component_registry(tmp_path):
    root = _make_project(tmp_path)
    (root / "src" / "design_tokens.json").write_text(
        json.dumps(_sample_tokens()), encoding="utf-8"
    )
    registry = {
        "version": "1.0",
        "components": {
            "btn-primary": {"name": "Button/Primary", "variants": ["size=sm", "size=lg"], "used_by": []},
        },
    }
    (root / "component_registry.json").write_text(json.dumps(registry), encoding="utf-8")
    result = DesignTokenDocsEngine(root).run()
    assert not result.errors
    md = (root / "docs" / "DESIGN_TOKENS.md").read_text(encoding="utf-8")
    assert "## Components" in md
    assert "Button/Primary" in md


def test_engine_html_format(tmp_path):
    root = _make_project(tmp_path)
    (root / "src" / "design_tokens.json").write_text(
        json.dumps(_sample_tokens()), encoding="utf-8"
    )
    cfg = DesignTokenDocsConfig.from_dict({"formats": ["html"]})
    result = DesignTokenDocsEngine(root, cfg).run()
    assert not result.errors
    assert any("docs/design_tokens.html" in f for f in result.files_written)
    html = (root / "docs" / "design_tokens.html").read_text(encoding="utf-8")
    assert "<h1>Design Tokens</h1>" in html
    assert "#0d0d14" in html


def test_engine_missing_source_error(tmp_path):
    root = _make_project(tmp_path)
    result = DesignTokenDocsEngine(root).run()
    assert any("no design_tokens.json" in e["reason"] for e in result.errors)
    assert not result.files_written


def test_engine_skips_overwrite_note(tmp_path):
    root = _make_project(tmp_path)
    (root / "src" / "design_tokens.json").write_text(
        json.dumps(_sample_tokens()), encoding="utf-8"
    )
    (root / "docs").mkdir(parents=True, exist_ok=True)
    (root / "docs" / "DESIGN_TOKENS.md").write_text("existing", encoding="utf-8")
    result = DesignTokenDocsEngine(root).run()
    assert not result.errors
    assert any("docs/DESIGN_TOKENS.md" in f for f in result.files_written)
    md = (root / "docs" / "DESIGN_TOKENS.md").read_text(encoding="utf-8")
    assert "# Design Tokens" in md


def test_engine_empty_colors_and_typography(tmp_path):
    root = _make_project(tmp_path)
    (root / "src" / "design_tokens.json").write_text(
        json.dumps({"fonts": {}, "font_sizes": {}, "font_weights": {}, "line_heights": {}}),
        encoding="utf-8",
    )
    result = DesignTokenDocsEngine(root).run()
    assert not result.errors
    payload = json.loads((root / "docs" / "design_tokens.docs.json").read_text(encoding="utf-8"))
    assert payload["sections"] == []
