"""Deployment packager for Figma-generated Next.js sites.

Generates ready-to-publish artifacts:
- package.json + next.config.ts + tsconfig.json + tailwind.config.ts
- vercel.json / netlify.toml
- .env.example
- README.md with deploy buttons
- deploy.sh one-click script
"""

import argparse
import json
import os
import textwrap
from pathlib import Path
from typing import Any, Dict, List, Optional


DEFAULT_NEXT_VERSION = "^15.1.0"
DEFAULT_REACT_VERSION = "^19.0.0"


def _safe_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2)


def _site_name(raw: Optional[str]) -> str:
    return " ".join(str(raw or "Figma Site").split()) or "Figma Site"


def _site_slug(raw: Optional[str]) -> str:
    name = _site_name(raw)
    slug = "".join(c if c.isalnum() or c.isspace() else " " for c in name).strip()
    slug = "-".join(slug.lower().split())
    return slug or "figma-site"


def generate_package_json(
    site_name: Optional[str] = None,
    next_version: str = DEFAULT_NEXT_VERSION,
    react_version: str = DEFAULT_REACT_VERSION,
    has_backend: bool = False,
    extra_scripts: Optional[Dict[str, str]] = None,
    extra_deps: Optional[Dict[str, str]] = None,
    extra_dev_deps: Optional[Dict[str, str]] = None,
) -> str:
    """Generate a package.json for a Next.js site produced by the Figma pipeline."""
    name = _site_slug(site_name)
    scripts: Dict[str, str] = {
        "dev": "next dev",
        "build": "next build",
        "start": "next start",
        "lint": "next lint",
        "typecheck": "tsc --noEmit",
    }
    scripts.update(extra_scripts or {})

    dependencies: Dict[str, str] = {
        "next": next_version,
        "react": react_version,
        "react-dom": react_version,
    }
    if has_backend:
        dependencies.setdefault("@prisma/client", "^6.0.0")
        dependencies.setdefault("zod", "^3.23.0")

    dev_dependencies: Dict[str, str] = {
        "typescript": "^5.7.0",
        "@types/node": "^22.0.0",
        "@types/react": "^19.0.0",
        "@types/react-dom": "^19.0.0",
        "tailwindcss": "^3.4.0",
        "postcss": "^8.4.0",
        "autoprefixer": "^10.4.0",
        "eslint": "^8.57.0",
        "eslint-config-next": next_version.lstrip("^").split(".")[0] + ".0.0",
    }
    if has_backend:
        dev_dependencies.setdefault("prisma", "^6.0.0")

    dependencies.update(extra_deps or {})
    dev_dependencies.update(extra_dev_deps or {})

    payload = {
        "name": name,
        "version": "0.1.0",
        "private": True,
        "scripts": scripts,
        "dependencies": dependencies,
        "devDependencies": dev_dependencies,
    }
    return _safe_json(payload)


def generate_next_config(
    output: str = "export",
    dist_dir: str = "dist",
    images_unoptimized: bool = True,
    trailing_slash: bool = False,
    base_path: str = "",
    asset_prefix: str = "",
) -> str:
    """Generate next.config.ts suitable for static or standalone hosting."""
    config: Dict[str, Any] = {
        "output": output,
        "distDir": dist_dir,
        "images": {"unoptimized": images_unoptimized},
        "trailingSlash": trailing_slash,
    }
    if base_path:
        config["basePath"] = base_path
    if asset_prefix:
        config["assetPrefix"] = asset_prefix
    if output == "export":
        config.setdefault("distDir", "dist")
    body = json.dumps(config, indent=2)
    return f"""import type {{ NextConfig }} from "next";

const nextConfig: NextConfig = {body};

export default nextConfig;
"""


def generate_tsconfig() -> str:
    """Generate a tsconfig.json tuned for Next.js App Router."""
    payload = {
        "compilerOptions": {
            "lib": ["dom", "dom.iterable", "es2022"],
            "allowJs": True,
            "skipLibCheck": True,
            "strict": True,
            "noEmit": True,
            "esModuleInterop": True,
            "module": "esnext",
            "moduleResolution": "bundler",
            "resolveJsonModule": True,
            "isolatedModules": True,
            "jsx": "preserve",
            "incremental": True,
            "plugins": [{"name": "next"}],
            "paths": {"@/*": ["./src/*"]},
        },
        "include": ["next-env.d.ts", "**/*.ts", "**/*.tsx", ".next/types/**/*.ts"],
        "exclude": ["node_modules"],
    }
    return _safe_json(payload)


def generate_tailwind_config(site_name: Optional[str] = None) -> str:
    """Generate a minimal but complete tailwind.config.ts for generated pages."""
    return """import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./src/app/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/components/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {},
      fontFamily: {},
    },
  },
  plugins: [],
};

export default config;
"""


def generate_postcss_config() -> str:
    """Generate postcss.config.mjs for Tailwind CSS."""
    return """/** @type {import('postcss-load-config').Config} */
const config = {
  plugins: {
    tailwindcss: {},
    autoprefixer: {},
  },
};

export default config;
"""


def generate_globals_css() -> str:
    """Generate a minimal src/app/globals.css using Tailwind directives."""
    return """@tailwind base;
@tailwind components;
@tailwind utilities;

:root {
  --background: #ffffff;
  --foreground: #171717;
}

body {
  color: var(--foreground);
  background: var(--background);
}
"""


def generate_vercel_json(
    framework: str = "nextjs",
    build_command: str = "pnpm build",
    output_directory: str = "dist",
    install_command: str = "pnpm install",
) -> str:
    """Generate vercel.json with framework and build settings."""
    payload = {
        "framework": framework,
        "buildCommand": build_command,
        "outputDirectory": output_directory,
        "installCommand": install_command,
        "crons": [],
    }
    return _safe_json(payload)


def generate_netlify_toml(
    build_command: str = "pnpm build",
    publish_dir: str = "dist",
    node_version: str = "22",
) -> str:
    """Generate netlify.toml for Next.js static deploy."""
    return f"""[build]
  command = "{build_command}"
  publish = "{publish_dir}"

[build.environment]
  NODE_VERSION = "{node_version}"
  NPM_FLAGS = "--version"

[[plugins]]
  package = "@netlify/plugin-nextjs"
"""


def generate_env_example(has_backend: bool = False) -> str:
    """Generate .env.example for the generated site."""
    lines = [
        "# Copy this file to .env.local and fill in real values.",
        "# NEVER commit .env.local.",
        "",
        "# Optional: analytics / third-party services",
        "# NEXT_PUBLIC_GA_ID=G-XXXXXXXXXX",
        "",
    ]
    if has_backend:
        lines.extend([
            "# Database (required for backend)",
            "# DATABASE_URL=postgresql://user:pass@localhost:5432/db",
            "",
        ])
    return "\n".join(lines)


def generate_readme(
    site_name: Optional[str] = None,
    base_url: str = "/",
    target: str = "vercel",
    has_backend: bool = False,
) -> str:
    """Generate README.md with one-click deploy buttons and local dev instructions."""
    name = _site_name(site_name)
    slug = _site_slug(site_name)
    vercel_button = f"[![Deploy with Vercel](https://vercel.com/button)](https://vercel.com/new/clone?repository-url=https://github.com/your-org/{slug}&project-name={slug}&repo-name={slug})"
    netlify_button = f"[![Deploy to Netlify](https://www.netlify.com/img/deploy/button.svg)](https://app.netlify.com/start/deploy?repository=https://github.com/your-org/{slug})"

    deploy_section = vercel_button if target == "vercel" else netlify_button
    if target == "both":
        deploy_section = f"{vercel_button}\n\n{netlify_button}"

    backend_section = ""
    if has_backend:
        backend_section = """
### Database setup
1. Copy `.env.example` to `.env.local` and set `DATABASE_URL`.
2. Run `npx prisma migrate dev` to apply the schema.
3. Restart the dev server.
"""

    return f"""# {name}

Generated from Figma by the Agentic Loop Figma Agent.

{deploy_section}

## Local development

```bash
pnpm install
pnpm dev
```

Open [http://localhost:3000](http://localhost:3000) to view the site.

## Build

```bash
pnpm build
```

The static export lands in `dist/` by default.
{backend_section}

## Environment variables

See `.env.example` for optional variables.
"""


def generate_deploy_script(
    target: str = "vercel",
    build_command: str = "pnpm build",
) -> str:
    """Generate a POSIX one-click deploy script."""
    if target == "vercel":
        cmd = "npx vercel --prod"
    elif target == "netlify":
        cmd = "npx netlify deploy --prod --dir=dist"
    else:
        cmd = f"{build_command} && echo 'Build complete. Upload dist/ to your host.'"

    return f"""#!/usr/bin/env bash
set -euo pipefail

# One-click deploy for the generated Figma site.
# Requires the matching CLI to be installed and authenticated.

{cmd}
"""


def package_site(
    output_dir: str,
    site_name: Optional[str] = None,
    base_url: str = "/",
    target: str = "vercel",
    has_backend: bool = False,
    next_version: str = DEFAULT_NEXT_VERSION,
    react_version: str = DEFAULT_REACT_VERSION,
    output_mode: str = "export",
    root_dir: Optional[str] = None,
    skip_existing: bool = True,
) -> List[str]:
    """Write all deployment artifacts into output_dir.

    Returns a list of written file paths (relative to output_dir).
    If skip_existing is True, files that already exist are left untouched
    (protects design_tokens-generated tailwind.config.ts / globals.css).
    """
    raw_base = Path(output_dir)
    if root_dir:
        root = Path(root_dir).resolve()
        if not raw_base.is_absolute():
            raw_base = root / raw_base
        base = Path(os.path.normpath(str(raw_base)))
        try:
            base.relative_to(root)
        except ValueError as exc:
            raise ValueError(f"Output directory outside workspace: {output_dir}") from exc
    else:
        base = raw_base.resolve()
    base.mkdir(parents=True, exist_ok=True)

    src_app = base / "src" / "app"
    src_app.mkdir(parents=True, exist_ok=True)

    files: Dict[str, str] = {
        "package.json": generate_package_json(
            site_name=site_name,
            next_version=next_version,
            react_version=react_version,
            has_backend=has_backend,
        ),
        "next.config.ts": generate_next_config(output=output_mode),
        "tsconfig.json": generate_tsconfig(),
        "tailwind.config.ts": generate_tailwind_config(site_name=site_name),
        "postcss.config.mjs": generate_postcss_config(),
        "src/app/globals.css": generate_globals_css(),
        "vercel.json": generate_vercel_json(output_directory="dist" if output_mode == "export" else ".next"),
        "netlify.toml": generate_netlify_toml(publish_dir="dist" if output_mode == "export" else ".next"),
        ".env.example": generate_env_example(has_backend=has_backend),
        "README.md": generate_readme(
            site_name=site_name,
            base_url=base_url,
            target=target,
            has_backend=has_backend,
        ),
        "deploy.sh": generate_deploy_script(target=target),
    }

    written: List[str] = []
    for relative_path, content in files.items():
        target_path = base / relative_path
        target_path.parent.mkdir(parents=True, exist_ok=True)
        if skip_existing and target_path.exists():
            continue
        target_path.write_text(content, encoding="utf-8")
        written.append(relative_path)

    # Make deploy.sh executable on POSIX systems.
    deploy_sh = base / "deploy.sh"
    if deploy_sh.exists():
        try:
            deploy_sh.chmod(0o755)
        except Exception:
            pass

    return written


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Deployment packager: generate ready-to-publish Next.js artifacts."
    )
    parser.add_argument(
        "--output-dir",
        default="generated-site",
        help="Directory to write deployment artifacts into.",
    )
    parser.add_argument(
        "--site-name",
        default=None,
        help="Human-readable site name and package name.",
    )
    parser.add_argument(
        "--base-url",
        default="/",
        help="Base URL of the published site.",
    )
    parser.add_argument(
        "--target",
        default="vercel",
        choices=["vercel", "netlify", "both"],
        help="Primary deployment target for README/deploy script.",
    )
    parser.add_argument(
        "--has-backend",
        action="store_true",
        help="Include backend/database dependencies and env vars.",
    )
    parser.add_argument(
        "--output-mode",
        default="export",
        choices=["export", "standalone"],
        help="Next.js output mode.",
    )
    parser.add_argument(
        "--root-dir",
        default=None,
        help="Workspace root for path containment check.",
    )
    args = parser.parse_args()

    written = package_site(
        output_dir=args.output_dir,
        site_name=args.site_name,
        base_url=args.base_url,
        target=args.target,
        has_backend=args.has_backend,
        output_mode=args.output_mode,
        root_dir=args.root_dir,
    )
    print(f"[PACKAGE] Deployment artifacts written to {args.output_dir}")
    for path in written:
        print(f"  - {path}")


if __name__ == "__main__":
    main()
