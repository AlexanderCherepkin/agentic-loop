"""Tests for runtime/pwa engine and config."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from runtime.pwa.config import PwaConfig
from runtime.pwa.engine import PwaEngine


pytestmark = [pytest.mark.core, pytest.mark.runtime]


def _make_project(tmp_path: Path) -> Path:
    (tmp_path / "package.json").write_text('{"name":"demo"}', encoding="utf-8")
    (tmp_path / "src").mkdir(parents=True, exist_ok=True)
    (tmp_path / "app").mkdir(parents=True, exist_ok=True)
    (tmp_path / "public").mkdir(parents=True, exist_ok=True)
    return tmp_path


def test_pwa_config_from_dict_defaults():
    cfg = PwaConfig.from_dict({})
    assert cfg.name == "Generated Site"
    assert cfg.display == "standalone"
    assert cfg.image_srcset_enabled is True
    assert cfg.font_subsetting_enabled is True
    assert cfg.budget["max_js_kib"] == 250


def test_pwa_config_validation_errors():
    cfg = PwaConfig.from_dict({"theme_color": "red", "icons": []})
    errors = cfg.validate()
    assert any("theme_color" in e for e in errors)
    assert any("icon" in e for e in errors)


def test_pwa_engine_writes_manifest_and_sw(tmp_path):
    root = _make_project(tmp_path)
    cfg = PwaConfig.from_dict({"name": "My App", "short_name": "MyApp"})
    result = PwaEngine(root, cfg).run()
    assert not result.errors
    assert any("public/manifest.json" in f for f in result.files_written)
    assert any("public/sw.js" in f for f in result.files_written)
    assert any("public/offline.html" in f for f in result.files_written)
    assert any("src/lib/pwa.ts" in f for f in result.files_written)
    assert any("src/lib/pwa-meta.ts" in f for f in result.files_written)
    assert any("src/components/PwaRegister.tsx" in f for f in result.files_written)

    manifest = json.loads((root / "public" / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["name"] == "My App"
    assert manifest["display"] == "standalone"


def test_pwa_engine_validates_missing_package(tmp_path):
    cfg = PwaConfig.from_dict({})
    result = PwaEngine(tmp_path, cfg).run()
    assert any("package.json" in e["reason"] for e in result.errors)


def test_pwa_engine_budget_violations(tmp_path):
    root = _make_project(tmp_path)
    # Write a huge JS file to exceed default 250 KiB budget.
    (root / "src" / "big.ts").write_text("const x = " + "'x' + " * 200_000 + "'x';\n", encoding="utf-8")
    cfg = PwaConfig.from_dict({"budget": {"max_js_kib": 100}})
    result = PwaEngine(root, cfg).run()
    assert any(v["type"] == "js" for v in result.budget_violations)


def test_pwa_engine_no_budget_violations_when_budget_disabled(tmp_path):
    root = _make_project(tmp_path)
    (root / "src" / "big.ts").write_text("const x = " + "'x' + " * 200_000 + "'x';\n", encoding="utf-8")
    cfg = PwaConfig.from_dict({"budget": {"max_js_kib": None}})
    result = PwaEngine(root, cfg).run()
    assert not any(v["type"] == "js" for v in result.budget_violations)


def test_pwa_engine_suggests_srcset_for_images(tmp_path):
    root = _make_project(tmp_path)
    (root / "app" / "page.tsx").write_text(
        'export default function Page() { return <img src="/a.jpg" alt="A" />; }\n',
        encoding="utf-8",
    )
    result = PwaEngine(root, PwaConfig()).run()
    assert any("srcSet" in n for n in result.notes)


def test_pwa_engine_suggests_font_subsetting(tmp_path):
    root = _make_project(tmp_path)
    (root / "src" / "fonts.ts").write_text(
        "import { Inter } from 'next/font/google';\nexport const inter = Inter({ subsets: ['latin'] });\n",
        encoding="utf-8",
    )
    result = PwaEngine(root, PwaConfig()).run()
    # Already has subsets so no note expected.
    assert not any("subsets" in n for n in result.notes)


def test_pwa_engine_notes_missing_font_subsetting(tmp_path):
    root = _make_project(tmp_path)
    (root / "src" / "fonts.ts").write_text(
        "import { Inter } from 'next/font/google';\nexport const inter = Inter({});\n",
        encoding="utf-8",
    )
    result = PwaEngine(root, PwaConfig()).run()
    assert any("subsets" in n for n in result.notes)


def test_pwa_engine_updates_next_config(tmp_path):
    root = _make_project(tmp_path)
    (root / "next.config.js").write_text("module.exports = {};\n", encoding="utf-8")
    result = PwaEngine(root, PwaConfig()).run()
    assert any("next.config.js" in f for f in result.files_modified)
    text = (root / "next.config.js").read_text(encoding="utf-8")
    assert "pwa-config-start" in text
    assert "poweredByHeader" in text


def test_pwa_engine_idempotent_next_config(tmp_path):
    root = _make_project(tmp_path)
    (root / "next.config.js").write_text("module.exports = {};\n", encoding="utf-8")
    PwaEngine(root, PwaConfig()).run()
    PwaEngine(root, PwaConfig.from_dict({"name": "Renamed"})).run()
    text = (root / "next.config.js").read_text(encoding="utf-8")
    assert text.count("pwa-config-start") == 1
    assert text.count("pwa-config-end") == 1
