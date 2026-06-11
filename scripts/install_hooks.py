#!/usr/bin/env python3
"""
Git hooks installer — copies hooks from .githooks/ to .git/hooks/

Cross-platform: works on Windows, macOS, Linux.
Also creates .safetyignore template if missing.

Usage:
    python scripts/install_hooks.py [--dry-run]
"""

from __future__ import annotations

import argparse
import shutil
import stat
import sys
from pathlib import Path


def chmod_plus_x(path: Path) -> None:
    """Make file executable (Unix). No-op on Windows."""
    if sys.platform != "win32":
        path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def install_hooks(dry_run: bool = False) -> int:
    root = Path(__file__).resolve().parent.parent
    src_dir = root / ".githooks"
    git_dir = root / ".git"
    dst_dir = git_dir / "hooks"

    if not git_dir.exists():
        print("[install-hooks] No .git directory found.")
        print("  Run: git init")
        return 1

    if not src_dir.exists():
        print("[install-hooks] No .githooks/ directory found.")
        return 1

    if not dst_dir.exists():
        if dry_run:
            print(f"[install-hooks] Would create: {dst_dir}")
        else:
            dst_dir.mkdir(parents=True, exist_ok=True)
            print(f"[install-hooks] Created: {dst_dir}")

    hooks = [f for f in src_dir.iterdir() if f.is_file() and not f.name.startswith(".")]
    if not hooks:
        print("[install-hooks] No hooks found in .githooks/.")
        return 0

    print(f"[install-hooks] Installing {len(hooks)} hook(s) from .githooks/ → .git/hooks/:\n")

    installed = 0
    for src in hooks:
        dst = dst_dir / src.name
        if dry_run:
            print(f"  [DRY-RUN] Would copy: {src.name}")
            continue
        shutil.copy2(src, dst)
        chmod_plus_x(dst)
        print(f"  ✓ {src.name}")
        installed += 1

    # Ensure .safetyignore template exists
    safetyignore = root / ".safetyignore"
    if not safetyignore.exists() and not dry_run:
        safetyignore.write_text(
            "# Patterns ignored by safety_check.js\n"
            "# Add files or directories (one per line) to skip during scanning\n"
            "# Supports wildcards: *.log, temp/*\n"
            "\n"
            "package-lock.json\n"
            "pnpm-lock.yaml\n"
            ".claude/\n"
        )
        print(f"\n  Created template: {safetyignore.name}")

    print("\n[install-hooks] Done.")
    print("  Hooks will run automatically on commit / push / merge.")
    print("  Bypass: git commit --no-verify  |  git push --no-verify")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Install git hooks")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be installed")
    args = parser.parse_args()
    return install_hooks(dry_run=args.dry_run)


if __name__ == "__main__":
    sys.exit(main())
