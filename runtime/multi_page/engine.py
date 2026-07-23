from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from runtime.safety.file_system_guard import safe_write_file

from .config import MultiPageConfig


def _stable_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True)


def _is_valid_url_slug(slug: str) -> bool:
    return bool(re.match(r"^[a-z0-9]+(-[a-z0-9]+)*$", str(slug)))


@dataclass
class MultiPageResult:
    files_written: list[str] = field(default_factory=list)
    files_modified: list[str] = field(default_factory=list)
    pages: list[dict[str, Any]] = field(default_factory=list)
    errors: list[dict[str, Any]] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


class MultiPageEngine:
    def __init__(self, target_dir: Path | str, config: MultiPageConfig | None = None):
        self.target_dir = Path(target_dir).resolve()
        self.config = config or MultiPageConfig()
        self.config.target_dir = self.target_dir
        self.result = MultiPageResult()

    def run(self) -> MultiPageResult:
        validation_errors = self.config.validate()
        if validation_errors:
            for err in validation_errors:
                self.result.errors.append({"file": "", "reason": err})
            return self.result

        self._ensure_dirs()
        if self.config.write_pages:
            self._write_pages()
        if self.config.generate_navigation:
            self._write_navigation()
        if self.config.generate_sitemap:
            self._write_sitemap()
        if self.config.generate_robots:
            self._write_robots()

        self.result.pages = list(self.config.pages)
        return self.result

    def _ensure_dirs(self) -> None:
        (self.target_dir / self.config.app_router_dir).mkdir(parents=True, exist_ok=True)
        (self.target_dir / self.config.components_dir).mkdir(parents=True, exist_ok=True)

    def _write_file(self, rel_path: str, content: str) -> None:
        try:
            full_path, existed = safe_write_file(
                self.target_dir, rel_path, content, track_existing=True
            )
            if existed:
                self.result.files_modified.append(rel_path)
            else:
                self.result.files_written.append(rel_path)
        except Exception as exc:
            self.result.errors.append({"file": rel_path, "reason": str(exc)})

    def _write_pages(self) -> None:
        for page in self.config.pages:
            slug = str(page.get("slug", "page"))
            code = page.get("code", "")
            if not code:
                self.result.errors.append({"file": f"app/{slug}/page.tsx", "reason": "missing page code"})
                continue
            if slug == "home":
                rel_path = f"{self.config.app_router_dir}/page.tsx"
            else:
                rel_path = f"{self.config.app_router_dir}/{slug}/page.tsx"
            self._write_file(rel_path, code)

    def _write_navigation(self) -> None:
        pages = self.config.pages
        if not pages:
            return
        links = []
        for page in pages:
            slug = str(page.get("slug", "page"))
            title = str(page.get("title", slug.replace("-", " ").title()))
            href = "/" if slug == "home" else f"/{slug}"
            links.append({"href": href, "label": title})
        links_json = _stable_json(links)
        code = f""""use client";

import Link from "next/link";

const pages = {links_json};

export function Navigation() {{
  return (
    <nav className="w-full py-4 px-6 border-b border-gray-200">
      <ul className="flex flex-wrap gap-6">
        {{pages.map((page) => (
          <li key={{page.href}}>
            <Link
              href={{page.href}}
              className="text-sm font-medium text-gray-700 hover:text-black transition-colors"
            >
              {{page.label}}
            </Link>
          </li>
        ))}}
      </ul>
    </nav>
  );
}}
"""
        self._write_file(f"{self.config.components_dir}/Navigation.tsx", code)

    def _write_sitemap(self) -> None:
        base = self.config.base_url.rstrip("/")
        entries = []
        for page in self.config.pages:
            slug = str(page.get("slug", "page"))
            href = "/" if slug == "home" else f"/{slug}"
            entries.append({
                "url": f"{base}{href}",
                "lastModified": "{{new Date().toISOString()}}",
                "priority": 1.0 if slug == "home" else 0.7,
            })
        # Build literal array expression for lastModified so it evaluates at runtime.
        entries_literal = "[\n" + ",\n".join(
            f"  {{ url: {json.dumps(e['url'])}, lastModified: new Date(), priority: {e['priority']} }}"
            for e in entries
        ) + "\n]"
        code = f"""import type {{ MetadataRoute }} from "next";

export default function sitemap(): MetadataRoute.Sitemap {{
  return {entries_literal};
}}
"""
        self._write_file(f"{self.config.app_router_dir}/sitemap.ts", code)

    def _write_robots(self) -> None:
        base = self.config.base_url.rstrip("/")
        code = f"""import type {{ MetadataRoute }} from "next";

export default function robots(): MetadataRoute.Robots {{
  return {{
    rules: {{
      userAgent: "*",
      allow: "/",
    }},
    sitemap: "{base}/sitemap.xml",
  }};
}}
"""
        self._write_file(f"{self.config.app_router_dir}/robots.ts", code)
