"""Configuration for the /journey radial memory graph."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass
class JourneyConfig:
    """Configuration for the /journey visualizer."""

    workspace_root: str | Path = "."
    wiki_dir: str = "memory/wiki"
    skills_dir: str = ".claude/skills"
    output_dir: str = "journey-out"
    output_file: str = "index.html"
    width: int = 960
    height: int = 960
    max_nodes: int = 500

    @property
    def wiki_root(self) -> Path:
        return Path(self.workspace_root).resolve() / self.wiki_dir

    @property
    def skills_root(self) -> Path:
        return Path(self.workspace_root).resolve() / self.skills_dir

    @property
    def output_path(self) -> Path:
        return Path(self.workspace_root).resolve() / self.output_dir / self.output_file
