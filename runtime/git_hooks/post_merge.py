#!/usr/bin/env python3
"""
Git post-merge hook — automatically scans merged files for conflict markers.

If conflict markers remain, prints a warning with file locations.
Can be extended to run runtime agents for semantic conflict analysis.

Usage:
    python runtime/git_hooks/post_merge.py
    # Or via git hook: .githooks/post-merge
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


CONFLICT_MARKERS = [b"<<<<<<<", b"=======", b">>>>>>>"]


def get_merged_files() -> list[str]:
    """Return files changed in the last merge commit."""
    result = subprocess.run(
        ["git", "diff", "HEAD@{1}", "--name-only"],
        capture_output=True, text=True, encoding="utf-8",
    )
    if result.returncode != 0:
        # Fallback: get all tracked files
        result = subprocess.run(
            ["git", "ls-files"],
            capture_output=True, text=True, encoding="utf-8",
        )
    return [f for f in result.stdout.strip().split("\n") if f]


def scan_for_conflicts(files: list[str]) -> list[tuple[str, int, bytes]]:
    """Return list of (file, line_number, marker) for remaining conflict markers."""
    conflicts = []
    for fp in files:
        path = Path(fp)
        if not path.exists():
            continue
        try:
            with open(path, "rb") as f:
                for lineno, line in enumerate(f, start=1):
                    for marker in CONFLICT_MARKERS:
                        if marker in line:
                            conflicts.append((fp, lineno, marker))
                            break
        except (OSError, UnicodeDecodeError):
            continue
    return conflicts


def main() -> int:
    files = get_merged_files()
    print(f"[post-merge] Scanning {len(files)} merged file(s) for conflict markers...")

    conflicts = scan_for_conflicts(files)

    if conflicts:
        print(f"[post-merge] WARNING: {len(conflicts)} conflict marker(s) found in {len(set(f for f, _, _ in conflicts))} file(s):")
        for fp, lineno, marker in conflicts:
            print(f"  {fp}:{lineno}  {marker.decode()}")
        print("[post-merge] Resolve conflicts before proceeding.")
        return 1

    print("[post-merge] No conflict markers found. Merge clean.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
