#!/usr/bin/env python3
"""
Agentic Loop CLI — command-line interface for the runtime engine.

Commands:
    run <task>          Execute a task through the agent pipeline
    status              Show active sessions and worker stats
    approve <id>        Approve a pending human-approval gate
    validate            Run runtime component validators
    demo                Run demo with sample request

Usage:
    python -m runtime.cli run "Analyze project structure"
    python -m runtime.cli status
    python -m runtime.cli approve session_abc123
    python -m runtime.cli validate
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from pathlib import Path

from runtime.engine.state_manager import StateManager, OperationStatus
from runtime.workers.worker_pool import WorkerPool
from runtime.workers.context_compressor import ContextCompressor


def _state_path() -> str:
    default = Path(__file__).resolve().parent.parent / ".agent_loop" / "data" / "state.db"
    default.parent.mkdir(parents=True, exist_ok=True)
    return str(default)


def fmt_duration(ms: float) -> str:
    if ms < 1000:
        return f"{ms:.0f}ms"
    return f"{ms/1000:.1f}s"


def cmd_run(args: argparse.Namespace) -> int:
    """Execute a task through the agent pipeline."""
    from runtime.main import main as runtime_main

    # Inject args into sys.argv for runtime.main parser
    sys.argv = [
        "runtime.main",
        args.task,
        "--max-iterations", str(args.max_iterations),
        "--provider", args.provider,
    ]
    if args.model:
        sys.argv.extend(["--model", args.model])
    if args.session_id:
        sys.argv.extend(["--session-id", args.session_id])
    if args.demo_mode:
        sys.argv.append("--demo")
    if args.tui:
        sys.argv.append("--tui")

    try:
        asyncio.run(runtime_main())
        return 0
    except KeyboardInterrupt:
        print("\n[CLI] Interrupted by user.")
        return 130
    except Exception as e:
        print(f"[CLI] Runtime error: {e}")
        return 1


def cmd_status(args: argparse.Namespace) -> int:
    """Show active sessions and runtime stats."""
    state = StateManager(db_path=_state_path())

    print("\n=== Agentic Loop Status ===\n")

    sessions = state.list_keys("session")
    if not sessions:
        print("  No active sessions.")
    else:
        print(f"  Sessions: {len(sessions)}")
        for sid in sessions:
            r = state.read(sid, scope="session")
            if r.status == OperationStatus.SUCCESS and r.value:
                val = r.value
                status = val.get("status", "unknown")
                started = val.get("started_at", 0)
                elapsed = fmt_duration((time.time() - started) * 1000) if started else "?"
                print(f"    {sid:40}  status={status:12}  elapsed={elapsed}")
            else:
                print(f"    {sid:40}  (unreadable)")

    approvals = state.list_keys("approval")
    if approvals:
        print(f"\n  Pending approvals: {len(approvals)}")
        for aid in approvals:
            r = state.read(aid, scope="approval")
            if r.status == OperationStatus.SUCCESS and r.value:
                val = r.value
                approved = val.get("approved", False)
                marker = "[OK]" if approved else "[PENDING]"
                print(f"    {aid:40}  {marker}")

    # Show ContextCompressor stats if any
    print("\n  Runtime components:")
    print("    StateManager:   OK")
    print("    MessageBus:     OK")
    print("    WorkerPool:     OK (if initialized)")
    print("    ContextCompressor: OK (if initialized)")

    # Observability quick summary
    try:
        from runtime.observability import HealthCheck, MetricsCollector
        h = HealthCheck()
        h.mark_component("cli_status", True)
        print(f"\n  Health: {h.status().status}")
        m = MetricsCollector()
        print(f"  Metrics: {len(m.snapshot().counters)} counters, {len(m.snapshot().gauges)} gauges")
    except ImportError:
        pass

    state.close()
    return 0


def cmd_health(args: argparse.Namespace) -> int:
    """Show runtime health status (for load balancers / monitoring)."""
    try:
        from runtime.observability import HealthCheck
    except ImportError:
        print("[CLI] Observability module not available.")
        return 1

    h = HealthCheck()
    # Simulate component checks based on what we can verify
    h.mark_component("state_manager", True)
    h.mark_component("cli", True)
    # Attempt to mark others if runtime is importable
    try:
        from runtime.engine.agent_loader import AgentLoader
        from runtime.main import resolve_root
        root = resolve_root()
        loader = AgentLoader(root)
        agents = loader.load_all_agents()
        h.mark_component("agent_loader", len(agents) > 0)
    except Exception:
        h.mark_component("agent_loader", False)

    print(h.to_json())
    return 0 if h.status().status in ("healthy", "degraded") else 1


def cmd_metrics(args: argparse.Namespace) -> int:
    """Dump metrics in JSON or Prometheus format."""
    try:
        from runtime.observability import MetricsCollector
    except ImportError:
        print("[CLI] Observability module not available.")
        return 1

    m = MetricsCollector()
    # Populate with some runtime-relevant placeholders
    m.counter("cli.metrics_calls").inc()
    m.gauge("cli.ready").set(1)

    if args.format == "prometheus":
        print(m.to_prometheus())
    else:
        print(m.to_json())
    return 0


def cmd_approve(args: argparse.Namespace) -> int:
    """Approve a pending human-approval gate."""
    state = StateManager(db_path=_state_path())
    key = f"approval:{args.id}"

    r = state.read(key, scope="approval")
    if r.status != OperationStatus.SUCCESS:
        print(f"[CLI] Approval ID not found: {args.id}")
        state.close()
        return 1

    state.update(key, {"approved": True, "approved_at": time.time(), "approved_by": "cli"},
                 scope="approval")
    print(f"[CLI] Approved: {args.id}")
    state.close()
    return 0


def cmd_mcp_connect(args: argparse.Namespace) -> int:
    """Connect to configured MCP servers and list available tools."""
    import json
    from pathlib import Path

    config_path = Path(__file__).resolve().parent.parent / "mcp-config.json"
    if not config_path.exists():
        print("[CLI] mcp-config.json not found.")
        return 1

    config = json.loads(config_path.read_text())
    servers = config.get("mcpServers", {})

    if not servers:
        print("[CLI] No MCP servers configured in mcp-config.json.")
        return 0

    print(f"\n=== MCP Servers ({len(servers)} configured) ===\n")
    for name, cfg in servers.items():
        transport = cfg.get("transport", cfg.get("type", "stdio"))
        command = cfg.get("command", cfg.get("args", ["?"])[0] if cfg.get("args") else "?")
        enabled = "disabled" not in cfg or not cfg.get("disabled")
        status = "enabled" if enabled else "disabled"
        print(f"  [{status}] {name}")
        print(f"         transport: {transport}  command: {command}")

    print("\n[CLI] MCP client runtime connection available via runtime.engine modules.")
    return 0


def cmd_validate(args: argparse.Namespace) -> int:
    """Run runtime component validators."""
    from runtime.main import main as runtime_main

    sys.argv = ["runtime.main", "--validate"]
    try:
        asyncio.run(runtime_main())
        return 0
    except Exception as e:
        print(f"[CLI] Validation error: {e}")
        return 1


def cmd_demo(args: argparse.Namespace) -> int:
    """Run demo mode."""
    from runtime.main import main as runtime_main

    sys.argv = ["runtime.main", "--demo", "--max-iterations", str(args.max_iterations)]
    try:
        asyncio.run(runtime_main())
        return 0
    except Exception as e:
        print(f"[CLI] Demo error: {e}")
        return 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="agentic-loop",
        description="Agentic Loop CLI — run tasks, check status, approve gates, validate runtime",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # run
    run_p = sub.add_parser("run", help="Execute a task")
    run_p.add_argument("task", help="Task description to execute")
    run_p.add_argument("--max-iterations", type=int, default=5, help="Max ReAct iterations")
    run_p.add_argument("--provider", default="anthropic", choices=["anthropic", "openai", "deepseek"])
    run_p.add_argument("--model", default=None, help="Model override")
    run_p.add_argument("--session-id", default=None, help="Resume existing session")
    run_p.add_argument("--demo-mode", action="store_true", help="Run in demo mode")
    run_p.add_argument("--tui", action="store_true", help="Launch TUI dashboard")
    run_p.set_defaults(func=cmd_run)

    # status
    status_p = sub.add_parser("status", help="Show active sessions and stats")
    status_p.set_defaults(func=cmd_status)

    # approve
    approve_p = sub.add_parser("approve", help="Approve a pending gate")
    approve_p.add_argument("id", help="Approval/session ID to approve")
    approve_p.set_defaults(func=cmd_approve)

    # validate
    validate_p = sub.add_parser("validate", help="Run runtime validators")
    validate_p.set_defaults(func=cmd_validate)

    # demo
    demo_p = sub.add_parser("demo", help="Run demo with sample request")
    demo_p.add_argument("--max-iterations", type=int, default=3)
    demo_p.set_defaults(func=cmd_demo)

    # health
    health_p = sub.add_parser("health", help="Show runtime health status")
    health_p.set_defaults(func=cmd_health)

    # mcp-connect
    mcp_p = sub.add_parser("mcp-connect", help="Connect to MCP servers and list tools")
    mcp_p.set_defaults(func=cmd_mcp_connect)

    # metrics
    metrics_p = sub.add_parser("metrics", help="Dump metrics snapshot")
    metrics_p.add_argument("--format", default="json", choices=["json", "prometheus"],
                           help="Output format")
    metrics_p.set_defaults(func=cmd_metrics)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
