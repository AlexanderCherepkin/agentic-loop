from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


DEFAULT_BUDGET: dict[str, int | None] = {
    "max_js_kib": 250,
    "max_css_kib": 50,
    "max_first_party_images": 15,
    "max_total_page_kib": 1024,
    "max_font_requests": 4,
    "max_third_party_requests": 5,
}

DEFAULT_FONT_SUBSETS: list[str] = ["latin", "latin-ext"]

DEFAULT_IMAGE_BREAKPOINTS: list[int] = [640, 750, 828, 1080, 1200, 1920]


@dataclass
class PwaConfig:
    target_dir: Path | str = "."
    name: str = "Generated Site"
    short_name: str = "Site"
    description: str = "Generated Next.js PWA"
    theme_color: str = "#000000"
    background_color: str = "#ffffff"
    start_url: str = "/"
    display: str = "standalone"
    orientation: str = "any"
    scope: str = "/"
    icons: list[dict[str, Any]] = field(
        default_factory=lambda: [
            {"src": "/icon-192x192.png", "sizes": "192x192", "type": "image/png", "purpose": "any maskable"},
            {"src": "/icon-512x512.png", "sizes": "512x512", "type": "image/png", "purpose": "any maskable"},
        ]
    )
    offline_page: bool = True
    offline_filename: str = "offline.html"
    service_worker_strategy: str = "CacheFirst"
    image_srcset_enabled: bool = True
    image_breakpoints: list[int] = field(default_factory=lambda: DEFAULT_IMAGE_BREAKPOINTS.copy())
    font_subsetting_enabled: bool = True
    font_subsets: list[str] = field(default_factory=lambda: DEFAULT_FONT_SUBSETS.copy())
    font_display: str = "swap"
    budget: dict[str, int | None] = field(default_factory=lambda: DEFAULT_BUDGET.copy())
    include: list[str] = field(default_factory=lambda: ["public/**", "src/**/*.{tsx,jsx,ts,js}", "app/**/*.{tsx,jsx,ts,js}"])
    exclude: list[str] = field(default_factory=lambda: ["node_modules", ".next", "out", "dist", "coverage"])

    def __post_init__(self) -> None:
        self.target_dir = Path(self.target_dir)

    def validate(self) -> list[str]:
        errors: list[str] = []
        if not self.target_dir.exists():
            errors.append(f"target_dir does not exist: {self.target_dir}")
        if not self.name:
            errors.append("name is required")
        if not self.short_name:
            errors.append("short_name is required")
        if not re.match(r"^#[0-9a-fA-F]{6}$", self.theme_color):
            errors.append(f"theme_color must be a 6-digit hex color, got {self.theme_color}")
        if not re.match(r"^#[0-9a-fA-F]{6}$", self.background_color):
            errors.append(f"background_color must be a 6-digit hex color, got {self.background_color}")
        valid_displays = {"fullscreen", "standalone", "minimal-ui", "browser"}
        if self.display not in valid_displays:
            errors.append(f"display must be one of {valid_displays}")
        if self.service_worker_strategy not in {"CacheFirst", "NetworkFirst", "StaleWhileRevalidate"}:
            errors.append("service_worker_strategy must be CacheFirst, NetworkFirst, or StaleWhileRevalidate")
        if not self.icons:
            errors.append("at least one icon is required")
        return errors

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "PwaConfig":
        return cls(
            target_dir=data.get("target_dir", "."),
            name=data.get("name", "Generated Site"),
            short_name=data.get("short_name", "Site"),
            description=data.get("description", "Generated Next.js PWA"),
            theme_color=data.get("theme_color", "#000000"),
            background_color=data.get("background_color", "#ffffff"),
            start_url=data.get("start_url", "/"),
            display=data.get("display", "standalone"),
            orientation=data.get("orientation", "any"),
            scope=data.get("scope", "/"),
            icons=data.get("icons", [
                {"src": "/icon-192x192.png", "sizes": "192x192", "type": "image/png", "purpose": "any maskable"},
                {"src": "/icon-512x512.png", "sizes": "512x512", "type": "image/png", "purpose": "any maskable"},
            ]),
            offline_page=data.get("offline_page", True),
            offline_filename=data.get("offline_filename", "offline.html"),
            service_worker_strategy=data.get("service_worker_strategy", "CacheFirst"),
            image_srcset_enabled=data.get("image_srcset_enabled", True),
            image_breakpoints=data.get("image_breakpoints", DEFAULT_IMAGE_BREAKPOINTS.copy()),
            font_subsetting_enabled=data.get("font_subsetting_enabled", True),
            font_subsets=data.get("font_subsets", DEFAULT_FONT_SUBSETS.copy()),
            font_display=data.get("font_display", "swap"),
            budget={**DEFAULT_BUDGET, **(data.get("budget") or {})},
            include=data.get("include", ["public/**", "src/**/*.{tsx,jsx,ts,js}", "app/**/*.{tsx,jsx,ts,js}"]),
            exclude=data.get("exclude", ["node_modules", ".next", "out", "dist", "coverage"]),
        )
