"""Unit tests for the PatchApplier diff engine."""

from __future__ import annotations

import pytest

from runtime.code_review.diff_engine import Patch, PatchApplier


class TestPatchApplierApply:
    def test_apply_single_patch(self):
        applier = PatchApplier()
        codebase = {"main.py": "print('hello')\n"}
        patches = [Patch(file="main.py", old="print('hello')", new="print('world')")]
        result, statuses = applier.apply(patches, codebase)

        assert result["main.py"] == "print('world')\n"
        assert len(statuses) == 1
        assert statuses[0].applied is True
        assert "Applied" in statuses[0].message

    def test_apply_multiple_patches_to_same_file(self):
        applier = PatchApplier()
        codebase = {"app.py": "a = 1\nb = 2\n"}
        patches = [
            Patch(file="app.py", old="a = 1", new="a = 10"),
            Patch(file="app.py", old="b = 2", new="b = 20"),
        ]
        result, statuses = applier.apply(patches, codebase)

        assert result["app.py"] == "a = 10\nb = 20\n"
        assert all(s.applied for s in statuses)

    def test_apply_patch_to_missing_file_fails(self):
        applier = PatchApplier()
        patches = [Patch(file="missing.py", old="x", new="y")]
        result, statuses = applier.apply(patches, {"other.py": "z"})

        assert statuses[0].applied is False
        assert "not found" in statuses[0].message
        assert "missing.py" not in result

    def test_apply_patch_with_missing_fragment_fails(self):
        applier = PatchApplier()
        patches = [Patch(file="main.py", old="missing", new="replacement")]
        result, statuses = applier.apply(patches, {"main.py": "content"})

        assert statuses[0].applied is False
        assert "Fragment not found" in statuses[0].message
        assert result["main.py"] == "content"

    def test_apply_patch_with_ambiguous_fragment_fails(self):
        applier = PatchApplier()
        codebase = {"main.py": "foo\nfoo\n"}
        patches = [Patch(file="main.py", old="foo", new="bar")]
        result, statuses = applier.apply(patches, codebase)

        assert statuses[0].applied is False
        assert "Ambiguous" in statuses[0].message
        assert result["main.py"] == "foo\nfoo\n"

    def test_apply_leaves_original_codebase_unchanged(self):
        applier = PatchApplier()
        codebase = {"main.py": "print('hello')\n"}
        patches = [Patch(file="main.py", old="print('hello')", new="print('world')")]
        result, _ = applier.apply(patches, codebase)

        assert codebase["main.py"] == "print('hello')\n"
        assert result["main.py"] == "print('world')\n"


class TestPatchApplierDictPatches:
    def test_apply_dict_patches(self):
        applier = PatchApplier()
        codebase = {"main.py": "x = 1\n"}
        patches = [{"file": "main.py", "old": "x = 1", "new": "x = 2"}]
        result, statuses = applier.apply_dict_patches(patches, codebase)

        assert result["main.py"] == "x = 2\n"
        assert statuses[0]["applied"] is True


class TestPatchModel:
    def test_patch_defaults(self):
        patch = Patch(file="a.py", old="x", new="y")
        assert patch.file == "a.py"
        assert patch.old == "x"
        assert patch.new == "y"
