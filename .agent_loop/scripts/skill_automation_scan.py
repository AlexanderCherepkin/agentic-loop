#!/usr/bin/env python3
"""Skill automation scanner.

Detects markdown sources worth turning into Claude Code skills and decides
whether graphify needs a refresh after significant workspace changes.

Usage:
    python .agent_loop/scripts/skill_automation_scan.py scan
    python .agent_loop/scripts/skill_automation_scan.py graphify-update
    python .agent_loop/scripts/skill_automation_scan.py propose-skills
    python .agent_loop/scripts/skill_automation_scan.py --post-commit
"""

from __future__ import annotations

import argparse
import json
import logging
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from runtime.skill_automation import SkillAutomationConfig, SkillAutomationEngine

logger = logging.getLogger(__name__)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _write_state(result: dict[str, Any]) -> Path:
    state_path = PROJECT_ROOT / "data" / "skill_automation.jsonl"
    state_path.parent.mkdir(parents=True, exist_ok=True)
    entry = {"type": "scan", "timestamp": _now(), "result": result}
    with state_path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return state_path


def _maybe_store_memory(actions: list[dict[str, Any]]) -> None:
    """Optional durable memory write; silently skips if runtime.memory is unavailable."""
    try:
        from runtime.memory.memory_manager import MemoryManager
    except Exception:
        return
    try:
        mm = MemoryManager()
        for action in actions:
            if action.get("type") != "learn_from_source":
                continue
            mm.store(
                {
                    "id": f"skill-candidate-{Path(action['path']).stem}-{_now()}",
                    "type": "project",
                    "title": f"Skill candidate: {action.get('path')}",
                    "body": action.get("reason", ""),
                    "tags": ["skill_candidate", "learn-from-source", "automation"],
                    "priority": 4 if action.get("estimated_reuse") == "high" else 3,
                    "source": action.get("path"),
                }
            )
        mm.close()
    except Exception as e:
        logger.debug("memory write skipped: %s", e)


def _run_graphify_update() -> dict[str, Any]:
    try:
        result = subprocess.run(
            ["graphify", ".", "--update"],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        return {
            "command": "graphify . --update",
            "returncode": result.returncode,
            "stdout": result.stdout[-2000:],
            "stderr": result.stderr[-1000:],
        }
    except Exception as e:
        return {"command": "graphify . --update", "error": str(e)}


def cmd_scan(args: argparse.Namespace) -> int:
    config = SkillAutomationConfig(
        workspace_root=PROJECT_ROOT,
        graphify_min_changed_files=args.graphify_min_changed_files,
        source_min_words=args.source_min_words,
    )
    engine = SkillAutomationEngine(config)
    result = engine.scan()
    actions = engine.propose_actions()
    _write_state(result.to_dict())
    if args.memory:
        _maybe_store_memory(actions)

    print(json.dumps({
        "scan_time": result.scan_time,
        "source_candidates": [c.to_dict() for c in result.source_candidates],
        "graphify_need": result.graphify_need.to_dict(),
        "actions": actions,
    }, ensure_ascii=False, indent=2))
    return 0


def cmd_graphify_update(args: argparse.Namespace) -> int:
    config = SkillAutomationConfig(
        workspace_root=PROJECT_ROOT,
        graphify_min_changed_files=args.graphify_min_changed_files,
    )
    engine = SkillAutomationEngine(config)
    need = engine._detect_graphify_need()
    if not need.needs_update and not args.force:
        print(json.dumps({
            "needs_update": False,
            "reason": need.reason,
        }, ensure_ascii=False, indent=2))
        return 0

    if need.warning_large_corpus and not args.force:
        print(json.dumps({
            "needs_update": True,
            "warning_large_corpus": True,
            "reason": need.reason,
            "message": "Large corpus detected; run with --force to execute graphify . --update",
        }, ensure_ascii=False, indent=2))
        return 0

    run_result = _run_graphify_update()
    _write_state({"type": "graphify_update", "timestamp": _now(), "run": run_result})
    print(json.dumps(run_result, ensure_ascii=False, indent=2))
    return run_result.get("returncode", 0) if isinstance(run_result.get("returncode"), int) else 0


def cmd_propose_skills(args: argparse.Namespace) -> int:
    config = SkillAutomationConfig(
        workspace_root=PROJECT_ROOT,
        source_min_words=args.source_min_words,
    )
    engine = SkillAutomationEngine(config)
    already = engine._load_already_proposed()
    candidates = engine._detect_new_sources(already)
    proposals = []
    for candidate in candidates:
        proposals.append({
            "type": "learn_from_source",
            "path": candidate.path,
            "reason": candidate.reason,
            "estimated_reuse": candidate.estimated_reuse,
            "requires_approval": True,
            "invocation": f"learn-from-source: {candidate.path}",
        })
    _write_state({"type": "propose_skills", "timestamp": _now(), "proposals": proposals})
    if args.memory:
        _maybe_store_memory(proposals)
    print(json.dumps(proposals, ensure_ascii=False, indent=2))
    return 0


def cmd_post_commit(args: argparse.Namespace) -> int:
    """Post-commit hook entry point: graphify update if needed, then record proposals."""
    config = SkillAutomationConfig(workspace_root=PROJECT_ROOT)
    engine = SkillAutomationEngine(config)
    result = engine.scan()
    actions = engine.propose_actions()
    _write_state(result.to_dict())
    _maybe_store_memory(actions)

    graphify_action = next(
        (a for a in actions if a.get("type") == "graphify_update"), None
    )
    if graphify_action and not graphify_action.get("warning_large_corpus"):
        run_result = _run_graphify_update()
        _write_state({"type": "graphify_update", "timestamp": _now(), "run": run_result})
        graphify_action["executed"] = run_result

    summary = {
        "source_proposals": len([a for a in actions if a.get("type") == "learn_from_source"]),
        "graphify_updated": bool(graphify_action and graphify_action.get("executed")),
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Skill automation scanner")
    parser.add_argument(
        "--graphify-min-changed-files",
        type=int,
        default=10,
        help="Threshold for triggering graphify update (default: 10)",
    )
    parser.add_argument(
        "--source-min-words",
        type=int,
        default=200,
        help="Minimum source word count to consider (default: 200)",
    )
    parser.add_argument(
        "--memory",
        action="store_true",
        help="Also write proposals to runtime memory store",
    )
    parser.add_argument(
        "--post-commit",
        action="store_true",
        help="Run post-commit automation (graphify update + proposals)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Execute graphify update even with large corpus warning",
    )

    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    if args.post_commit:
        return cmd_post_commit(args)

    # Without explicit subcommand, default to scan.
    return cmd_scan(args)


if __name__ == "__main__":
    raise SystemExit(main())
