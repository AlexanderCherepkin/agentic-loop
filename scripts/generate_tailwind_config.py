#!/usr/bin/env python3
"""CLI adapter: DTCG design_tokens.json -> Tailwind config + CSS variables.

Usage:
    python scripts/generate_tailwind_config.py \
        --input design_tokens.json \
        --output tailwind.config.ts \
        --css-output src/app/globals.css

    python scripts/generate_tailwind_config.py \
        --input design_tokens.json \
        --output tailwind.config.ts \
        --patch \
        --strict
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from runtime.premium_design.tailwind_adapter import generate_tailwind_from_tokens


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate Tailwind config and CSS variables from DTCG tokens"
    )
    parser.add_argument(
        "--input",
        "-i",
        required=True,
        help="Path to design_tokens.json (DTCG format)",
    )
    parser.add_argument(
        "--output",
        "-o",
        default="tailwind.config.ts",
        help="Output path for tailwind.config.ts (default: tailwind.config.ts)",
    )
    parser.add_argument(
        "--css-output",
        "-c",
        help="Optional path for globals.css with CSS custom properties",
    )
    parser.add_argument(
        "--patch",
        action="store_true",
        help="Patch an existing tailwind.config.ts instead of overwriting",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        default=True,
        help="Fail if anti-slop violations are detected (default: true)",
    )
    parser.add_argument(
        "--no-strict",
        dest="strict",
        action="store_false",
        help="Allow generating config even if slop violations are found",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Print generated file paths and notes",
    )

    args = parser.parse_args()

    result = generate_tailwind_from_tokens(
        tokens_path=args.input,
        tailwind_output=args.output,
        css_output=args.css_output,
        patch_existing=args.patch,
        strict=args.strict,
    )

    if args.verbose:
        if result.tailwind_path:
            print(f"Tailwind config: {result.tailwind_path}")
        if result.css_path:
            print(f"CSS variables:   {result.css_path}")
        for note in result.notes:
            print(f"Note: {note}")

    if result.violations:
        print(f"Anti-Slop violations: {len(result.violations)}", file=sys.stderr)
        for v in result.violations:
            print(f"  - {v}", file=sys.stderr)
        if args.strict:
            return 1

    if args.verbose:
        print("OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
