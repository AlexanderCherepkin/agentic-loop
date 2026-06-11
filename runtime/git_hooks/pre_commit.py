#!/usr/bin/env python3
"""
Git pre-commit hook — runs three-circuit safety checks on staged files.

Reuses the existing safety_check.js logic via subprocess for speed.
Can be upgraded to invoke runtime agents directly when API keys are available.

Usage:
    python runtime/git_hooks/pre_commit.py [--json]
    # Or via git hook: .githooks/pre-commit
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def get_staged_files() -> list[str]:
    """Return list of staged file paths."""
    result = subprocess.run(
        ["git", "diff", "--cached", "--name-only", "--diff-filter=ACM"],
        capture_output=True, text=True, encoding="utf-8",
    )
    if result.returncode != 0:
        print("[pre-commit] Not a git repository or git error.", file=sys.stderr)
        sys.exit(1)
    return [f for f in result.stdout.strip().split("\n") if f]


def run_safety_check(files: list[str]) -> dict:
    """Run the existing Node.js safety check on given files."""
    if not files:
        return {"validation": {"status": "PASS"}, "findings": []}

    script = Path(__file__).resolve().parent.parent.parent / "scripts" / "safety_check.js"
    result = subprocess.run(
        ["node", str(script), *files, "--json"],
        capture_output=True, text=True, encoding="utf-8",
    )
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        return {"validation": {"status": "ERROR"}, "findings": [], "raw": result.stdout}


def main() -> int:
    files = get_staged_files()
    if not files:
        print("[pre-commit] No staged files. Skipping safety check.")
        return 0

    print(f"[pre-commit] Scanning {len(files)} staged file(s)...")
    report = run_safety_check(files)

    status = report.get("validation", {}).get("status", "PASS")
    findings = report.get("findings", [])
    critical = sum(1 for f in findings if f.get("severity") == "critical")
    high = sum(1 for f in findings if f.get("severity") == "high")

    print(f"[pre-commit] Findings: {len(findings)} ({critical} critical, {high} high)")

    if status == "BLOCKED":
        print("[pre-commit] BLOCKED — resolve critical/high issues before committing.")
        for f in findings:
            if f.get("severity") in ("critical", "high"):
                print(f"  [{f['severity'].upper()}] {f['file']}: {f['label']}")
        return 1

    if status == "WARNING":
        print("[pre-commit] WARNING — review findings before pushing.")

    print("[pre-commit] PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
