"""Wiki engine configuration."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Sequence


@dataclass
class WikiConfig:
    """Configuration for the LLM Wiki engine."""

    memory_root: str | Path = "."
    wiki_dir: str = "wiki"
    schema_file: str = "wiki-schema.md"
    index_file: str = "index.md"
    template_file: str = "_template.md"
    allowed_page_types: Sequence[str] = (
        "concept",
        "howto",
        "decision",
        "project",
        "source",
        "person",
        "tool",
    )
    stale_days: int = 90
    deprecated_delete_days: int = 180
    max_lint_issues: int = 20

    @property
    def wiki_root(self) -> Path:
        return Path(self.memory_root).resolve() / self.wiki_dir

    @property
    def schema_path(self) -> Path:
        return Path(self.memory_root).resolve() / self.schema_file

    @property
    def index_path(self) -> Path:
        return self.wiki_root / self.index_file
