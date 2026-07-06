from __future__ import annotations

import os
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any


class FSOperation(str, Enum):
    READ = "read"
    WRITE = "write"
    DELETE = "delete"
    EXECUTE = "execute"


class FSVerdict(str, Enum):
    ALLOWED = "allowed"
    BLOCKED = "blocked"
    ESCALATE = "escalate"


@dataclass
class FSGuardResult:
    path: str
    operation: FSOperation
    verdict: FSVerdict
    reason: str = ""
    normalized_path: str | None = None
    allowed_dirs: list[str] = field(default_factory=list)
    blocked_dirs: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "operation": self.operation.value,
            "verdict": self.verdict.value,
            "reason": self.reason,
            "normalized_path": self.normalized_path,
            "allowed_dirs": self.allowed_dirs,
            "blocked_dirs": self.blocked_dirs,
        }


class FileSystemGuard:
    """Deterministic filesystem guardrail for the autonomous agent runtime.

    Enforces:
    - An explicit allow-list of directories the agent may touch (workspace + configured extras).
    - A block-list of sensitive paths (.ssh, .env, system directories, Windows system dirs).
    - Path-traversal detection: resolved path must be inside an allowed directory.
    - Per-operation gating: write/delete are stricter than read.

    The guard is intentionally non-LLM: it must be fast, auditable, and impossible to prompt-inject.
    """

    # Relative path components that are forbidden anywhere inside a resolved path.
    DEFAULT_BLOCKED_RELATIVE_PARTS = (
        ".ssh",
        ".env",
        ".gitconfig",
        ".aws",
        ".docker",
        ".kube",
        "System Volume Information",
        "$Recycle.Bin",
        "AppData\\Local\\Microsoft\\Windows",
    )

    # Absolute system directories. POSIX entries are only enforced on POSIX systems;
    # Windows entries are only enforced on Windows.
    DEFAULT_BLOCKED_ABSOLUTE_DIRS = (
        "/etc/",
        "/proc/",
        "/sys/",
        "/bin/",
        "/sbin/",
        "/usr/bin/",
        "/usr/sbin/",
        "/boot/",
        "/dev/",
        "/var/log/",
        "C:\\Windows\\System32",
        "C:\\Windows\\SysWOW64",
        "C:\\Program Files",
        "C:\\ProgramData",
    )

    SYSTEM_PROTECTED_NAMES = {
        ".ssh",
        ".env",
        ".env.local",
        ".env.production",
        ".env.development",
        ".gitconfig",
        "id_rsa",
        "id_ed25519",
        "id_ecdsa",
        "known_hosts",
        "authorized_keys",
        "shadow",
        "passwd",
    }

    def __init__(
        self,
        workspace_root: str | Path = ".",
        allowed_dirs: list[str] | None = None,
        blocked_dirs: list[str] | None = None,
        allow_read_anywhere: bool = False,
    ):
        self.workspace_root = Path(workspace_root).resolve()
        self.allowed_dirs: list[Path] = [self.workspace_root]
        if allowed_dirs:
            for d in allowed_dirs:
                p = Path(d).expanduser().resolve()
                if p not in self.allowed_dirs:
                    self.allowed_dirs.append(p)

        self.blocked_parts: set[str] = set()
        for part in self.DEFAULT_BLOCKED_RELATIVE_PARTS:
            self.blocked_parts.add(part.lower().replace("\\", "/"))

        self.blocked_dirs: list[Path] = []
        source_dirs = blocked_dirs or self.DEFAULT_BLOCKED_ABSOLUTE_DIRS
        for prefix in source_dirs:
            expanded = Path(prefix).expanduser()
            if not expanded.is_absolute():
                continue
            try:
                self.blocked_dirs.append(expanded.resolve())
            except Exception:
                self.blocked_dirs.append(expanded)

        self.allow_read_anywhere = allow_read_anywhere

    def check(self, raw_path: str | Path, operation: FSOperation | str = FSOperation.READ) -> FSGuardResult:
        """Evaluate whether the requested filesystem operation is permitted."""
        operation = FSOperation(operation) if isinstance(operation, str) else operation
        raw = str(raw_path)

        try:
            target = Path(raw).expanduser()
            if not target.is_absolute():
                target = self.workspace_root / target
            resolved = target.resolve()
        except (OSError, RuntimeError) as e:
            return FSGuardResult(
                path=raw,
                operation=operation,
                verdict=FSVerdict.BLOCKED,
                reason=f"Path resolution failed: {e}",
                allowed_dirs=[str(d) for d in self.allowed_dirs],
                blocked_dirs=[str(d) for d in self.blocked_dirs],
            )

        result = FSGuardResult(
            path=raw,
            operation=operation,
            verdict=FSVerdict.ALLOWED,
            normalized_path=str(resolved),
            allowed_dirs=[str(d) for d in self.allowed_dirs],
            blocked_dirs=[str(d) for d in self.blocked_dirs],
        )

        lower_name = resolved.name.lower()
        resolved_parts = [p.lower().replace("\\", "/") for p in resolved.parts]

        # 1. Blocked relative path components: .ssh, .env, System Volume Information, etc.
        for part in resolved_parts:
            if part in self.blocked_parts:
                result.verdict = FSVerdict.BLOCKED
                result.reason = f"Path contains blocked component: {part}"
                return result

        # 2. Block-list check: explicit absolute sensitive directories.
        for blocked in self.blocked_dirs:
            try:
                resolved.relative_to(blocked)
                result.verdict = FSVerdict.BLOCKED
                result.reason = f"Path resolves inside blocked directory: {blocked}"
                return result
            except ValueError:
                pass

        # 3. Protected file names: id_rsa, shadow, passwd, etc.
        if lower_name in {n.lower() for n in self.SYSTEM_PROTECTED_NAMES}:
            result.verdict = FSVerdict.BLOCKED
            result.reason = f"Protected name '{resolved.name}' is not accessible"
            return result

        # 4. Allow-list check: write/delete must be inside allowed_dirs; read is gated by allow_read_anywhere.
        inside_allowed = False
        for allowed in self.allowed_dirs:
            try:
                resolved.relative_to(allowed)
                inside_allowed = True
                break
            except ValueError:
                pass

        if operation in (FSOperation.WRITE, FSOperation.DELETE, FSOperation.EXECUTE):
            if not inside_allowed:
                result.verdict = FSVerdict.BLOCKED
                result.reason = f"{operation.value} operation outside allowed directories is forbidden"
                return result

        if operation == FSOperation.READ and not self.allow_read_anywhere and not inside_allowed:
            result.verdict = FSVerdict.ESCALATE
            result.reason = "Read outside allowed directories requires human escalation"
            return result

        result.reason = "Path permitted"
        return result

    def assert_allowed(self, raw_path: str | Path, operation: FSOperation | str = FSOperation.READ) -> FSGuardResult:
        """Same as check(), but raises FileSystemGuardError if not ALLOWED."""
        result = self.check(raw_path, operation)
        if result.verdict != FSVerdict.ALLOWED:
            raise FileSystemGuardError(result)
        return result

    def is_write_allowed(self, raw_path: str | Path) -> bool:
        return self.check(raw_path, FSOperation.WRITE).verdict == FSVerdict.ALLOWED

    def is_read_allowed(self, raw_path: str | Path) -> bool:
        return self.check(raw_path, FSOperation.READ).verdict in (FSVerdict.ALLOWED, FSVerdict.ESCALATE)

    def to_dict(self) -> dict[str, Any]:
        return {
            "workspace_root": str(self.workspace_root),
            "allowed_dirs": [str(d) for d in self.allowed_dirs],
            "blocked_dirs": [str(d) for d in self.blocked_dirs],
            "blocked_parts": sorted(self.blocked_parts),
            "allow_read_anywhere": self.allow_read_anywhere,
        }


class FileSystemGuardError(Exception):
    def __init__(self, result: FSGuardResult):
        super().__init__(f"Filesystem guard blocked {result.operation.value} on '{result.path}': {result.reason}")
        self.result = result
