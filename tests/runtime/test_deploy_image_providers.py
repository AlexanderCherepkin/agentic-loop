"""Tests for runtime/deploy image providers (Render, Railway, Fly.io)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from runtime.deploy import DeployConfig, DeployEngine
from runtime.deploy.providers import DeployProviderFactory


pytestmark = [pytest.mark.core, pytest.mark.runtime]


def test_factory_lists_providers():
    providers = DeployProviderFactory.list()
    assert set(providers.keys()) == {"render", "railway", "flyio"}


def test_factory_get_unknown_raises():
    with pytest.raises(ValueError):
        DeployProviderFactory.get("aws")


def test_deploy_config_accepts_image_providers(tmp_path):
    cfg = DeployConfig(
        target_dir=tmp_path,
        provider="render",
        image_tag="example/app:latest",
        project_id="demo",
        owner_id="owner-123",
    )
    errors = cfg.validate()
    assert not errors


def test_deploy_config_requires_image_tag_for_render(tmp_path):
    cfg = DeployConfig(target_dir=tmp_path, provider="render", project_id="demo")
    errors = cfg.validate()
    assert any("image_tag" in e for e in errors)


def test_deploy_config_requires_project_id_for_flyio(tmp_path):
    cfg = DeployConfig(target_dir=tmp_path, provider="flyio", image_tag="example/app:latest")
    errors = cfg.validate()
    assert any("project_id" in e for e in errors)


def test_render_dry_run_without_api_key(tmp_path):
    cfg = DeployConfig(
        target_dir=tmp_path,
        provider="render",
        image_tag="example/app:latest",
        project_id="demo",
        owner_id="owner-123",
        dry_run=True,
    )
    result = DeployEngine(tmp_path, cfg).run()
    assert result.success
    assert result.dry_run is True
    assert any("Dry-run" in n for n in result.notes)


def test_render_live_without_api_key_fails(tmp_path):
    cfg = DeployConfig(
        target_dir=tmp_path,
        provider="render",
        image_tag="example/app:latest",
        project_id="demo",
        owner_id="owner-123",
        dry_run=False,
    )
    result = DeployEngine(tmp_path, cfg).run()
    assert not result.success
    assert any("API key" in e["reason"] for e in result.errors)


def test_flyio_live_without_org_slug_fails(tmp_path, monkeypatch):
    monkeypatch.setenv("DEPLOY_FLY_API_TOKEN", "token-123")
    cfg = DeployConfig(
        target_dir=tmp_path,
        provider="flyio",
        image_tag="example/app:latest",
        project_id="demo",
        dry_run=False,
    )
    result = DeployEngine(tmp_path, cfg).run()
    assert not result.success
    assert any("ORG_SLUG" in e["reason"] for e in result.errors)
