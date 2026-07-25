#!/usr/bin/env python3
"""Rotational cleanup for Agentic Loop operational artifacts.

Removes generated artifacts and old operational data that are not required for
runtime correctness.  Safe to run from cron, CI, or manually.

Targets:
- .audit/audit_YYYY-MM-DD.jsonl files older than --retention-days
- graphify-out/YYYY-MM-DD snapshots older than --retention-days
- data/cost_tracking.db rows older than --retention-days (then VACUUM)
- htmlcov/, __pycache__/, .pytest_cache/, .ruff_cache/
- .agent_loop/specs/*_spec.md mock files (450-byte placeholders)

Usage:
    python .agent_loop/scripts/cleanup_artifacts.py
    python .agent_loop/scripts/cleanup_artifacts.py --retention-days 20 --dry-run
    python .agent_loop/scripts/cleanup_artifacts.py --retention-days 7 --vacuum-cost-db

Exit codes:
    0 — cleanup completed
    1 — fatal error
"""

from __future__ import annotations

import argparse
import shutil
import sqlite3
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Iterable


def _project_root() -> Path:
    return Path(__file__).resolve().parent.parent.parent


def _parse_audit_date(name: str) -> datetime | None:
    """Parse audit_YYYY-MM-DD.jsonl filename into a UTC date."""
    if not name.startswith("audit_") or not name.endswith(".jsonl"):
        return None
    body = name[len("audit_") : -len(".jsonl")]
    try:
        return datetime.strptime(body, "%Y-%m-%d")
    except ValueError:
        return None


def _parse_snapshot_date(name: str) -> datetime | None:
    """Parse graphify-out/YYYY-MM-DD directory name into a UTC date."""
    try:
        return datetime.strptime(name, "%Y-%m-%d")
    except ValueError:
        return None


def clean_audit_logs(root: Path, cutoff: datetime, dry_run: bool) -> list[Path]:
    """Remove audit JSONL files older than cutoff."""
    removed: list[Path] = []
    audit_dir = root / ".audit"
    if not audit_dir.exists():
        return removed
    for path in audit_dir.glob("audit_*.jsonl"):
        date = _parse_audit_date(path.name)
        if date is None:
            continue
        if date < cutoff:
            if not dry_run:
                path.unlink(missing_ok=True)
            removed.append(path)
    return removed


def clean_graphify_snapshots(root: Path, cutoff: datetime, dry_run: bool) -> list[Path]:
    """Remove graphify-out/YYYY-MM-DD directories older than cutoff."""
    removed: list[Path] = []
    graphify_dir = root / "graphify-out"
    if not graphify_dir.exists():
        return removed
    for path in graphify_dir.iterdir():
        if not path.is_dir():
            continue
        date = _parse_snapshot_date(path.name)
        if date is None:
            continue
        if date < cutoff:
            if not dry_run:
                shutil.rmtree(path, ignore_errors=True)
            removed.append(path)
    return removed


def vacuum_cost_db(root: Path, cutoff_iso: str, dry_run: bool) -> tuple[int, int]:
    """Trim cost_tracking.db rows older than cutoff_iso and VACUUM."""
    db_path = root / "data" / "cost_tracking.db"
    if not db_path.exists():
        return 0, 0
    if dry_run:
        conn = sqlite3.connect(db_path)
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM cost_events WHERE timestamp < ?", (cutoff_iso,))
        would_delete = cur.fetchone()[0]
        conn.close()
        return would_delete, db_path.stat().st_size

    backup = db_path.with_suffix(".db.pre_cleanup")
    shutil.copy2(db_path, backup)
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("DELETE FROM cost_events WHERE timestamp < ?", (cutoff_iso,))
    deleted = cur.rowcount
    conn.commit()
    cur.execute("VACUUM")
    conn.close()
    backup.unlink(missing_ok=True)
    new_size = db_path.stat().st_size
    return deleted, new_size


def clean_caches(root: Path, dry_run: bool) -> list[Path]:
    """Remove generated cache directories."""
    removed: list[Path] = []
    targets = [root / "htmlcov"]
    for cache_name in ("__pycache__", ".pytest_cache", ".ruff_cache"):
        targets.extend(root.rglob(cache_name))
    for path in targets:
        if not path.exists():
            continue
        if not dry_run:
            if path.is_dir():
                shutil.rmtree(path, ignore_errors=True)
            else:
                path.unlink(missing_ok=True)
        removed.append(path)
    return removed


def clean_mock_specs(root: Path, dry_run: bool) -> list[Path]:
    """Remove 450-byte placeholder spec files."""
    removed: list[Path] = []
    specs_dir = root / ".agent_loop" / "specs"
    if not specs_dir.exists():
        return removed
    whitelist = {
        "memory_architecture_upgrade_spec.md",
        "anti-slop-rule-set_spec.md",
        "loop_engine_spec.md",
        "aedafddc-2c32-4848-875b-7d4667c15f84_spec.md",
        "2026-07-25-multi-agent-profiles-moa_spec.md",
        "2026-07-25-model-economy_spec.md",
    }
    for path in specs_dir.glob("*_spec.md"):
        if path.name in whitelist:
            continue
        if path.stat().st_size == 450 or path.stat().st_size < 512:
            if not dry_run:
                path.unlink(missing_ok=True)
            removed.append(path)
    return removed


def _fmt_bytes(n: int) -> str:
    if n >= 1024 * 1024 * 1024:
        return f"{n / 1024 / 1024 / 1024:.2f} GB"
    if n >= 1024 * 1024:
        return f"{n / 1024 / 1024:.2f} MB"
    if n >= 1024:
        return f"{n / 1024:.2f} KB"
    return f"{n} B"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Rotate operational artifacts for Agentic Loop")
    parser.add_argument(
        "--retention-days",
        type=int,
        default=20,
        help="Keep artifacts from the last N days (default: 20)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would be deleted without removing anything",
    )
    parser.add_argument(
        "--vacuum-cost-db",
        action="store_true",
        default=True,
        help="Trim cost_tracking.db and VACUUM (default: true)",
    )
    parser.add_argument(
        "--no-vacuum-cost-db",
        dest="vacuum_cost_db",
        action="store_false",
        help="Skip cost_tracking.db vacuum",
    )
    args = parser.parse_args(argv)

    root = _project_root()
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    cutoff = today - timedelta(days=args.retention_days)
    cutoff_iso = cutoff.strftime("%Y-%m-%d")

    print(f"Cleanup root: {root}")
    print(f"Retention window: keep artifacts from {cutoff.date()} onward")
    if args.dry_run:
        print("DRY RUN — no files will be deleted")
    print()

    audit_removed = clean_audit_logs(root, cutoff, args.dry_run)
    print(f"Audit logs {'would be ' if args.dry_run else ''}removed: {len(audit_removed)}")
    for p in audit_removed[:10]:
        print(f"  - {p}")
    if len(audit_removed) > 10:
        print(f"  ... and {len(audit_removed) - 10} more")
    print()

    snapshot_removed = clean_graphify_snapshots(root, cutoff, args.dry_run)
    print(f"Graphify snapshots {'would be ' if args.dry_run else ''}removed: {len(snapshot_removed)}")
    for p in snapshot_removed[:10]:
        print(f"  - {p}")
    if len(snapshot_removed) > 10:
        print(f"  ... and {len(snapshot_removed) - 10} more")
    print()

    if args.vacuum_cost_db:
        deleted, new_size = vacuum_cost_db(root, cutoff_iso, args.dry_run)
        print(
            f"cost_tracking.db: {'would delete' if args.dry_run else 'deleted'} {deleted} rows, "
            f"resulting size {('would be ' if args.dry_run else '')}{_fmt_bytes(new_size)}"
        )
    print()

    cache_removed = clean_caches(root, args.dry_run)
    print(f"Cache entries {'would be ' if args.dry_run else ''}removed: {len(cache_removed)}")
    for p in cache_removed[:10]:
        print(f"  - {p}")
    if len(cache_removed) > 10:
        print(f"  ... and {len(cache_removed) - 10} more")
    print()

    mock_specs_removed = clean_mock_specs(root, args.dry_run)
    print(f"Mock spec files {'would be ' if args.dry_run else ''}removed: {len(mock_specs_removed)}")
    for p in mock_specs_removed[:10]:
        print(f"  - {p}")
    print()

    print("Cleanup complete." if not args.dry_run else "Dry run complete.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
