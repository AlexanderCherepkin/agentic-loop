#!/usr/bin/env python3
"""CLI for /skill, /learn, and wiki operations.

This script is the runtime entry point for the LLM Wiki and skill commands.
It can be invoked directly or wrapped by a Claude Code skill.

Usage:
    python .agent_loop/scripts/skill_cli.py skill <name-or-source>
    python .agent_loop/scripts/skill_cli.py learn <path|URL|note|this-chat>
    python .agent_loop/scripts/skill_cli.py wiki-ingest <path|URL|note>
    python .agent_loop/scripts/skill_cli.py wiki-query "question"
    python .agent_loop/scripts/skill_cli.py wiki-lint
    python .agent_loop/scripts/skill_cli.py apply --operation <op> --approval approved --proposal <json>
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from runtime.wiki import WikiConfig, WikiEngine


def _wiki_engine() -> WikiEngine:
    cfg = WikiConfig(memory_root=PROJECT_ROOT / "memory")
    return WikiEngine(cfg)


def _build_skill_proposal(target: str, raw: str | None = None) -> dict[str, Any]:
    """Build a proposal for creating a skill from a name or source text."""
    name = target.strip().lower()
    trigger = f"User invokes /{name} or mentions the related task."
    description = f"Reusable Claude Code skill for {name}."
    if raw:
        words = len(raw.split())
        description = f"Auto-proposed skill from source ({words} words): {name}."
    return {
        "operation": "create_skill",
        "requires_approval": True,
        "proposal": {
            "name": name,
            "trigger": trigger,
            "description": description,
            "decision_flow": [],
            "failure_modes": [],
            "gotchas": [],
        },
    }


def _build_learn_proposal(source: str) -> dict[str, Any]:
    """Build a proposal for ingesting a source into the wiki."""
    if source in ("this-chat", "this chat", "этот чат"):
        source = "[transcript placeholder — provide chat text or use session export]"
    return {
        "operation": "ingest_wiki",
        "requires_approval": True,
        "proposal": [
            {
                "name": "auto-ingested-source",
                "type": "source",
                "description": "Auto-ingested source from /learn command.",
                "content": source,
            }
        ],
    }


def _print_json(payload: dict[str, Any]) -> int:
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def cmd_skill(args: argparse.Namespace) -> int:
    raw = " ".join(args.target).strip() if isinstance(args.target, list) else args.target.strip()
    if not raw:
        return _print_json({"command": "skill", "error": "Missing skill name or source."})
    return _print_json(_build_skill_proposal(raw, raw if args.from_source else None))


def cmd_learn(args: argparse.Namespace) -> int:
    return _print_json(_build_learn_proposal(args.source))


def cmd_wiki_ingest(args: argparse.Namespace) -> int:
    return _print_json(_build_learn_proposal(args.source))


def cmd_wiki_query(args: argparse.Namespace) -> int:
    engine = _wiki_engine()
    result = engine.query(args.question)
    return _print_json({
        "command": "wiki-query",
        "summary": result.summary,
        "pages": [p.to_dict() for p in result.relevant_pages],
    })


def cmd_wiki_lint(args: argparse.Namespace) -> int:
    engine = _wiki_engine()
    result = engine.lint()
    return _print_json({
        "command": "wiki-lint",
        "summary": result.summary,
        "issues": result.issues,
        "requires_approval": result.requires_approval,
    })


def cmd_apply(args: argparse.Namespace) -> int:
    """Apply an approved proposal by writing files through SkillIntegrationEngine."""
    from runtime.skill_integration import SkillIntegrationConfig, SkillIntegrationEngine

    if args.approval not in ("approved", "modify"):
        return _print_json({"command": "apply", "status": "rejected", "reason": "approval must be approved or modify"})

    proposal: dict[str, Any] | list[dict[str, Any]] | None = None
    if args.proposal:
        try:
            proposal = json.loads(args.proposal)
        except json.JSONDecodeError as exc:
            return _print_json({"command": "apply", "status": "error", "reason": f"Invalid proposal JSON: {exc}"})

    engine = SkillIntegrationEngine(SkillIntegrationConfig(workspace_root=PROJECT_ROOT))
    skill_candidate = None
    wiki_updates = None
    lint_plan = None

    if args.operation == "create_skill" or args.operation == "update_skill":
        skill_candidate = proposal if isinstance(proposal, dict) else None
    elif args.operation == "ingest_wiki":
        wiki_updates = proposal if isinstance(proposal, list) else None
    elif args.operation == "lint_wiki":
        lint_plan = proposal if isinstance(proposal, list) else None

    result = engine.apply(
        operation=args.operation,
        user_approval=args.approval,
        skill_candidate=skill_candidate,
        wiki_updates=wiki_updates,
        lint_plan=lint_plan,
        session_id=args.session_id,
    )
    return _print_json({"command": "apply", **result.to_dict()})


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Skill and wiki CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    p_skill = sub.add_parser("skill", help="Propose a skill")
    p_skill.add_argument("target", nargs="+", help="Skill name or source")
    p_skill.add_argument("--from-source", action="store_true", help="Treat target as source text")

    p_learn = sub.add_parser("learn", help="Propose a skill/learn page from source")
    p_learn.add_argument("source", help="Path, URL, note, or 'this-chat'")

    p_ingest = sub.add_parser("wiki-ingest", help="Propose ingesting raw material into wiki")
    p_ingest.add_argument("source", help="Path, URL, or note")

    p_query = sub.add_parser("wiki-query", help="Query wiki pages")
    p_query.add_argument("question", help="Question to ask")

    p_lint = sub.add_parser("wiki-lint", help="Lint the wiki")

    p_apply = sub.add_parser("apply", help="Apply an approved proposal")
    p_apply.add_argument("--operation", required=True, choices=["create_skill", "update_skill", "ingest_wiki", "lint_wiki"])
    p_apply.add_argument("--approval", required=True, choices=["approved", "modify", "rejected"])
    p_apply.add_argument("--proposal", help="JSON proposal to apply")
    p_apply.add_argument("--session-id", default="", help="Session ID for audit")

    args = parser.parse_args(argv)
    handlers = {
        "skill": cmd_skill,
        "learn": cmd_learn,
        "wiki-ingest": cmd_wiki_ingest,
        "wiki-query": cmd_wiki_query,
        "wiki-lint": cmd_wiki_lint,
        "apply": cmd_apply,
    }
    return handlers[args.command](args)


if __name__ == "__main__":
    raise SystemExit(main())
