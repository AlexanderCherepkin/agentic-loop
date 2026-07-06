from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from runtime.safety.file_system_guard import FSOperation, FSVerdict, FileSystemGuard, FileSystemGuardError


@pytest.fixture
def guard(tmp_path):
    return FileSystemGuard(workspace_root=str(tmp_path))


class TestFileSystemGuardWorkspace:
    def test_allows_workspace_read_and_write(self, guard, tmp_path):
        target = tmp_path / "some_file.txt"
        target.write_text("hello")

        read_result = guard.check(target, FSOperation.READ)
        write_result = guard.check(target, FSOperation.WRITE)

        assert read_result.verdict == FSVerdict.ALLOWED
        assert write_result.verdict == FSVerdict.ALLOWED
        assert read_result.normalized_path == str(target.resolve())

    def test_allows_relative_path_in_workspace(self, guard, tmp_path):
        (tmp_path / "nested").mkdir()
        rel = "nested/file.txt"
        result = guard.check(rel, FSOperation.WRITE)
        assert result.verdict == FSVerdict.ALLOWED
        assert result.normalized_path == str((tmp_path / "nested" / "file.txt").resolve())

    def test_blocks_write_outside_workspace(self, guard, tmp_path):
        outside = tmp_path.parent / "outside_file.txt"
        result = guard.check(str(outside), FSOperation.WRITE)
        assert result.verdict == FSVerdict.BLOCKED
        assert "outside allowed directories" in result.reason.lower()

    def test_read_outside_workspace_escalates_by_default(self, guard, tmp_path):
        outside = tmp_path.parent / "outside_file.txt"
        result = guard.check(str(outside), FSOperation.READ)
        assert result.verdict == FSVerdict.ESCALATE

    def test_read_outside_allowed_when_flag_set(self, guard, tmp_path):
        outside_guard = FileSystemGuard(workspace_root=str(tmp_path), allow_read_anywhere=True)
        outside = tmp_path.parent / "outside_file.txt"
        result = outside_guard.check(str(outside), FSOperation.READ)
        assert result.verdict == FSVerdict.ALLOWED

    def test_allows_extra_allowed_dir(self, tmp_path):
        extra = tmp_path / "extra"
        extra.mkdir()
        guard = FileSystemGuard(workspace_root=str(tmp_path / "ws"), allowed_dirs=[str(extra)])
        file_in_extra = extra / "data.txt"
        assert guard.check(str(file_in_extra), FSOperation.WRITE).verdict == FSVerdict.ALLOWED

    def test_assert_allowed_raises_when_blocked(self, guard, tmp_path):
        outside = tmp_path.parent / "blocked.txt"
        with pytest.raises(FileSystemGuardError) as exc_info:
            guard.assert_allowed(str(outside), FSOperation.WRITE)
        assert exc_info.value.result.verdict == FSVerdict.BLOCKED


class TestFileSystemGuardProtectedPaths:
    def test_blocks_dot_ssh_directory(self, guard, tmp_path):
        ssh = tmp_path / ".ssh" / "id_rsa"
        result = guard.check(str(ssh), FSOperation.READ)
        assert result.verdict == FSVerdict.BLOCKED
        assert ".ssh" in result.reason.lower() or "blocked component" in result.reason.lower()

    def test_blocks_dot_env_by_name(self, guard, tmp_path):
        env_file = tmp_path / ".env"
        result = guard.check(str(env_file), FSOperation.READ)
        assert result.verdict == FSVerdict.BLOCKED
        assert ".env" in result.reason.lower()

    def test_blocks_etc_passwd(self, guard):
        result = guard.check("/etc/passwd", FSOperation.READ)
        assert result.verdict == FSVerdict.BLOCKED
        assert "/etc/" in result.reason.lower() or "passwd" in result.reason.lower()

    @pytest.mark.skipif(sys.platform != "win32", reason="Windows-specific absolute path")
    def test_blocks_windows_system32(self, guard):
        result = guard.check(r"C:\Windows\System32\drivers\etc\hosts", FSOperation.READ)
        assert result.verdict == FSVerdict.BLOCKED
        assert "system32" in result.reason.lower()

    @pytest.mark.skipif(sys.platform == "win32", reason="POSIX-specific absolute path")
    def test_blocks_posix_etc_directory(self, guard):
        result = guard.check("/etc/passwd", FSOperation.READ)
        assert result.verdict == FSVerdict.BLOCKED
        assert "/etc/" in result.reason.lower()

    def test_blocks_path_traversal_to_etc(self, guard, tmp_path):
        traversal = str(tmp_path / ".." / ".." / "etc" / "passwd")
        result = guard.check(traversal, FSOperation.READ)
        assert result.verdict == FSVerdict.BLOCKED

    def test_blocks_protected_names_case_insensitive(self, guard, tmp_path):
        env_file = tmp_path / ".ENV"
        result = guard.check(str(env_file), FSOperation.READ)
        assert result.verdict == FSVerdict.BLOCKED


class TestFileSystemGuardOperations:
    def test_delete_inside_allowed_dir(self, guard, tmp_path):
        target = tmp_path / "delete_me.txt"
        target.write_text("x")
        result = guard.check(str(target), FSOperation.DELETE)
        assert result.verdict == FSVerdict.ALLOWED

    def test_delete_outside_blocked(self, guard, tmp_path):
        outside = tmp_path.parent / "dont_delete.txt"
        result = guard.check(str(outside), FSOperation.DELETE)
        assert result.verdict == FSVerdict.BLOCKED

    def test_execute_blocked_outside_allowed(self, guard, tmp_path):
        outside = tmp_path.parent / "script.py"
        result = guard.check(str(outside), FSOperation.EXECUTE)
        assert result.verdict == FSVerdict.BLOCKED

    def test_convenience_methods(self, guard, tmp_path):
        inside = tmp_path / "in.txt"
        outside = tmp_path.parent / "out.txt"
        assert guard.is_write_allowed(str(inside)) is True
        assert guard.is_write_allowed(str(outside)) is False
        assert guard.is_read_allowed(str(outside)) is True  # escalate still allows read-level check


class TestFileSystemGuardSerialization:
    def test_to_dict_includes_allowed_and_blocked_dirs(self, guard, tmp_path):
        data = guard.to_dict()
        assert data["workspace_root"] == str(tmp_path.resolve())
        assert any(str(tmp_path.resolve()) in d for d in data["allowed_dirs"])
        assert len(data["blocked_dirs"]) > 0
        assert ".ssh" in data["blocked_parts"]
