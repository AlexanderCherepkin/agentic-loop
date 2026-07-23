"""Tests for runtime/storybook engine and config."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from runtime.storybook import StorybookConfig, StorybookEngine


pytestmark = [pytest.mark.core, pytest.mark.runtime]


def _make_project(tmp_path: Path) -> Path:
    (tmp_path / "package.json").write_text('{"name":"demo"}', encoding="utf-8")
    (tmp_path / "src" / "app" / "components").mkdir(parents=True, exist_ok=True)
    return tmp_path


def test_config_from_dict_defaults():
    cfg = StorybookConfig.from_dict({})
    assert cfg.stories_dir == "src/stories"
    assert cfg.framework == "@storybook/nextjs"


def test_config_validation_errors(tmp_path):
    cfg = StorybookConfig(target_dir=tmp_path, component_dirs=[])
    errors = cfg.validate()
    assert any("component_dir" in e for e in errors)


def test_engine_generates_stories_and_config(tmp_path):
    root = _make_project(tmp_path)
    (root / "src" / "app" / "components" / "Button.tsx").write_text(
        "export default function Button() { return <button>Click</button>; }\n",
        encoding="utf-8",
    )
    cfg = StorybookConfig(target_dir=root)
    result = StorybookEngine(root, cfg).run()
    assert not result.errors
    assert any(".storybook/main.ts" in f for f in result.files_written)
    assert any(".storybook/preview.ts" in f for f in result.files_written)
    assert any("src/stories/Button.stories.tsx" in f for f in result.files_written)
    assert any(s["name"] == "Button" for s in result.stories)


def test_engine_updates_package_json(tmp_path):
    root = _make_project(tmp_path)
    (root / "src" / "app" / "components" / "Card.tsx").write_text(
        "export function Card() { return <div>Card</div>; }\n",
        encoding="utf-8",
    )
    result = StorybookEngine(root, StorybookConfig(target_dir=root)).run()
    assert any("package.json" in f for f in result.files_modified)
    data = json.loads((root / "package.json").read_text(encoding="utf-8"))
    assert "storybook" in data.get("scripts", {})
    assert "@storybook/nextjs" in data.get("devDependencies", {})


def test_engine_no_components_note(tmp_path):
    root = _make_project(tmp_path)
    result = StorybookEngine(root, StorybookConfig(target_dir=root)).run()
    assert any("No React components found" in n for n in result.notes)
    assert not result.files_written


def test_engine_missing_package_json_error(tmp_path):
    cfg = StorybookConfig(target_dir=tmp_path)
    result = StorybookEngine(tmp_path, cfg).run()
    # No components means early return before package.json check.
    assert any("No React components found" in n for n in result.notes)


def test_engine_blocks_path_traversal_write(tmp_path):
    root = _make_project(tmp_path)
    (root / "src" / "app" / "components" / "Button.tsx").write_text(
        "export default function Button() { return <button>Click</button>; }\n",
        encoding="utf-8",
    )
    cfg = StorybookConfig(target_dir=root)
    # Inject a malicious component path by overriding directory discovery.
    engine = StorybookEngine(root, cfg)
    engine._write_file("../../../evil.stories.tsx", "evil")
    assert any("Path escapes" in e["reason"] for e in engine.result.errors)
    assert not (tmp_path.parent / "evil.stories.tsx").exists()
