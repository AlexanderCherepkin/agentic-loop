"""Tests for runtime/loop_presets YAML files."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))


PRESETS_DIR = Path(__file__).resolve().parent.parent.parent / "runtime" / "loop_presets"
PRESET_FILES = list(PRESETS_DIR.glob("*.yaml")) if PRESETS_DIR.is_dir() else []

REQUIRED_KEYS = [
    "goal",
    "max_iterations",
    "trust_level",
    "schedule",
    "verification_plan",
    "human_zones",
    "exit_conditions",
]

pytestmark = [pytest.mark.core, pytest.mark.runtime]


@pytest.mark.skipif(not PRESET_FILES, reason="No loop preset YAML files found")
@pytest.mark.parametrize("preset_path", PRESET_FILES, ids=lambda p: p.stem)
def test_preset_has_required_keys(preset_path: Path) -> None:
    with open(preset_path, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    assert data, f"{preset_path.name} is empty or invalid YAML"
    for key in REQUIRED_KEYS:
        assert key in data, f"{preset_path.name} missing required key: {key}"


def test_at_least_four_presets_exist() -> None:
    if not PRESETS_DIR.is_dir():
        pytest.skip(f"Presets directory not found: {PRESETS_DIR}")
    assert len(PRESET_FILES) >= 4, f"Expected at least 4 presets, found {len(PRESET_FILES)}"
