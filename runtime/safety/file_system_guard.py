from __future__ import annotations

import os
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any


def safe_write_file(
    base_dir: str | Path,
    rel_path: str | Path,
    content: str,
    *,
    track_existing: bool = False,
) -> Path | tuple[Path, bool]:
    """Write content to a path relative to base_dir, blocking traversal escapes.

    - Collapses `..` and redundant separators using os.path.normpath (does NOT
      follow symlinks, so this check is safe for untrusted relative paths).
    - Verifies the normalized path is still inside base_dir.
    - Runs the path through FileSystemGuard for WRITE operation.
    - Creates parent directories automatically.

    If track_existing is True, returns (path, existed_before_write).

    Raises FileSystemGuardError if the path escapes base_dir or is blocked.
    """
    base = Path(base_dir).resolve()
    raw_target = base / rel_path
    normalized = Path(os.path.normpath(str(raw_target)))

    # Path-traversal guard: normalized path must remain inside base_dir.
    try:
        normalized.relative_to(base)
    except ValueError as exc:
        result = FSGuardResult(
            path=str(normalized),
            operation=FSOperation.WRITE,
            verdict=FSVerdict.BLOCKED,
            reason=f"Path escapes base directory: {base}",
            normalized_path=str(normalized),
            allowed_dirs=[str(base)],
        )
        raise FileSystemGuardError(result) from exc

    # Additional guard against blocked components and protected names.
    guard = FileSystemGuard(workspace_root=str(base))
    guard.assert_allowed(str(normalized), FSOperation.WRITE)

    existed = normalized.exists() if track_existing else False
    normalized.parent.mkdir(parents=True, exist_ok=True)
    normalized.write_text(content, encoding="utf-8")
    if track_existing:
        return normalized, existed
    return normalized


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
    # Multi-component entries are split at runtime into ordered segment tuples so that
    # checks match the full sequence (e.g. AppData/Local/Microsoft/Windows) rather than
    # a single part that never appears in resolved_parts.
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
        self.blocked_sequences: list[tuple[str, ...]] = []
        for part in self.DEFAULT_BLOCKED_RELATIVE_PARTS:
            normalized = part.lower().replace("\\", "/")
            segments = tuple(normalized.split("/"))
            if len(segments) == 1:
                self.blocked_parts.add(segments[0])
            else:
                self.blocked_sequences.append(segments)

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

        # 1b. Blocked multi-component sequences (e.g. AppData/Local/Microsoft/Windows).
        for sequence in self.blocked_sequences:
            seq_len = len(sequence)
            for i in range(len(resolved_parts) - seq_len + 1):
                if tuple(resolved_parts[i:i + seq_len]) == sequence:
                    result.verdict = FSVerdict.BLOCKED
                    result.reason = f"Path contains blocked sequence: {'/'.join(sequence)}"
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
            "blocked_sequences": ["/".join(seq) for seq in self.blocked_sequences],
            "allow_read_anywhere": self.allow_read_anywhere,
        }


class FileSystemGuardError(Exception):
    def __init__(self, result: FSGuardResult):
        super().__init__(f"Filesystem guard blocked {result.operation.value} on '{result.path}': {result.reason}")
        self.result = result
