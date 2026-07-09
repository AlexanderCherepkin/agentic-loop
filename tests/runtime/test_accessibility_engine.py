"""Tests for runtime/accessibility engine and config."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from runtime.accessibility.config import AccessibilityConfig, CheckType, WcagLevel
from runtime.accessibility.engine import AccessibilityEngine, contrast_ratio


pytestmark = [pytest.mark.core, pytest.mark.runtime]


def _make_project(tmp_path: Path) -> Path:
    (tmp_path / "package.json").write_text('{"name":"demo"}', encoding="utf-8")
    (tmp_path / "tailwind.config.ts").write_text(
        "export default { content: ['./src/**/*.{js,ts,jsx,tsx}'] };\n", encoding="utf-8"
    )
    (tmp_path / "app").mkdir(parents=True, exist_ok=True)
    (tmp_path / "app" / "globals.css").write_text(":root { --background: #ffffff; }\n", encoding="utf-8")
    return tmp_path


def test_low_contrast_classname_is_flagged(tmp_path):
    root = _make_project(tmp_path)
    (root / "app" / "page.tsx").write_text(
        'export default function Page() { return <p className="text-gray-400 bg-gray-200">Low</p>; }\n',
        encoding="utf-8",
    )
    engine = AccessibilityEngine(root, AccessibilityConfig())
    result = engine.run()
    violations = [v for v in result.issues if v.check == "contrast"]
    assert violations
    assert any("below" in v.message and "contrast" in v.message.lower() for v in violations)


def test_low_contrast_inline_style_is_flagged(tmp_path):
    root = _make_project(tmp_path)
    (root / "app" / "page.tsx").write_text(
        'export default function Page() { return <p style={{ color: "#cccccc", backgroundColor: "#ffffff" }}>Low</p>; }\n',
        encoding="utf-8",
    )
    engine = AccessibilityEngine(root, AccessibilityConfig())
    result = engine.run()
    violations = [v for v in result.issues if v.check == "contrast"]
    assert violations


def test_accessible_contrast_passes(tmp_path):
    root = _make_project(tmp_path)
    (root / "app" / "page.tsx").write_text(
        'export default function Page() { return <p className="text-gray-900 bg-white">Readable</p>; }\n',
        encoding="utf-8",
    )
    engine = AccessibilityEngine(root, AccessibilityConfig())
    result = engine.run()
    violations = [v for v in result.issues if v.check == "contrast"]
    assert not violations


def test_missing_focus_visible_on_button_is_flagged(tmp_path):
    root = _make_project(tmp_path)
    (root / "app" / "page.tsx").write_text(
        'export default function Page() { return <button className="px-4 py-2">Click</button>; }\n',
        encoding="utf-8",
    )
    engine = AccessibilityEngine(root, AccessibilityConfig())
    result = engine.run()
    violations = [v for v in result.issues if v.check == "focus_visible"]
    assert violations


def test_positive_tabindex_is_flagged(tmp_path):
    root = _make_project(tmp_path)
    (root / "app" / "page.tsx").write_text(
        'export default function Page() { return <div tabIndex={2}>Focus me</div>; }\n',
        encoding="utf-8",
    )
    engine = AccessibilityEngine(root, AccessibilityConfig())
    result = engine.run()
    violations = [v for v in result.issues if v.check == "focus_order"]
    assert violations
    assert any("tabIndex" in v.message for v in violations)


def test_invalid_aria_role_is_flagged(tmp_path):
    root = _make_project(tmp_path)
    (root / "app" / "page.tsx").write_text(
        'export default function Page() { return <div role="hedeer">Bad role</div>; }\n',
        encoding="utf-8",
    )
    config = AccessibilityConfig.from_dict({"checks": ["aria"]})
    result = AccessibilityEngine(root, config).run()
    violations = [v for v in result.issues if v.check == "aria"]
    assert any("Invalid ARIA role" in v.message for v in violations)


def test_required_aria_attr_for_role_is_flagged(tmp_path):
    root = _make_project(tmp_path)
    (root / "app" / "page.tsx").write_text(
        'export default function Page() { return <div role="checkbox">Unchecked</div>; }\n',
        encoding="utf-8",
    )
    config = AccessibilityConfig.from_dict({"checks": ["aria"]})
    result = AccessibilityEngine(root, config).run()
    violations = [v for v in result.issues if v.check == "aria"]
    assert any("aria-checked" in v.message for v in violations)


def test_duplicate_id_is_flagged(tmp_path):
    root = _make_project(tmp_path)
    (root / "app" / "page.tsx").write_text(
        'export default function Page() { return (<><div id="dup">A</div><div id="dup">B</div></>); }\n',
        encoding="utf-8",
    )
    config = AccessibilityConfig.from_dict({"checks": ["aria"]})
    result = AccessibilityEngine(root, config).run()
    violations = [v for v in result.issues if v.check == "aria"]
    assert any("Duplicate id" in v.message for v in violations)


def test_missing_aria_describedby_ref_is_flagged(tmp_path):
    root = _make_project(tmp_path)
    (root / "app" / "page.tsx").write_text(
        'export default function Page() { return <input aria-describedby="missing" />; }\n',
        encoding="utf-8",
    )
    config = AccessibilityConfig.from_dict({"checks": ["aria"]})
    result = AccessibilityEngine(root, config).run()
    violations = [v for v in result.issues if v.check == "aria"]
    assert any("missing id" in v.message for v in violations)


def test_missing_alt_on_img_is_flagged(tmp_path):
    root = _make_project(tmp_path)
    (root / "app" / "page.tsx").write_text(
        'export default function Page() { return <img src="/photo.jpg" />; }\n',
        encoding="utf-8",
    )
    engine = AccessibilityEngine(root, AccessibilityConfig())
    result = engine.run()
    violations = [v for v in result.issues if v.check == "alt_text"]
    assert violations


def test_keyboard_trap_custom_div_is_flagged(tmp_path):
    root = _make_project(tmp_path)
    (root / "app" / "page.tsx").write_text(
        'export default function Page() { return <div role="button" tabIndex={0} onClick={() => {}}>Act</div>; }\n',
        encoding="utf-8",
    )
    config = AccessibilityConfig.from_dict({"checks": ["keyboard_trap"]})
    result = AccessibilityEngine(root, config).run()
    violations = [v for v in result.issues if v.check == "keyboard_trap"]
    assert violations
    assert any("keyboard activation" in v.message for v in violations)


def test_keydown_without_escape_or_tab_is_flagged(tmp_path):
    root = _make_project(tmp_path)
    (root / "app" / "page.tsx").write_text(
        'export default function Page() { return <input onKeyDown={(e) => { if (e.key === "Enter") e.preventDefault(); }} />; }\n',
        encoding="utf-8",
    )
    config = AccessibilityConfig.from_dict({"checks": ["keyboard_trap"]})
    result = AccessibilityEngine(root, config).run()
    violations = [v for v in result.issues if v.check == "keyboard_trap"]
    assert violations


def test_skipped_heading_is_flagged(tmp_path):
    root = _make_project(tmp_path)
    (root / "app" / "page.tsx").write_text(
        'export default function Page() { return (<main><h1>Title</h1><h3>Subtitle</h3></main>); }\n',
        encoding="utf-8",
    )
    engine = AccessibilityEngine(root, AccessibilityConfig())
    result = engine.run()
    violations = [v for v in result.issues if v.check == "heading_hierarchy"]
    assert violations
    assert any("h1" in v.message and "h3" in v.message for v in violations)


def test_config_from_dict_defaults_to_aa():
    config = AccessibilityConfig.from_dict({})
    assert config.level == WcagLevel.WCAG21_AA
    assert CheckType.CONTRAST.value in config.checks
    assert config.contrast_threshold_normal == 4.5


def test_config_validation_rejects_empty_checks():
    config = AccessibilityConfig.from_dict({"checks": []})
    assert config.validate()


def test_contrast_ratio_calculation():
    assert contrast_ratio("#ffffff", "#000000") == 21.0
    assert contrast_ratio("#000000", "#000000") == 1.0
    assert contrast_ratio("#ffffff", "#ffffff") == 1.0


def test_report_passed_when_clean(tmp_path):
    root = _make_project(tmp_path)
    (root / "app" / "page.tsx").write_text(
        'export default function Page() { return <h1 className="text-gray-900 bg-white focus:outline-none">Hello</h1>; }\n',
        encoding="utf-8",
    )
    config = AccessibilityConfig.from_dict({
        "checks": ["contrast", "focus_visible", "focus_order", "aria", "keyboard_trap"]
    })
    result = AccessibilityEngine(root, config).run()
    assert result.passed
    assert result.score == 1.0
    assert result.duration_seconds >= 0
