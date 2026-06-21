"""Unit tests for figma-agent-core/design_tokens.py.

Loads the module via importlib because the directory name contains a hyphen.
"""

from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent
DESIGN_TOKENS_PATH = ROOT / "figma-agent-core" / "design_tokens.py"
FIXTURES = ROOT / "tests" / "figma" / "fixtures"


def _load_design_tokens() -> Any:
    spec = importlib.util.spec_from_file_location("figma_design_tokens", str(DESIGN_TOKENS_PATH))
    module = importlib.util.module_from_spec(spec)
    sys.modules["figma_design_tokens"] = module
    spec.loader.exec_module(module)
    return module


design_tokens = _load_design_tokens()


def load_complex_fixture() -> dict:
    return json.loads((FIXTURES / "complex_layout.json").read_text(encoding="utf-8"))


def test_module_loads() -> None:
    assert hasattr(design_tokens, "FigmaTokenExtractor")
    assert hasattr(design_tokens, "generate_artifacts")


def test_extracts_expected_color_tokens() -> None:
    fixture = load_complex_fixture()
    registry = design_tokens.FigmaTokenExtractor(fixture).extract()

    assert "foreground" in registry.colors
    assert "background" in registry.colors
    assert "primary" in registry.colors
    assert "secondary" in registry.colors
    assert "muted" in registry.colors
    assert "destructive" in registry.colors
    assert "border" in registry.colors

    # Verify heuristic assignments against the known fixture palette.
    assert registry.colors["foreground"].hex == "#1a1a1f"
    assert registry.colors["background"].hex == "#ffffff"
    assert registry.colors["primary"].hex == "#3b82f5"
    assert registry.colors["secondary"].hex == "#334c66"
    assert registry.colors["muted"].hex == "#66666e"
    assert registry.colors["destructive"].hex == "#f04242"


def test_extracts_typography_tokens() -> None:
    fixture = load_complex_fixture()
    registry = design_tokens.FigmaTokenExtractor(fixture).extract()

    assert registry.fonts == {"Inter": "sans"}
    assert set(registry.font_sizes.keys()) == {12, 14, 16, 18, 22, 24, 56}
    assert set(registry.font_weights.keys()) == {400, 500, 600, 700}


def test_explicit_styles_override_heuristics() -> None:
    fixture = json.loads((FIXTURES / "tokens_explicit.json").read_text(encoding="utf-8"))
    registry = design_tokens.FigmaTokenExtractor(fixture).extract()

    assert registry.colors["background"].hex == "#ffffff"
    assert registry.colors["foreground"].hex == "#1a1a1f"
    assert registry.colors["primary"].hex == "#3b82f5"
    assert registry.colors["secondary"].hex == "#334c66"
    assert registry.colors["muted"].hex == "#66666e"
    assert registry.colors["destructive"].hex == "#f04242"
    assert registry.colors["border"].hex == "#e6ebf2"


def test_generates_tailwind_config_with_css_variables() -> None:
    fixture = load_complex_fixture()
    registry = design_tokens.FigmaTokenExtractor(fixture).extract()
    config = design_tokens.generate_tailwind_config(registry)

    assert 'import type { Config } from "tailwindcss";' in config
    assert '"primary": {' in config
    assert '"DEFAULT": "var(--primary)"' in config
    assert '"foreground": "var(--primary-foreground)"' in config
    assert '"background": "var(--background)"' in config
    assert '"fontFamily": {' in config


def test_generates_globals_css_with_root_variables() -> None:
    fixture = load_complex_fixture()
    registry = design_tokens.FigmaTokenExtractor(fixture).extract()
    css = design_tokens.generate_globals_css(registry)

    assert "@tailwind base;" in css
    assert ":root {" in css
    assert "--background: #ffffff;" in css
    assert "--foreground: #1a1a1f;" in css
    assert "--primary: #3b82f5;" in css
    assert "--font-sans: 'Inter'" in css
    assert "body {" in css
    assert "@apply bg-background text-foreground;" in css


def test_generate_artifacts_writes_files() -> None:
    fixture = load_complex_fixture()
    with tempfile.TemporaryDirectory() as tmp:
        artifacts = design_tokens.generate_artifacts(
            fixture,
            output_dir=tmp,
            registry_file="design_tokens.json",
            tailwind_config="tailwind.config.ts",
            globals_css="app/globals.css",
        )
        assert Path(artifacts["registry"]).exists()
        assert Path(artifacts["tailwind_config"]).exists()
        assert Path(artifacts["globals_css"]).exists()

        saved = json.loads(Path(artifacts["registry"]).read_text(encoding="utf-8"))
        assert "colors" in saved
        assert "fonts" in saved
