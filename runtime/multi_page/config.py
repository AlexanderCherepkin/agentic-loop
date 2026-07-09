from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class MultiPageConfig:
    target_dir: Path | str = "."
    base_url: str = "/"
    pages: list[dict[str, Any]] = field(default_factory=list)
    app_router_dir: str = "src/app"
    components_dir: str = "src/app/components"
    generate_navigation: bool = True
    generate_sitemap: bool = True
    generate_robots: bool = True
    write_pages: bool = True
    default_locale: str = "en"
    site_name: str = "Generated Site"

    def __post_init__(self) -> None:
        self.target_dir = Path(self.target_dir)

    def validate(self) -> list[str]:
        errors: list[str] = []
        if not self.target_dir.exists():
            errors.append(f"target_dir does not exist: {self.target_dir}")
        if not self.pages:
            errors.append("at least one page is required")
        for i, page in enumerate(self.pages):
            slug = page.get("slug")
            if not slug:
                errors.append(f"page {i} missing slug")
            elif not self._is_valid_slug(str(slug)):
                errors.append(f"page {i} has invalid slug: {slug}")
        return errors

    @staticmethod
    def _is_valid_slug(slug: str) -> bool:
        if not slug:
            return False
        return all(c.isalnum() or c in "-_" for c in slug)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "MultiPageConfig":
        return cls(
            target_dir=data.get("target_dir", "."),
            base_url=data.get("base_url", "/"),
            pages=list(data.get("pages") or []),
            app_router_dir=data.get("app_router_dir", "src/app"),
            components_dir=data.get("components_dir", "src/app/components"),
            generate_navigation=data.get("generate_navigation", True),
            generate_sitemap=data.get("generate_sitemap", True),
            generate_robots=data.get("generate_robots", True),
            write_pages=data.get("write_pages", True),
            default_locale=data.get("default_locale", "en"),
            site_name=data.get("site_name", "Generated Site"),
        )
