"""Sandbox configuration data classes."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any


class SandboxBackend(str, Enum):
    """Preferred execution backend."""

    AUTO = "auto"
    DOCKER = "docker"
    WSL2 = "wsl2"


@dataclass
class SandboxConfig:
    """Configuration for an isolated sandbox execution.

    All paths are resolved relative to the project workspace unless absolute.
    """

    workspace_root: Path | str = "."
    backend: SandboxBackend = SandboxBackend.AUTO
    image: str = "node:20-slim"
    wsl_distro: str = "Ubuntu"
    user: str = "root"
    network: str = "bridge"
    timeout_ms: int = 120_000
    env: dict[str, str] = field(default_factory=dict)
    mounts: list[tuple[str, str]] = field(default_factory=list)
    # Files or globs to copy back into workspace_root after execution.
    artifact_paths: list[str] = field(default_factory=list)
    keep_container: bool = False
    enable_screenshot: bool = True

    def __post_init__(self) -> None:
        self.workspace_root = Path(self.workspace_root).resolve()
        if self.backend == SandboxBackend.AUTO:
            self.backend = SandboxBackend.DOCKER if self._docker_available() else SandboxBackend.WSL2

    @staticmethod
    def from_dict(data: dict[str, Any]) -> "SandboxConfig":
        backend = SandboxBackend(data.get("backend", "auto"))
        mounts_raw = data.get("mounts", [])
        mounts: list[tuple[str, str]] = []
        for entry in mounts_raw:
            if isinstance(entry, (list, tuple)) and len(entry) == 2:
                mounts.append((str(entry[0]), str(entry[1])))
            elif isinstance(entry, str) and ":" in entry:
                host, cont = entry.split(":", 1)
                mounts.append((host, cont))
        return SandboxConfig(
            workspace_root=data.get("workspace_root", "."),
            backend=backend,
            image=data.get("image", "node:20-slim"),
            wsl_distro=data.get("wsl_distro", "Ubuntu"),
            user=data.get("user", "root"),
            network=data.get("network", "bridge"),
            timeout_ms=int(data.get("timeout_ms", 120_000)),
            env=data.get("env", {}),
            mounts=mounts,
            artifact_paths=data.get("artifact_paths", []),
            keep_container=bool(data.get("keep_container", False)),
            enable_screenshot=bool(data.get("enable_screenshot", True)),
        )

    @staticmethod
    def _docker_available() -> bool:
        try:
            import shutil
            import subprocess

            if not shutil.which("docker"):
                return False
            result = subprocess.run(
                ["docker", "info"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            return result.returncode == 0
        except Exception:
            return False
