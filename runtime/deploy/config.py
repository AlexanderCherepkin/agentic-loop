from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class DeployConfig:
    target_dir: Path | str = "."
    provider: str = "vercel"
    dry_run: bool = True
    build_command: str = "pnpm build"
    dist_dir: str = "dist"
    env: dict[str, str] = field(default_factory=dict)
    timeout: float = 300.0

    def __post_init__(self) -> None:
        self.target_dir = Path(self.target_dir)

    def validate(self) -> list[str]:
        errors: list[str] = []
        if not self.target_dir.exists():
            errors.append(f"target_dir does not exist: {self.target_dir}")
        if self.provider not in {"vercel", "netlify", "generic"}:
            errors.append(f"provider must be vercel, netlify, or generic, got {self.provider}")
        if not self.build_command:
            errors.append("build_command is required")
        if self.provider == "generic" and not self.dist_dir:
            errors.append("dist_dir is required for generic provider")
        return errors

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "DeployConfig":
        return cls(
            target_dir=data.get("target_dir", "."),
            provider=data.get("provider", "vercel"),
            dry_run=bool(data.get("dry_run", True)),
            build_command=data.get("build_command", "pnpm build"),
            dist_dir=data.get("dist_dir", "dist"),
            env=dict(data.get("env") or {}),
            timeout=float(data.get("timeout", 300.0)),
        )
