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

    # Image/API provider fields (Render, Railway, Fly.io)
    image_tag: str | None = None
    project_id: str | None = None
    language: str | None = None
    service_name: str | None = None
    app_name: str | None = None
    region: str | None = None
    owner_id: str | None = None
    plan: str | None = None
    org_slug: str | None = None

    def __post_init__(self) -> None:
        self.target_dir = Path(self.target_dir)

    @property
    def is_image_provider(self) -> bool:
        return self.provider in {"render", "railway", "flyio"}

    def validate(self) -> list[str]:
        errors: list[str] = []
        if not self.target_dir.exists():
            errors.append(f"target_dir does not exist: {self.target_dir}")
        if self.provider not in {"vercel", "netlify", "generic", "render", "railway", "flyio"}:
            errors.append(f"provider must be vercel, netlify, generic, render, railway, or flyio; got {self.provider}")
        if not self.build_command:
            errors.append("build_command is required")
        if self.provider == "generic" and not self.dist_dir:
            errors.append("dist_dir is required for generic provider")
        if self.is_image_provider:
            if not self.image_tag:
                errors.append(f"image_tag is required for {self.provider} provider")
            if not self.project_id:
                errors.append(f"project_id is required for {self.provider} provider")
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
            image_tag=data.get("image_tag"),
            project_id=data.get("project_id"),
            language=data.get("language"),
            service_name=data.get("service_name"),
            app_name=data.get("app_name"),
            region=data.get("region"),
            owner_id=data.get("owner_id"),
            plan=data.get("plan"),
            org_slug=data.get("org_slug"),
        )
