"""Tests for runtime/deploy engine and config."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from runtime.deploy import DeployConfig, DeployEngine


pytestmark = [pytest.mark.core, pytest.mark.runtime]


def test_config_from_dict_defaults():
    cfg = DeployConfig.from_dict({})
    assert cfg.provider == "vercel"
    assert cfg.dry_run is True
    assert cfg.build_command == "pnpm build"


def test_config_validation_bad_provider(tmp_path):
    cfg = DeployConfig(target_dir=tmp_path, provider="aws")
    errors = cfg.validate()
    assert any("provider" in e for e in errors)


def test_engine_dry_run_does_not_execute_command(tmp_path):
    cfg = DeployConfig(target_dir=tmp_path, provider="vercel", dry_run=True)
    result = DeployEngine(tmp_path, cfg).run()
    assert result.success
    assert result.dry_run is True
    assert result.returncode is None
    assert any("Dry-run" in n for n in result.notes)


def test_engine_builds_vercel_command(tmp_path):
    cfg = DeployConfig(target_dir=tmp_path, provider="vercel", dry_run=True)
    result = DeployEngine(tmp_path, cfg).run()
    assert "npx vercel --prod --yes" in result.command


def test_engine_builds_netlify_command(tmp_path):
    cfg = DeployConfig(target_dir=tmp_path, provider="netlify", dry_run=True, dist_dir="out")
    result = DeployEngine(tmp_path, cfg).run()
    assert "npx netlify deploy" in result.command
    assert "out" in result.command


def test_engine_builds_generic_command(tmp_path):
    cfg = DeployConfig(target_dir=tmp_path, provider="generic", dry_run=True, build_command="npm run build")
    result = DeployEngine(tmp_path, cfg).run()
    assert "npm run build" in result.command


def test_config_validation_blocks_shell_metacharacters(tmp_path):
    cfg = DeployConfig(target_dir=tmp_path, provider="netlify", build_command="pnpm build; rm -rf /")
    errors = cfg.validate()
    assert any("shell metacharacters" in e for e in errors)


def test_engine_passes_command_as_argv_not_shell_string(tmp_path):
    cfg = DeployConfig(target_dir=tmp_path, provider="netlify", dry_run=True, dist_dir="out dir")
    result = DeployEngine(tmp_path, cfg).run()
    assert result.command_argv
    assert any("--dir=out dir" in arg for arg in result.command_argv)


def test_extract_url_finds_vercel_and_netlify():
    engine = DeployEngine(Path("."), DeployConfig())
    assert engine._extract_url("Preview: https://demo.vercel.app") == "https://demo.vercel.app"
    assert engine._extract_url("URL: https://demo--xxx.netlify.app") == "https://demo--xxx.netlify.app"
    assert engine._extract_url("Live at https://example.com") == "https://example.com"
    assert engine._extract_url("no url here") is None
