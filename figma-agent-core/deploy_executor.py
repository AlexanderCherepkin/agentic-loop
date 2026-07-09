"""CLI wrapper for runtime/deploy/DeployEngine.

Executes Vercel/Netlify/generic deploy for a generated Next.js site.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from runtime.deploy import DeployConfig, DeployEngine


def main() -> None:
    parser = argparse.ArgumentParser(description="Deploy executor: run Vercel/Netlify/generic deploy.")
    parser.add_argument("--target-dir", default=".", help="Next.js project root.")
    parser.add_argument("--provider", default="vercel", choices=["vercel", "netlify", "generic"], help="Deploy provider.")
    parser.add_argument("--live", action="store_true", help="Run a real deploy (default is dry-run).")
    parser.add_argument("--build-command", default="pnpm build", help="Build command for generic/netlify provider.")
    parser.add_argument("--dist-dir", default="dist", help="Output directory for static export.")
    parser.add_argument("--env", default=None, help="JSON object of environment variables.")
    parser.add_argument("--timeout", type=float, default=300.0, help="Deploy command timeout in seconds.")
    args = parser.parse_args()

    env: dict[str, str] = {}
    if args.env:
        env = json.loads(args.env)

    config = DeployConfig(
        target_dir=args.target_dir,
        provider=args.provider,
        dry_run=not args.live,
        build_command=args.build_command,
        dist_dir=args.dist_dir,
        env=env,
        timeout=args.timeout,
    )
    engine = DeployEngine(args.target_dir, config)
    result = engine.run()

    report: dict[str, Any] = {
        "provider": result.provider,
        "command": result.command,
        "dry_run": result.dry_run,
        "success": result.success,
        "deploy_url": result.deploy_url,
        "returncode": result.returncode,
        "stdout": result.stdout,
        "stderr": result.stderr,
        "errors": result.errors,
        "notes": result.notes,
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))

    sys.exit(0 if result.success else 1)


if __name__ == "__main__":
    main()
