"""Tests for PatchApplier deterministic patch application."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from runtime.code_review.diff_engine import Patch, PatchApplier


pytestmark = [pytest.mark.core, pytest.mark.runtime]


@pytest.fixture
def applier():
    return PatchApplier()


def test_apply_simple_patch(applier):
    codebase = {"main.py": "x = 1\ny = 2\n"}
    patches = [Patch(file="main.py", old="x = 1", new="x = 42")]
    result, statuses = applier.apply(patches, codebase)
    assert result["main.py"] == "x = 42\ny = 2\n"
    assert statuses[0].applied is True
    assert "Applied" in statuses[0].message


def test_apply_missing_file(applier):
    codebase = {"main.py": "x = 1\n"}
    patches = [Patch(file="missing.py", old="x = 1", new="x = 42")]
    result, statuses = applier.apply(patches, codebase)
    assert result == codebase
    assert statuses[0].applied is False
    assert "not found" in statuses[0].message


def test_apply_fragment_not_found(applier):
    codebase = {"main.py": "x = 1\n"}
    patches = [Patch(file="main.py", old="z = 9", new="z = 99")]
    result, statuses = applier.apply(patches, codebase)
    assert result == codebase
    assert statuses[0].applied is False
    assert "Fragment not found" in statuses[0].message


def test_apply_ambiguous_fragment(applier):
    codebase = {"main.py": "a = 1\nb = 2\na = 1\n"}
    patches = [Patch(file="main.py", old="a = 1", new="a = 99")]
    result, statuses = applier.apply(patches, codebase)
    assert statuses[0].applied is False
    assert "Ambiguous" in statuses[0].message


def test_apply_multiple_patches(applier):
    codebase = {"a.py": "x = 1\n", "b.py": "y = 2\n"}
    patches = [
        Patch(file="a.py", old="x = 1", new="x = 10"),
        Patch(file="b.py", old="y = 2", new="y = 20"),
    ]
    result, statuses = applier.apply(patches, codebase)
    assert result["a.py"] == "x = 10\n"
    assert result["b.py"] == "y = 20\n"
    assert all(s.applied for s in statuses)


def test_apply_dict_patches_wrapper(applier):
    codebase = {"main.py": "x = 1\n"}
    raw = [{"file": "main.py", "old": "x = 1", "new": "x = 42"}]
    result, statuses = applier.apply_dict_patches(raw, codebase)
    assert result["main.py"] == "x = 42\n"
    assert statuses[0]["applied"] is True
    assert statuses[0]["patch"]["file"] == "main.py"


def test_apply_does_not_mutate_input(applier):
    codebase = {"main.py": "x = 1\n"}
    patches = [Patch(file="main.py", old="x = 1", new="x = 42")]
    applier.apply(patches, codebase)
    assert codebase["main.py"] == "x = 1\n"
