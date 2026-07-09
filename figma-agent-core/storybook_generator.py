"""CLI wrapper for runtime/storybook/StorybookEngine.

Generates .stories.tsx files and Storybook configuration for a Next.js project.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from runtime.storybook import StorybookConfig, StorybookEngine


def main() -> None:
    parser = argparse.ArgumentParser(description="Storybook generator: create .stories.tsx for UI components.")
    parser.add_argument("--target-dir", default=".", help="Next.js project root.")
    parser.add_argument("--component-dirs", default=None, help="Comma-separated component directories.")
    parser.add_argument("--stories-dir", default="src/stories", help="Output directory for stories.")
    args = parser.parse_args()

    component_dirs = None
    if args.component_dirs:
        component_dirs = [d.strip() for d in args.component_dirs.split(",") if d.strip()]

    config = StorybookConfig(
        target_dir=args.target_dir,
        component_dirs=component_dirs or ["src/components/ui", "src/app/components"],
        stories_dir=args.stories_dir,
    )
    engine = StorybookEngine(args.target_dir, config)
    result = engine.run()

    if result.errors:
        for err in result.errors:
            print(f"[STORYBOOK ERROR] {err['file']}: {err['reason']}")

    for story in result.stories:
        print(f"[STORYBOOK WRITTEN] {story['story_path']}")
    for path in result.files_modified:
        print(f"[STORYBOOK MODIFIED] {path}")

    sys.exit(1 if result.errors else 0)


if __name__ == "__main__":
    main()
