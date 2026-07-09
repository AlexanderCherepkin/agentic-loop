"""CLI wrapper for runtime/multi_page/MultiPageEngine.

Generates multi-page Next.js App Router routes, Navigation, sitemap and robots.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

# Allow imports from project root (runtime package).
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from runtime.multi_page import MultiPageConfig, MultiPageEngine


def main() -> None:
    parser = argparse.ArgumentParser(description="Multi-page composer: write Next.js App Router pages + routing artifacts.")
    parser.add_argument("--target-dir", default=".", help="Next.js project root.")
    parser.add_argument("--pages", default=None, help="JSON list of pages with slug/title/code/metadata.")
    parser.add_argument("--pages-file", default=None, help="JSON file with pages list.")
    parser.add_argument("--base-url", default="/", help="Base URL for canonical/sitemap.")
    parser.add_argument("--app-router-dir", default="src/app", help="App Router directory relative to target-dir.")
    parser.add_argument("--components-dir", default="src/app/components", help="Components directory relative to target-dir.")
    parser.add_argument("--no-navigation", action="store_true", help="Skip Navigation.tsx generation.")
    parser.add_argument("--no-sitemap", action="store_true", help="Skip sitemap.ts generation.")
    parser.add_argument("--no-robots", action="store_true", help="Skip robots.ts generation.")
    parser.add_argument("--routing-only", action="store_true", help="Only generate routing artifacts; do not write page.tsx files.")
    parser.add_argument("--site-name", default="Generated Site", help="Site name for metadata.")
    args = parser.parse_args()

    pages: list[dict[str, Any]] = []
    if args.pages:
        pages = json.loads(args.pages)
    elif args.pages_file:
        pages = json.loads(Path(args.pages_file).read_text(encoding="utf-8"))
    else:
        print("[MULTI-PAGE] No pages provided. Use --pages or --pages-file.")
        sys.exit(1)

    config = MultiPageConfig(
        target_dir=args.target_dir,
        base_url=args.base_url,
        pages=pages,
        app_router_dir=args.app_router_dir,
        components_dir=args.components_dir,
        generate_navigation=not args.no_navigation,
        generate_sitemap=not args.no_sitemap,
        generate_robots=not args.no_robots,
        write_pages=not args.routing_only,
        site_name=args.site_name,
    )
    engine = MultiPageEngine(args.target_dir, config)
    result = engine.run()

    if result.errors:
        for err in result.errors:
            print(f"[MULTI-PAGE ERROR] {err['file']}: {err['reason']}")

    for path in result.files_written:
        print(f"[MULTI-PAGE WRITTEN] {path}")
    for path in result.files_modified:
        print(f"[MULTI-PAGE MODIFIED] {path}")

    sys.exit(1 if result.errors else 0)


if __name__ == "__main__":
    main()
