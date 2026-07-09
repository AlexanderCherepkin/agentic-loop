from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


DEFAULT_COMPONENT_DIRS: list[str] = ["src/components/ui", "src/app/components"]
DEFAULT_STORIES_DIR: str = "src/stories"


@dataclass
class StorybookConfig:
    target_dir: Path | str = "."
    component_dirs: list[str] = field(default_factory=lambda: list(DEFAULT_COMPONENT_DIRS))
    stories_dir: str = DEFAULT_STORIES_DIR
    framework: str = "@storybook/nextjs"
    builder: str = "@storybook/builder-webpack5"
    renderer: str = "@storybook/react"

    def __post_init__(self) -> None:
        self.target_dir = Path(self.target_dir)

    def validate(self) -> list[str]:
        errors: list[str] = []
        if not self.target_dir.exists():
            errors.append(f"target_dir does not exist: {self.target_dir}")
        if not self.component_dirs:
            errors.append("at least one component_dir is required")
        if not self.framework:
            errors.append("framework is required")
        return errors

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "StorybookConfig":
        return cls(
            target_dir=data.get("target_dir", "."),
            component_dirs=list(data.get("component_dirs") or DEFAULT_COMPONENT_DIRS),
            stories_dir=data.get("stories_dir", DEFAULT_STORIES_DIR),
            framework=data.get("framework", "@storybook/nextjs"),
            builder=data.get("builder", "@storybook/builder-webpack5"),
            renderer=data.get("renderer", "@storybook/react"),
        )
