from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .config import PwaConfig


@dataclass
class PwaResult:
    files_written: list[str] = field(default_factory=list)
    files_modified: list[str] = field(default_factory=list)
    budget_violations: list[dict[str, Any]] = field(default_factory=list)
    errors: list[dict[str, Any]] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


class PwaEngine:
    def __init__(self, target_dir: Path | str, config: PwaConfig | None = None):
        self.target_dir = Path(target_dir).resolve()
        self.config = config or PwaConfig()
        self.config.target_dir = self.target_dir
        self.result = PwaResult()

    def run(self) -> PwaResult:
        validation_errors = self.config.validate()
        if validation_errors:
            for err in validation_errors:
                self.result.errors.append({"file": "", "reason": err})
            return self.result

        self._validate_project()
        if self.result.errors:
            return self.result

        self._write_manifest()
        self._write_service_worker_registration()
        self._write_offline_page()
        self._write_metadata_tags()
        self._analyze_budget()
        self._suggest_image_srcset()
        self._suggest_font_subsetting()
        self._update_next_config()

        return self.result

    def _validate_project(self) -> None:
        if not (self.target_dir / "package.json").exists():
            self.result.errors.append({"file": "package.json", "reason": "missing package.json; target_dir is not a Next.js project"})

    def _write_file(self, rel_path: str, content: str) -> None:
        full_path = self.target_dir / rel_path
        try:
            full_path.parent.mkdir(parents=True, exist_ok=True)
            full_path.write_text(content, encoding="utf-8")
            self.result.files_written.append(rel_path)
        except Exception as exc:
            self.result.errors.append({"file": rel_path, "reason": str(exc)})

    def _write_manifest(self) -> None:
        manifest = {
            "name": self.config.name,
            "short_name": self.config.short_name,
            "description": self.config.description,
            "start_url": self.config.start_url,
            "display": self.config.display,
            "orientation": self.config.orientation,
            "background_color": self.config.background_color,
            "theme_color": self.config.theme_color,
            "scope": self.config.scope,
            "icons": self.config.icons,
        }
        self._write_file("public/manifest.json", _stable_json(manifest))
        self._write_file(
            "src/lib/pwa.ts",
            """'use client';

export function registerServiceWorker() {
  if (typeof window === 'undefined' || !('serviceWorker' in navigator)) return;
  window.addEventListener('load', () => {
    navigator.serviceWorker.register('/sw.js').catch(() => {
      // silent fail; offline support is best-effort
    });
  });
}
""",
        )

    def _write_service_worker_registration(self) -> None:
        # The actual /sw.js is served from public/sw.js; Next.js serves public files at root.
        cache_name = "static-v1"
        strategy = self.config.service_worker_strategy
        offline_fallback = f"'{self.config.offline_filename}'" if self.config.offline_page else "undefined"
        sw = f"""const CACHE_NAME = '{cache_name}';
const PRECACHE_ASSETS = {json.dumps(['/'] + ([self.config.offline_filename] if self.config.offline_page else []))};
const STRATEGY = '{strategy}';
const OFFLINE_FALLBACK = {offline_fallback};

self.addEventListener('install', (event) => {{
  event.waitUntil(
    caches.open(CACHE_NAME)
      .then((cache) => cache.addAll(PRECACHE_ASSETS))
      .then(() => self.skipWaiting())
  );
}});

self.addEventListener('activate', (event) => {{
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((k) => k !== CACHE_NAME).map((k) => caches.delete(k)))
    ).then(() => self.clients.claim())
  );
}});

self.addEventListener('fetch', (event) => {{
  const {{ request }} = event;
  if (request.method !== 'GET') return;

  const isNavigation = request.mode === 'navigate';
  const isStatic = request.destination === 'image' || request.destination === 'script' || request.destination === 'style' || request.destination === 'font';

  const cacheFirst = async () => {{
    const cached = await caches.match(request);
    if (cached) return cached;
    try {{
      const response = await fetch(request);
      if (response && response.status === 200) {{
        const clone = response.clone();
        caches.open(CACHE_NAME).then((cache) => cache.put(request, clone));
      }}
      return response;
    }} catch (err) {{
      if (isNavigation && OFFLINE_FALLBACK) {{
        return caches.match(OFFLINE_FALLBACK).then((r) => r || new Response('Offline', {{ status: 503 }}));
      }}
      throw err;
    }}
  }};

  const networkFirst = async () => {{
    try {{
      const response = await fetch(request);
      if (response && response.status === 200) {{
        const clone = response.clone();
        caches.open(CACHE_NAME).then((cache) => cache.put(request, clone));
      }}
      return response;
    }} catch (err) {{
      const cached = await caches.match(request);
      if (cached) return cached;
      if (isNavigation && OFFLINE_FALLBACK) {{
        return caches.match(OFFLINE_FALLBACK).then((r) => r || new Response('Offline', {{ status: 503 }}));
      }}
      throw err;
    }}
  }};

  const staleWhileRevalidate = async () => {{
    const cached = await caches.match(request);
    const fetchPromise = fetch(request).then((response) => {{
      if (response && response.status === 200) {{
        const clone = response.clone();
        caches.open(CACHE_NAME).then((cache) => cache.put(request, clone));
      }}
      return response;
    }}).catch(() => cached);
    return cached || fetchPromise;
  }};

  if (isNavigation || !isStatic) {{
    if (STRATEGY === 'NetworkFirst') {{
      event.respondWith(networkFirst());
    }} else if (STRATEGY === 'StaleWhileRevalidate') {{
      event.respondWith(staleWhileRevalidate());
    }} else {{
      event.respondWith(cacheFirst());
    }}
  }} else {{
    if (STRATEGY === 'NetworkFirst') {{
      event.respondWith(networkFirst());
    }} else if (STRATEGY === 'StaleWhileRevalidate') {{
      event.respondWith(staleWhileRevalidate());
    }} else {{
      event.respondWith(cacheFirst());
    }}
  }}
}});
"""
        self._write_file("public/sw.js", sw)

    def _write_offline_page(self) -> None:
        if not self.config.offline_page:
            return
        html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Offline | {self.config.name}</title>
  <style>
    body {{ font-family: system-ui, sans-serif; text-align: center; padding: 4rem 1rem; }}
    h1 {{ font-size: 1.5rem; margin-bottom: 1rem; }}
    p {{ color: #666; }}
    a {{ color: #2563eb; }}
  </style>
</head>
<body>
  <h1>You are offline</h1>
  <p>This page was saved for offline use. <a href="/">Go home</a></p>
</body>
</html>
"""
        self._write_file(f"public/{self.config.offline_filename}", html)

    def _write_metadata_tags(self) -> None:
        # Write a Next.js metadata helper to public/ metadata is easier to set in layout.tsx
        # We generate a snippet file that the user can import into app/layout.tsx.
        self._write_file(
            "src/lib/pwa-meta.ts",
            f"""export const pwaMetadata = {{
  manifest: '/manifest.json',
  themeColor: '{self.config.theme_color}',
  icons: {self.config.icons!r},
  appleWebApp: {{
    capable: true,
    statusBarStyle: 'default',
    title: '{self.config.short_name}',
  }},
}};
""",
        )
        self._write_file(
            "src/components/PwaRegister.tsx",
            """'use client';

import { useEffect } from 'react';
import { registerServiceWorker } from '@/lib/pwa';

export default function PwaRegister() {
  useEffect(() => {
    registerServiceWorker();
  }, []);
  return null;
}
""",
        )

    def _analyze_budget(self) -> None:
        budget = self.config.budget
        public_dir = self.target_dir / "public"
        # JS from .next/static is not available before build, so estimate from node_modules + src.
        src_dir = self.target_dir / "src"
        app_dir = self.target_dir / "app"

        js_bytes = sum(_file_bytes(p) for p in self._walk([src_dir, app_dir], (".js", ".ts", ".jsx", ".tsx")))
        css_bytes = sum(_file_bytes(p) for p in self._walk([src_dir, app_dir], (".css",)))
        image_count = len(list(public_dir.rglob("*.*"))) if public_dir.exists() else 0

        # Font request estimate: count next/font/google imports.
        font_requests = 0
        for p in self._walk([src_dir, app_dir], (".tsx", ".ts", ".jsx", ".js")):
            try:
                text = p.read_text(encoding="utf-8")
                font_requests += len(re.findall(r"from\s+['\"]next/font/google['\"]|from\s+['\"]next/font/local['\"]", text))
            except Exception:
                pass

        third_party = 0
        for p in self._walk([src_dir, app_dir], (".tsx", ".ts", ".jsx", ".js")):
            try:
                text = p.read_text(encoding="utf-8")
                third_party += len(re.findall(r"(https?://|//cdn\.|//unpkg\.|//cdnjs\.|//jsdelivr)", text))
            except Exception:
                pass

        if budget.get("max_js_kib") is not None and js_bytes > budget["max_js_kib"] * 1024:
            self.result.budget_violations.append({
                "type": "js",
                "actual_kib": round(js_bytes / 1024, 1),
                "limit_kib": budget["max_js_kib"],
                "message": f"Estimated JS payload {round(js_bytes / 1024, 1)} KiB exceeds budget {budget['max_js_kib']} KiB",
            })
        if budget.get("max_css_kib") is not None and css_bytes > budget["max_css_kib"] * 1024:
            self.result.budget_violations.append({
                "type": "css",
                "actual_kib": round(css_bytes / 1024, 1),
                "limit_kib": budget["max_css_kib"],
                "message": f"CSS payload {round(css_bytes / 1024, 1)} KiB exceeds budget {budget['max_css_kib']} KiB",
            })
        if budget.get("max_first_party_images") is not None and image_count > budget["max_first_party_images"]:
            self.result.budget_violations.append({
                "type": "images",
                "actual": image_count,
                "limit": budget["max_first_party_images"],
                "message": f"{image_count} first-party public assets exceed budget {budget['max_first_party_images']}",
            })
        if budget.get("max_font_requests") is not None and font_requests > budget["max_font_requests"]:
            self.result.budget_violations.append({
                "type": "fonts",
                "actual": font_requests,
                "limit": budget["max_font_requests"],
                "message": f"{font_requests} font imports exceed budget {budget['max_font_requests']}",
            })
        if budget.get("max_third_party_requests") is not None and third_party > budget["max_third_party_requests"]:
            self.result.budget_violations.append({
                "type": "third_party",
                "actual": third_party,
                "limit": budget["max_third_party_requests"],
                "message": f"{third_party} third-party references exceed budget {budget['max_third_party_requests']}",
            })

    def _suggest_image_srcset(self) -> None:
        if not self.config.image_srcset_enabled:
            return
        # Find <img> tags without srcSet / sizes in generated source and note them.
        candidates: list[tuple[str, int]] = []
        for p in self._walk([self.target_dir / "src", self.target_dir / "app"], (".tsx", ".jsx")):
            try:
                text = p.read_text(encoding="utf-8")
                rel = str(p.relative_to(self.target_dir))
                for idx, line in enumerate(text.splitlines(), start=1):
                    if "<img" in line or "<Image" in line:
                        if "srcSet=" not in line and "srcset=" not in line and "fill" not in line:
                            candidates.append((rel, idx))
            except Exception:
                pass
        if candidates:
            rel, line = candidates[0]
            self.result.notes.append(
                f"Consider adding responsive srcSet/sizes for images ({len(candidates)} sites), e.g. {rel}:{line}"
            )

    def _suggest_font_subsetting(self) -> None:
        if not self.config.font_subsetting_enabled:
            return
        # Note next/font/google imports that lack explicit subsets.
        candidates: list[tuple[str, int]] = []
        subset_str = ",".join(self.config.font_subsets)
        for p in self._walk([self.target_dir / "src", self.target_dir / "app"], (".tsx", ".jsx", ".ts", ".js")):
            try:
                text = p.read_text(encoding="utf-8")
                rel = str(p.relative_to(self.target_dir))
                has_subset = "subsets" in text
                for idx, line in enumerate(text.splitlines(), start=1):
                    if "next/font/google" in line or "next/font/local" in line:
                        if not has_subset:
                            candidates.append((rel, idx))
                        # Insert note per file only once.
                        break
            except Exception:
                pass
        for rel, line in candidates:
            self.result.notes.append(
                f"Add subsets:['{subset_str}'] to next/font/google import at {rel}:{line}"
            )

    def _update_next_config(self) -> None:
        config_path = self.target_dir / "next.config.js"
        if not config_path.exists():
            return
        try:
            content = config_path.read_text(encoding="utf-8")
            marker = "// pwa-config-start"
            end_marker = "// pwa-config-end"
            pwa_block = f"""
{marker}
  // PWA configuration injected by runtime/pwa/PwaEngine
  poweredByHeader: false,
{end_marker}
"""
            if marker in content:
                content = re.sub(
                    rf"{re.escape(marker)}.*?{re.escape(end_marker)}",
                    pwa_block,
                    content,
                    flags=re.DOTALL,
                )
            else:
                content = content.rstrip() + "\n" + pwa_block + "\n"
            config_path.write_text(content, encoding="utf-8")
            self.result.files_modified.append(str(config_path))
        except Exception as exc:
            self.result.errors.append({"file": "next.config.js", "reason": str(exc)})

    def _walk(self, roots: list[Path], extensions: tuple[str, ...]) -> list[Path]:
        out: list[Path] = []
        for root in roots:
            if not root.exists():
                continue
            for p in root.rglob("*"):
                if p.is_file() and p.suffix in extensions:
                    if any(part in p.parts for part in ("node_modules", ".next", "out", "dist", "coverage")):
                        continue
                    out.append(p)
        return out


def _file_bytes(path: Path) -> int:
    try:
        return path.stat().st_size
    except Exception:
        return 0


def _stable_json(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, indent=2, sort_keys=True)
