#!/usr/bin/env python3
"""Agentic Loop health check for the agent bot.

Prints a concise 5-10 second status report covering:
- agent count
- validator status
- MCP server status
- pytest core suite status
- actionable repair recommendation

Usage:
    python .agent_loop/scripts/health_check.py
    python .agent_loop/scripts/health_check.py --json

Exit codes:
    0 — all checks healthy
    1 — one or more checks failed
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
AGENT_LOOP_DIR = PROJECT_ROOT / ".agent_loop"
CROSS_REF_SCRIPT = AGENT_LOOP_DIR / "scripts" / "validate_cross_references.js"
CONSISTENCY_SCRIPT = AGENT_LOOP_DIR / "scripts" / "validate_consistency.js"
COVERAGE_SCRIPT = AGENT_LOOP_DIR / "scripts" / "validate_runtime_coverage.py"

EXPECTED_AGENTS = 272
EXPECTED_MCP_SERVERS = 16


def run(cmd: list[str], timeout: int = 60, **kwargs: Any) -> subprocess.CompletedProcess:
    return subprocess.run(
        cmd,
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        timeout=timeout,
        **kwargs,
    )


def check_agents() -> dict[str, Any]:
    start = time.perf_counter()
    result = run(["node", str(CROSS_REF_SCRIPT)], timeout=30)
    elapsed = time.perf_counter() - start

    total_match = re.search(r"Total agents/files:\s+(\d+)", result.stdout)
    broken_match = re.search(r"Broken links:\s+(\d+|NONE)", result.stdout)
    isolated_match = re.search(r"Isolated agents \(no incoming refs\):\s+(\d+|NONE)", result.stdout)

    total = int(total_match.group(1)) if total_match else 0
    broken = 0 if broken_match and broken_match.group(1) == "NONE" else int(broken_match.group(1) or 0)
    isolated = 0 if isolated_match and isolated_match.group(1) == "NONE" else int(isolated_match.group(1) or 0)

    return {
        "label": "Agents",
        "ok": result.returncode == 0 and total >= EXPECTED_AGENTS and broken == 0 and isolated == 0,
        "value": f"{total} agents",
        "details": f"broken_links={broken}, isolated={isolated}",
        "elapsed_sec": round(elapsed, 2),
        "raw": {"stdout": result.stdout, "stderr": result.stderr, "returncode": result.returncode},
    }


def check_validators() -> dict[str, Any]:
    start = time.perf_counter()
    cross = run(["node", str(CROSS_REF_SCRIPT)], timeout=30)
    consistency = run(["node", str(CONSISTENCY_SCRIPT)], timeout=30)
    elapsed = time.perf_counter() - start

    cross_ok = cross.returncode == 0 and "clean" in cross.stdout.lower()
    consistency_ok = consistency.returncode == 0 and (
        "All agents consistent" in consistency.stdout
        or ("Errors: 0" in consistency.stdout and "Warnings: 0" in consistency.stdout)
    )

    errors_match = re.search(r"Errors:\s+(\d+)", consistency.stdout)
    warnings_match = re.search(r"Warnings:\s+(\d+)", consistency.stdout)
    errors = int(errors_match.group(1)) if errors_match else 0
    warnings = int(warnings_match.group(1)) if warnings_match else 0

    return {
        "label": "Validators",
        "ok": cross_ok and consistency_ok,
        "value": "cross-ref " + ("OK" if cross_ok else "FAIL") + ", consistency " + ("OK" if consistency_ok else "FAIL"),
        "details": f"errors={errors}, warnings={warnings}",
        "elapsed_sec": round(elapsed, 2),
        "raw": {
            "cross_returncode": cross.returncode,
            "consistency_returncode": consistency.returncode,
        },
    }


def check_runtime_coverage() -> dict[str, Any]:
    start = time.perf_counter()
    result = run([sys.executable, str(COVERAGE_SCRIPT)], timeout=30)
    elapsed = time.perf_counter() - start

    ok = result.returncode == 0 and "[OK]" in result.stdout
    loaded_match = re.search(r"Loaded agents:\s+(\d+)", result.stdout)
    loaded = int(loaded_match.group(1)) if loaded_match else 0

    return {
        "label": "Runtime coverage",
        "ok": ok,
        "value": f"{loaded} agents referenced",
        "details": "coverage_validator" if ok else "unreachable agents detected",
        "elapsed_sec": round(elapsed, 2),
        "raw": {"stdout": result.stdout, "stderr": result.stderr, "returncode": result.returncode},
    }


def check_mcp_servers() -> dict[str, Any]:
    start = time.perf_counter()
    result = run([sys.executable, "-m", "mcp_servers.bootstrap", "--test"], timeout=60)
    elapsed = time.perf_counter() - start

    pass_count = len(re.findall(r"\[PASS\]", result.stdout))
    fail_count = len(re.findall(r"\[FAIL\]", result.stdout))
    operational_match = re.search(r"(\d+/\d+)\s+servers operational", result.stdout)
    operational = operational_match.group(1) if operational_match else f"{pass_count}/{pass_count + fail_count}"

    return {
        "label": "MCP servers",
        "ok": pass_count == EXPECTED_MCP_SERVERS and fail_count == 0,
        "value": f"{operational} operational",
        "details": f"pass={pass_count}, fail={fail_count}",
        "elapsed_sec": round(elapsed, 2),
        "raw": {"stdout": result.stdout, "stderr": result.stderr, "returncode": result.returncode},
    }


def check_pytest_core() -> dict[str, Any]:
    start = time.perf_counter()
    # Use default verbosity so pytest prints the final "N passed, M deselected" line.
    result = run([sys.executable, "-m", "pytest", "-m", "core"], timeout=120)
    elapsed = time.perf_counter() - start

    summary_match = re.search(r"(\d+)\s+passed(?:,\s+(\d+)\s+failed)?", result.stdout)
    passed = int(summary_match.group(1)) if summary_match else 0
    failed = int(summary_match.group(2) or 0) if summary_match else 0
    if failed == 0 and result.returncode != 0:
        failed_match = re.search(r"(\d+)\s+failed", result.stdout)
        failed = int(failed_match.group(1)) if failed_match else 1
    ok = result.returncode == 0 and passed > 0 and failed == 0

    return {
        "label": "pytest core",
        "ok": ok,
        "value": f"{passed} passed" + (f", {failed} failed" if failed else ""),
        "details": f"exit_code={result.returncode}",
        "elapsed_sec": round(elapsed, 2),
        "raw": {"stdout": result.stdout, "stderr": result.stderr, "returncode": result.returncode},
    }


def build_recommendations(checks: list[dict[str, Any]]) -> list[str]:
    recs: list[str] = []

    agents = next((c for c in checks if c["label"] == "Agents"), None)
    if agents and not agents["ok"]:
        if EXPECTED_AGENTS not in agents["value"]:
            recs.append(f"Agent count mismatch: expected {EXPECTED_AGENTS}. Review newly added or deleted agent specs.")
        if "broken_links" in agents["details"] and "broken_links=0" not in agents["details"]:
            recs.append("Run `node .agent_loop/scripts/validate_cross_references.js` and fix broken agent references.")
        if "isolated=" in agents["details"] and "isolated=0" not in agents["details"]:
            recs.append("Isolated agents detected: ensure every agent is referenced from at least one other agent or ARCHITECTURE.md/main_loop.md.")

    validators = next((c for c in checks if c["label"] == "Validators"), None)
    if validators and not validators["ok"]:
        recs.append("Run validators and fix reported template/naming/cycle/safety issues before continuing.")

    coverage = next((c for c in checks if c["label"] == "Runtime coverage"), None)
    if coverage and not coverage["ok"]:
        recs.append("Run `python .agent_loop/scripts/validate_runtime_coverage.py` and add missing agents to runtime/engine/agent_invocation_map.py.")

    mcp = next((c for c in checks if c["label"] == "MCP servers"), None)
    if mcp and not mcp["ok"]:
        recs.append("MCP bootstrap failure. Run `python -m mcp_servers.bootstrap --test`, check optional dependencies and env vars.")

    tests = next((c for c in checks if c["label"] == "pytest core"), None)
    if tests and not tests["ok"]:
        recs.append("Core pytest suite failing. Run `pytest -m core -v` to identify regressions.")

    if not recs:
        recs.append("All checks healthy. Proceed with next increment.")

    return recs


def main() -> int:
    parser = argparse.ArgumentParser(description="Agentic Loop health check")
    parser.add_argument("--json", action="store_true", help="Emit JSON report")
    args = parser.parse_args()

    overall_start = time.perf_counter()

    checks = [
        check_agents(),
        check_validators(),
        check_runtime_coverage(),
        check_mcp_servers(),
        check_pytest_core(),
    ]

    recommendations = build_recommendations(checks)
    overall_elapsed = time.perf_counter() - overall_start
    all_ok = all(c["ok"] for c in checks)

    if args.json:
        report = {
            "healthy": all_ok,
            "overall_elapsed_sec": round(overall_elapsed, 2),
            "checks": checks,
            "recommendations": recommendations,
        }
        print(json.dumps(report, indent=2, ensure_ascii=False))
        return 0 if all_ok else 1

    status = "HEALTHY" if all_ok else "DEGRADED"
    print(f"=== Agentic Loop Health Check - {status} ({round(overall_elapsed, 2)} s) ===")
    print()
    for c in checks:
        icon = "[OK]" if c["ok"] else "[FAIL]"
        print(f"{icon} {c['label']:<14} {c['value']:<30} ({c['details']}) [{c['elapsed_sec']} s]")
    print()
    print("Recommendations:")
    for r in recommendations:
        print(f"  - {r}")
    print()

    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
