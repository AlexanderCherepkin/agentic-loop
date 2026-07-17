"""Tests for the Tailwind config adapter."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

from runtime.premium_design import DtcgTokenEngine, TailwindConfigAdapter, generate_tailwind_from_tokens


@pytest.fixture
def sample_tokens():
    engine = DtcgTokenEngine()
    result = engine.generate(
        "SaaS dashboard для AI API", variance=0.5, density=0.0, motion=0.0
    )
    return result.tokens


def test_adapter_builds_css_variables(sample_tokens):
    adapter = TailwindConfigAdapter(tokens=sample_tokens)
    result = adapter.generate()
    assert result.ok
    css = TailwindConfigAdapter._render_globals_css(
        adapter._build_css_variables(sample_tokens)
    )
    assert "--color-primary" in css
    assert "--font-body" in css


def test_adapter_generates_files(sample_tokens):
    adapter = TailwindConfigAdapter(tokens=sample_tokens)
    with tempfile.TemporaryDirectory() as tmp:
        tw_path = Path(tmp) / "tailwind.config.ts"
        css_path = Path(tmp) / "globals.css"
        result = adapter.generate(
            tailwind_output=tw_path,
            css_output=css_path,
        )
        assert result.ok
        assert tw_path.exists()
        assert css_path.exists()

        tw_text = tw_path.read_text(encoding="utf-8")
        assert "import type { Config }" in tw_text
        assert "var(--color-primary)" in tw_text
        assert "var(--font-body)" in tw_text

        css_text = css_path.read_text(encoding="utf-8")
        assert ":root {" in css_text
        assert "--color-primary:" in css_text


def test_adapter_detects_slop_and_blocks_in_strict_mode():
    bad_tokens = {
        "color": {
            "primary": {"$value": "#000000", "$type": "color"},
            "muted": {"$value": "#777777", "$type": "color"},
        },
        "fontFamily": {
            "body": {"$value": "'Inter', sans-serif", "$type": "fontFamily"}
        },
        "spacing": {
            "sm": {"$value": "8px", "$type": "dimension"},
            "md": {"$value": "10px", "$type": "dimension"},
        },
        "shadow": {
            "card": {"$value": "0 4px 6px rgba(0,0,0,0.1)", "$type": "shadow"},
        },
        "motion": {
            "duration": {},
            "allowed_properties": {
                "$value": ["width", "transform"],
                "$type": "stringArray",
            },
        },
    }
    adapter = TailwindConfigAdapter(tokens=bad_tokens)
    with tempfile.TemporaryDirectory() as tmp:
        result = adapter.generate(
            tailwind_output=Path(tmp) / "tailwind.config.ts",
            strict=True,
        )
        assert not result.ok
        assert result.tailwind_path is None
        rules = {v["rule"] for v in result.violations}
        assert "forbidden_font" in rules
        assert "flat_gray_on_white" in rules
        assert "generic_shadow" in rules
        assert "uniform_padding" in rules
        assert "layout_animation" in rules


def test_adapter_allows_slop_in_non_strict_mode():
    bad_tokens = {
        "color": {
            "primary": {"$value": "#000000", "$type": "color"},
        },
        "fontFamily": {
            "body": {"$value": "'Inter', sans-serif", "$type": "fontFamily"}
        },
    }
    adapter = TailwindConfigAdapter(tokens=bad_tokens)
    with tempfile.TemporaryDirectory() as tmp:
        result = adapter.generate(
            tailwind_output=Path(tmp) / "tailwind.config.ts",
            css_output=Path(tmp) / "globals.css",
            strict=False,
        )
        assert result.tailwind_path.exists()
        assert result.css_path.exists()
        assert result.violations


def test_adapter_patches_existing_config(sample_tokens):
    adapter = TailwindConfigAdapter(tokens=sample_tokens)
    with tempfile.TemporaryDirectory() as tmp:
        tw_path = Path(tmp) / "tailwind.config.ts"
        tw_path.write_text(
            '''import type { Config } from "tailwindcss";\n\nconst config: Config = {\n  content: ["./src/**/*.{js,ts,jsx,tsx}"],\n  theme: {\n    extend: {\n      colors: {\n        legacy: "#123456"\n      }\n    }\n  },\n  plugins: []\n};\n\nexport default config;\n''',
            encoding="utf-8",
        )
        result = adapter.generate(
            tailwind_output=tw_path,
            patch_existing=True,
        )
        assert result.ok
        text = tw_path.read_text(encoding="utf-8")
        assert "legacy" in text  # preserved
        assert "var(--color-primary)" in text


def test_generate_tailwind_from_tokens_wrapper(sample_tokens):
    with tempfile.TemporaryDirectory() as tmp:
        tokens_path = Path(tmp) / "design_tokens.json"
        tokens_path.write_text(json.dumps(sample_tokens), encoding="utf-8")
        result = generate_tailwind_from_tokens(
            tokens_path=tokens_path,
            tailwind_output=Path(tmp) / "tailwind.config.ts",
            css_output=Path(tmp) / "globals.css",
        )
        assert result.ok
        assert result.tailwind_path.exists()
        assert result.css_path.exists()


def test_cli_runs_successfully():
    engine = DtcgTokenEngine()
    tokens = engine.generate("Fashion editorial", variance=0.3, density=0.0).tokens
    with tempfile.TemporaryDirectory() as tmp:
        tokens_path = Path(tmp) / "design_tokens.json"
        tokens_path.write_text(json.dumps(tokens), encoding="utf-8")
        tw_path = Path(tmp) / "tailwind.config.ts"
        css_path = Path(tmp) / "globals.css"

        result = subprocess.run(
            [
                sys.executable,
                "scripts/generate_tailwind_config.py",
                "--input",
                str(tokens_path),
                "--output",
                str(tw_path),
                "--css-output",
                str(css_path),
                "--verbose",
            ],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, result.stderr
        assert tw_path.exists()
        assert css_path.exists()
        assert "OK" in result.stdout


def test_cli_fails_on_slop_in_strict_mode():
    bad_tokens = {
        "color": {
            "primary": {"$value": "#000000", "$type": "color"},
        },
        "fontFamily": {
            "body": {"$value": "'Inter', sans-serif", "$type": "fontFamily"}
        },
    }
    with tempfile.TemporaryDirectory() as tmp:
        tokens_path = Path(tmp) / "design_tokens.json"
        tokens_path.write_text(json.dumps(bad_tokens), encoding="utf-8")
        tw_path = Path(tmp) / "tailwind.config.ts"

        result = subprocess.run(
            [
                sys.executable,
                "scripts/generate_tailwind_config.py",
                "--input",
                str(tokens_path),
                "--output",
                str(tw_path),
                "--strict",
            ],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 1
        assert "Anti-Slop violations" in result.stderr
        assert not tw_path.exists()
