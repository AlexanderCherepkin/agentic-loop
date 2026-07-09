#!/usr/bin/env python3
"""Runtime coverage validator.

Verifies that every .agent_loop/*.md spec returned by AgentLoader.load_all_agents()
is referenced by at least one runtime phase, MCP category/tool, or runtime entry
point. Exits 0 when coverage is complete, nonzero otherwise.

Usage:
    python .agent_loop/scripts/validate_runtime_coverage.py
    python .agent_loop/scripts/validate_runtime_coverage.py --json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from runtime.engine.agent_invocation_map import all_referenced_paths  # noqa: E402
from runtime.engine.agent_loader import AgentLoader  # noqa: E402

EXPECTED_AGENT_COUNT = 254


def main() -> int:
    parser = argparse.ArgumentParser(description="Runtime agent coverage validator")
    parser.add_argument("--json", action="store_true", help="Emit JSON report")
    args = parser.parse_args()

    loader = AgentLoader(str(PROJECT_ROOT / ".agent_loop"))
    loaded = loader.load_all_agents()
    loaded_paths = set(loaded.keys())

    referenced = all_referenced_paths()
    # runtime/main.py is the concrete entry point for main_loop.md.
    referenced.add("main_loop.md")

    unreachable = sorted(loaded_paths - referenced)
    missing = sorted(referenced - loaded_paths)

    count_ok = len(loaded_paths) == EXPECTED_AGENT_COUNT
    coverage_ok = not unreachable

    if args.json:
        report = {
            "coverage_ok": coverage_ok and count_ok,
            "expected_count": EXPECTED_AGENT_COUNT,
            "loaded_count": len(loaded_paths),
            "referenced_count": len(referenced),
            "unreachable_agents": unreachable,
            "referenced_but_missing": missing,
        }
        print(json.dumps(report, indent=2, ensure_ascii=False))
        return 0 if coverage_ok and count_ok else 1

    print("=== Runtime Agent Coverage Validator ===")
    print(f"Loaded agents: {len(loaded_paths)} (expected {EXPECTED_AGENT_COUNT})")
    print(f"Referenced by runtime/MCP map: {len(referenced)}")
    if not count_ok:
        print(f"[FAIL] Agent count mismatch: expected {EXPECTED_AGENT_COUNT}, got {len(loaded_paths)}")
    if missing:
        print(f"[WARN] Referenced but not loaded: {len(missing)}")
        for p in missing:
            print(f"  - {p}")
    if unreachable:
        print(f"[FAIL] Unreachable agents: {len(unreachable)}")
        for p in unreachable:
            print(f"  - {p}")
        return 1

    print("[OK] Every loaded agent is reachable from a runtime phase, MCP category, or tool.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
