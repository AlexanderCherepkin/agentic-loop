"""Shared path resolution helper for MCP servers.

Wraps runtime.safety.file_system_guard so every server that touches files
can fail-closed on path traversal / partial traversal attempts.
"""
from __future__ import annotations

from pathlib import Path

from runtime.safety.file_system_guard import FileSystemGuard, FSOperation, FSVerdict


class MCPPathGuard:
    """Resolve user-supplied paths strictly inside a workspace root."""

    def __init__(self, workspace_root: str | Path):
        self.workspace = Path(workspace_root).resolve()
        self._guard = FileSystemGuard(self.workspace)

    def resolve(self, path: str, operation: FSOperation = FSOperation.READ) -> Path:
        """Return normalized absolute path or raise PermissionError."""
        result = self._guard.check(path, operation)
        if result.verdict != FSVerdict.ALLOWED:
            raise PermissionError(f"Access denied: {path} is outside workspace")
        if not result.normalized_path:
            raise PermissionError(f"Access denied: {path} could not be resolved")
        return Path(result.normalized_path)

    def read_path(self, path: str) -> Path:
        return self.resolve(path, FSOperation.READ)

    def write_path(self, path: str) -> Path:
        return self.resolve(path, FSOperation.WRITE)
