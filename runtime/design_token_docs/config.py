from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


DEFAULT_SOURCE_FILES: list[str] = [
    "src/design_tokens.json",
    "design_tokens.json",
    "src/tokens/design_tokens.json",
    "tokens/design_tokens.json",
    "figma-agent-core/.tmp/tokens/design_tokens.json",
]

DEFAULT_COMPONENT_REGISTRY_FILES: list[str] = [
    "component_registry.json",
    "src/component_registry.json",
    "figma-agent-core/component_registry.json",
]


@dataclass
class DesignTokenDocsConfig:
    target_dir: Path | str = "."
    output_dir: str = "docs"
    markdown_filename: str = "DESIGN_TOKENS.md"
    json_filename: str = "design_tokens.docs.json"
    html_filename: str = "design_tokens.html"
    title: str = "Design Tokens"
    description: str = "Human-readable design token documentation generated from Figma styles and variables."
    source_files: list[str] = field(default_factory=lambda: DEFAULT_SOURCE_FILES.copy())
    component_registry_files: list[str] = field(
        default_factory=lambda: DEFAULT_COMPONENT_REGISTRY_FILES.copy()
    )
    formats: list[str] = field(default_factory=lambda: ["markdown", "json"])
    include_sections: list[str] = field(
        default_factory=lambda: ["colors", "typography", "components", "usage"]
    )
    include_color_preview: bool = True
    include_css_vars: bool = True

    def __post_init__(self) -> None:
        self.target_dir = Path(self.target_dir)
        self.formats = [f.lower() for f in self.formats]
        valid = {"markdown", "json", "html"}
        self.formats = [f for f in self.formats if f in valid]
        if not self.formats:
            self.formats = ["markdown"]

    def validate(self) -> list[str]:
        errors: list[str] = []
        if not self.target_dir.exists():
            errors.append(f"target_dir does not exist: {self.target_dir}")
        if not self.title:
            errors.append("title is required")
        if not self.markdown_filename.endswith(".md"):
            errors.append(f"markdown_filename must end with .md: {self.markdown_filename}")
        if not self.json_filename.endswith(".json"):
            errors.append(f"json_filename must end with .json: {self.json_filename}")
        if not self.html_filename.endswith((".html", ".htm")):
            errors.append(f"html_filename must end with .html: {self.html_filename}")
        valid_sections = {"colors", "typography", "components", "usage", "sources"}
        unknown = set(self.include_sections) - valid_sections
        if unknown:
            errors.append(f"unknown include_sections: {sorted(unknown)}")
        return errors

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "DesignTokenDocsConfig":
        return cls(
            target_dir=data.get("target_dir", "."),
            output_dir=data.get("output_dir", "docs"),
            markdown_filename=data.get("markdown_filename", "DESIGN_TOKENS.md"),
            json_filename=data.get("json_filename", "design_tokens.docs.json"),
            html_filename=data.get("html_filename", "design_tokens.html"),
            title=data.get("title", "Design Tokens"),
            description=data.get("description", "Human-readable design token documentation generated from Figma styles and variables."),
            source_files=data.get("source_files", DEFAULT_SOURCE_FILES.copy()),
            component_registry_files=data.get(
                "component_registry_files", DEFAULT_COMPONENT_REGISTRY_FILES.copy()
            ),
            formats=data.get("formats", ["markdown", "json"]),
            include_sections=data.get(
                "include_sections", ["colors", "typography", "components", "usage"]
            ),
            include_color_preview=data.get("include_color_preview", True),
            include_css_vars=data.get("include_css_vars", True),
        )
