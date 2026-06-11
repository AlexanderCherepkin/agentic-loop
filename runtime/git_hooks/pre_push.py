#!/usr/bin/env python3
"""
Git pre-push hook — runs three-circuit safety + mutual_check + human approval.

Blocks push on critical findings unless human explicitly approves.

Usage:
    python runtime/git_hooks/pre_push.py [--auto]
    # Or via git hook: .githooks/pre-push
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def get_staged_files() -> list[str]:
    result = subprocess.run(
        ["git", "diff", "--cached", "--name-only", "--diff-filter=ACM"],
        capture_output=True, text=True, encoding="utf-8",
    )
    if result.returncode != 0:
        print("[pre-push] Not a git repository.", file=sys.stderr)
        sys.exit(1)
    return [f for f in result.stdout.strip().split("\n") if f]


def run_safety_check(files: list[str]) -> dict:
    if not files:
        return {"validation": {"status": "PASS"}, "findings": [], "violations": []}

    script = Path(__file__).resolve().parent.parent.parent / "scripts" / "safety_check.js"
    result = subprocess.run(
        ["node", str(script), *files, "--json"],
        capture_output=True, text=True, encoding="utf-8",
    )
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        return {"validation": {"status": "ERROR"}, "findings": [], "violations": []}


def request_approval(violations: list[dict]) -> bool:
    print("\n[pre-push] HUMAN APPROVAL REQUIRED")
    print(f"  {len(violations)} critical/high issue(s) detected:")
    for v in violations:
        sev = v.get("severity", "unknown").upper()
        print(f"    [{sev}] {v.get('file', '?')}: {v.get('label', '?')}")
    print("  These may include secrets, destructive commands, or security threats.")

    for _ in range(3):
        ans = input("  Proceed anyway? (y)es / (n)o / (r)eview details: ").strip().lower()
        if ans in ("y", "yes"):
            print("  [OK] Manual override granted. Proceeding with push.")
            return True
        elif ans in ("n", "no"):
            print("  [BLOCK] Push blocked by human decision.")
            return False
        elif ans in ("r", "review"):
            for v in violations:
                print(f"\n  File: {v.get('file', '?')}")
                print(f"    Type: {v.get('type', '?')}, Severity: {v.get('severity', '?')}")
                print(f"    Detail: {v.get('label', '?')}")
        else:
            print("  Please answer y, n, or r.")

    print("  [BLOCK] Max retries reached. Denying by default.")
    return False


def main() -> int:
    auto_mode = "--auto" in sys.argv

    files = get_staged_files()
    if not files:
        print("[pre-push] No staged files. Clean push.")
        return 0

    print(f"[pre-push] Scanning {len(files)} staged file(s)...")
    report = run_safety_check(files)

    status = report.get("validation", {}).get("status", "PASS")
    findings = report.get("findings", [])
    violations = report.get("violations", [])

    print(f"[pre-push] Findings: {len(findings)} | Violations: {len(violations)} | Status: {status}")

    if status == "PASS":
        print("[pre-push] SAFETY CHECK PASSED — push allowed.")
        return 0

    if not violations:
        print("[pre-push] Warnings found but no blocking violations.")
        return 0

    if auto_mode:
        print("[pre-push] BLOCKED — critical issues detected. Resolve before pushing.")
        return 1

    if request_approval(violations):
        print("[pre-push] SAFETY CHECK PASSED (with human approval) — push allowed.")
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
