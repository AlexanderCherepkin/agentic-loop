"""Tests for ProjectStarterEngine and TemplateManager (deterministic, no LLM)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from runtime.project_starter import ProjectStarterEngine, TemplateManager, TemplatePreset
from runtime.project_starter.config import ProjectStarterConfig


pytestmark = [pytest.mark.core, pytest.mark.runtime]


def _make_preset_dir(tmp_path: Path, preset_id: str, language: str = "python") -> Path:
    preset_dir = tmp_path / preset_id
    preset_dir.mkdir(parents=True)
    (preset_dir / "files").mkdir()
    meta = {
        "id": preset_id,
        "name": f"Preset {preset_id}",
        "description": "A test preset.",
        "base_category": "SaaS",
        "language": language,
        "stack": {"framework": "fastapi"},
        "variables": {"API_KEY": "change-me"},
    }
    (preset_dir / "preset.yaml").write_text(yaml.safe_dump(meta), encoding="utf-8")
    (preset_dir / "files" / "main.py").write_text("print('hello')", encoding="utf-8")
    return preset_dir


@pytest.fixture
def populated_manager(tmp_path):
    templates_dir = tmp_path / "templates"
    _make_preset_dir(templates_dir, "saas-python")
    _make_preset_dir(templates_dir, "saas-typescript", language="typescript")
    cfg = ProjectStarterConfig(templates_dir=templates_dir)
    return TemplateManager(cfg)


def test_template_manager_discovers_presets(populated_manager):
    assert len(populated_manager.presets) == 2
    assert "saas-python" in populated_manager.presets


def test_template_manager_list_presets(populated_manager):
    summaries = populated_manager.list_presets()
    assert len(summaries) == 2
    ids = {s["id"] for s in summaries}
    assert ids == {"saas-python", "saas-typescript"}
    assert summaries[0]["files_count"] == 1


def test_template_manager_get_preset(populated_manager):
    preset = populated_manager.get_preset("saas-python")
    assert preset is not None
    assert preset.name == "Preset saas-python"


def test_template_manager_get_preset_none_for_missing(populated_manager):
    assert populated_manager.get_preset("missing") is None


def test_template_manager_get_preset_files(populated_manager):
    files = populated_manager.get_preset_files("saas-python")
    assert "main.py" in files
    assert files["main.py"] == "print('hello')"


def test_template_manager_build_context(populated_manager):
    context = populated_manager.build_context("saas-python")
    assert context is not None
    assert context["id"] == "saas-python"
    assert "main.py" in context["files"]


def test_template_manager_apply_merges_generated(populated_manager):
    generated = {"README.md": "# Custom"}
    merged = populated_manager.apply("saas-python", generated)
    assert merged["README.md"] == "# Custom"
    assert merged["main.py"] == "print('hello')"


def test_template_manager_detect_language_python():
    cfg = ProjectStarterConfig(language_auto_detect_enabled=True)
    manager = TemplateManager(cfg)
    assert manager.detect_language("Build a fastapi service") == "python"


def test_template_manager_detect_language_typescript():
    cfg = ProjectStarterConfig(language_auto_detect_enabled=True)
    manager = TemplateManager(cfg)
    assert manager.detect_language("nextjs react app") == "typescript"


def test_template_manager_detect_language_disabled():
    cfg = ProjectStarterConfig(language_auto_detect_enabled=False)
    manager = TemplateManager(cfg)
    assert manager.detect_language("fastapi service") is None


def test_template_manager_find_match_by_category(populated_manager):
    classification = {"project_type": {"base_category": "SaaS"}}
    preset_id = populated_manager.find_match(classification, language="python")
    assert preset_id == "saas-python"


def test_template_manager_find_match_fallback_language(populated_manager):
    classification = {"project_type": {"base_category": "SaaS"}}
    preset_id = populated_manager.find_match(classification, language="go")
    assert preset_id in {"saas-python", "saas-typescript"}


def test_template_manager_find_match_none_without_base_category(populated_manager):
    assert populated_manager.find_match({}) is None


def test_template_manager_format_prompt_context_static():
    context = {"id": "x", "name": "X"}
    text = TemplateManager.format_prompt_context_static(context)
    assert "PROJECT STARTER TEMPLATE" in text
    assert '"id": "x"' in text


def test_project_starter_build_package(populated_manager):
    engine = ProjectStarterEngine(populated_manager.config)
    engine.manager = populated_manager
    classification = {"project_type": {"base_category": "SaaS"}}
    result = engine.build_package("saas brief", classification=classification, language="python")
    assert result.template_id == "saas-python"
    assert result.language == "python"
    assert any(f["path"] == "main.py" for f in result.files)
    assert "pip install" in result.commands[0]
    assert "API_KEY=change-me" in result.env_example
    assert result.confidence == 0.9


def test_project_starter_no_preset_returns_low_confidence(populated_manager):
    engine = ProjectStarterEngine(populated_manager.config)
    engine.manager = populated_manager
    classification = {"project_type": {"base_category": "Unknown"}}
    result = engine.build_package("unknown brief", classification=classification)
    assert result.confidence == 0.5
    assert "No matching starter preset" in result.missing_inputs[0]


def test_project_starter_derive_commands_django():
    engine = ProjectStarterEngine()
    preset = TemplatePreset(
        id="django",
        name="Django",
        language="python",
        stack={"framework": "django"},
    )
    commands = engine._derive_commands(preset)
    assert commands[0] == "pip install -r requirements.txt"
    assert "migrate" in commands[1]


def test_project_starter_derive_commands_typescript():
    engine = ProjectStarterEngine()
    preset = TemplatePreset(
        id="next",
        name="Next.js",
        language="typescript",
        stack={"framework": "nextjs"},
    )
    commands = engine._derive_commands(preset)
    assert commands == ["npm install", "npm run dev"]


def test_project_starter_build_readme_and_env():
    engine = ProjectStarterEngine()
    preset = TemplatePreset(
        id="x",
        name="X",
        stack={"language": "python"},
        variables={"DEBUG": "True"},
    )
    readme = engine._build_readme(preset)
    env = engine._build_env_example(preset)
    assert "# X" in readme
    assert "DEBUG=True" in env
