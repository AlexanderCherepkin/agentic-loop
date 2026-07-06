"""Unit tests for figma-agent-core/deployment_packager.py."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent
PACKAGER_PATH = ROOT / "figma-agent-core" / "deployment_packager.py"


def _load_packager() -> Any:
    spec = importlib.util.spec_from_file_location("figma_deployment_packager", str(PACKAGER_PATH))
    module = importlib.util.module_from_spec(spec)
    sys.modules["figma_deployment_packager"] = module
    spec.loader.exec_module(module)
    return module


packager = _load_packager()


def test_generate_package_json_has_next_and_react() -> None:
    text = packager.generate_package_json(site_name="My Site")
    data = json.loads(text)
    assert data["name"] == "my-site"
    assert data["dependencies"]["next"].startswith("^")
    assert data["dependencies"]["react"].startswith("^")
    assert "build" in data["scripts"]
    assert "dev" in data["scripts"]


def test_generate_package_json_backend_adds_prisma_and_zod() -> None:
    text = packager.generate_package_json(has_backend=True)
    data = json.loads(text)
    assert "@prisma/client" in data["dependencies"]
    assert "zod" in data["dependencies"]
    assert "prisma" in data["devDependencies"]


def test_generate_next_config_export_mode() -> None:
    text = packager.generate_next_config(output="export", dist_dir="dist")
    assert 'import type { NextConfig } from "next";' in text
    assert '"output": "export"' in text
    assert '"distDir": "dist"' in text
    assert '"unoptimized": true' in text


def test_generate_tsconfig_has_paths() -> None:
    text = packager.generate_tsconfig()
    data = json.loads(text)
    assert data["compilerOptions"]["paths"]["@/*"] == ["./src/*"]


def test_generate_tailwind_config_targets_app_dirs() -> None:
    text = packager.generate_tailwind_config()
    assert "./src/app/**/*" in text
    assert "./src/components/**/*" in text


def test_generate_postcss_config_loads_tailwind() -> None:
    text = packager.generate_postcss_config()
    assert "tailwindcss" in text
    assert "autoprefixer" in text


def test_generate_globals_css_has_directives() -> None:
    text = packager.generate_globals_css()
    assert "@tailwind base" in text
    assert "@tailwind components" in text
    assert "@tailwind utilities" in text


def test_generate_vercel_json_framework_nextjs() -> None:
    text = packager.generate_vercel_json()
    data = json.loads(text)
    assert data["framework"] == "nextjs"
    assert "buildCommand" in data
    assert "outputDirectory" in data


def test_generate_netlify_toml_has_build_section() -> None:
    text = packager.generate_netlify_toml()
    assert "[build]" in text
    assert 'command = "pnpm build"' in text
    assert "publish" in text
    assert "NODE_VERSION" in text


def test_generate_env_example_has_no_secrets() -> None:
    text = packager.generate_env_example()
    assert "DATABASE_URL" not in text
    assert "NEVER commit" in text


def test_generate_env_example_backend_includes_database() -> None:
    text = packager.generate_env_example(has_backend=True)
    assert "DATABASE_URL" in text


def test_generate_readme_has_vercel_button() -> None:
    text = packager.generate_readme(site_name="Awesome Site", target="vercel")
    assert "# Awesome Site" in text
    assert "Deploy with Vercel" in text


def test_generate_readme_netlify_target() -> None:
    text = packager.generate_readme(site_name="Awesome Site", target="netlify")
    assert "Deploy to Netlify" in text
    assert "vercel.com/button" not in text


def test_generate_readme_both_targets() -> None:
    text = packager.generate_readme(site_name="Awesome Site", target="both")
    assert "Deploy with Vercel" in text
    assert "Deploy to Netlify" in text


def test_generate_deploy_script_vercel() -> None:
    text = packager.generate_deploy_script(target="vercel")
    assert "npx vercel --prod" in text
    assert "#!/usr/bin/env bash" in text


def test_generate_deploy_script_netlify() -> None:
    text = packager.generate_deploy_script(target="netlify")
    assert "npx netlify deploy --prod --dir=dist" in text


def test_package_site_writes_all_files(tmp_path: Path) -> None:
    output_dir = tmp_path / "site"
    written = packager.package_site(str(output_dir), site_name="Test Site")
    assert "package.json" in written
    assert "next.config.ts" in written
    assert "tsconfig.json" in written
    assert "tailwind.config.ts" in written
    assert "postcss.config.mjs" in written
    assert "src/app/globals.css" in written
    assert "vercel.json" in written
    assert "netlify.toml" in written
    assert ".env.example" in written
    assert "README.md" in written
    assert "deploy.sh" in written

    package_data = json.loads((output_dir / "package.json").read_text(encoding="utf-8"))
    assert package_data["name"] == "test-site"


def test_package_site_skips_existing_when_skip_existing_true(tmp_path: Path) -> None:
    output_dir = tmp_path / "site"
    output_dir.mkdir()
    existing = output_dir / "tailwind.config.ts"
    existing.write_text("// custom", encoding="utf-8")
    written = packager.package_site(str(output_dir), site_name="Test Site", skip_existing=True)
    assert "tailwind.config.ts" not in written
    assert existing.read_text(encoding="utf-8") == "// custom"


def test_package_site_overwrites_when_skip_existing_false(tmp_path: Path) -> None:
    output_dir = tmp_path / "site"
    output_dir.mkdir()
    existing = output_dir / "tailwind.config.ts"
    existing.write_text("// custom", encoding="utf-8")
    written = packager.package_site(str(output_dir), site_name="Test Site", skip_existing=False)
    assert "tailwind.config.ts" in written
    assert "// custom" not in existing.read_text(encoding="utf-8")


def test_package_site_root_dir_containment(tmp_path: Path) -> None:
    output_dir = tmp_path / ".." / "outside"
    with pytest.raises(ValueError):
        packager.package_site(str(output_dir), site_name="Test Site", root_dir=str(tmp_path))


def test_site_slug_normalization() -> None:
    assert packager._site_slug("My Cool Site!!!") == "my-cool-site"
    assert packager._site_slug("  ") == "figma-site"
    assert packager._site_slug(None) == "figma-site"
