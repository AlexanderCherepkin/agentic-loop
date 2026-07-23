"""Tests for runtime/deploy image providers (Render, Railway, Fly.io)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from runtime.deploy import DeployConfig, DeployEngine
from runtime.deploy.providers import DeployProviderFactory, RailwayDeployer


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


def test_railway_uses_graphql_variables(monkeypatch):
    """RailwayDeployer must send values via GraphQL variables, not string interpolation."""
    from unittest.mock import MagicMock, patch

    monkeypatch.setenv("DEPLOY_RAILWAY_API_KEY", "token-123")

    def fake_post(url, *, headers, json):
        resp = MagicMock()
        resp.status_code = 200
        if "projectCreate" in json.get("query", ""):
            resp.json.return_value = {"data": {"projectCreate": {"id": "proj-1", "name": "demo"}}}
        elif "serviceCreate" in json.get("query", ""):
            assert "variables" in json
            assert json["variables"]["name"] == "demo-svc"
            assert json["variables"]["projectId"] == "proj-1"
            resp.json.return_value = {"data": {"serviceCreate": {"id": "svc-1", "__typename": "Service"}}}
        elif "serviceInstanceDeploy" in json.get("query", ""):
            assert "variables" in json
            assert json["variables"]["serviceId"] == "svc-1"
            assert json["variables"]["image"] == "example/app:latest"
            resp.json.return_value = {"data": {"serviceInstanceDeploy": {"id": "dep-1", "status": "SUCCESS"}}}
        else:
            resp.json.return_value = {}
        resp.raise_for_status = lambda: None
        return resp

    with patch("httpx.Client") as mock_client_class:
        instance = MagicMock()
        instance.post.side_effect = fake_post
        instance.__enter__ = MagicMock(return_value=instance)
        instance.__exit__ = MagicMock(return_value=False)
        mock_client_class.return_value = instance

        deployer = RailwayDeployer(api_key="token-123")
        result = deployer.deploy(
            image_tag="example/app:latest",
            project={"project_id": "demo", "language": "typescript"},
            config={"service_name": "demo-svc"},
        )

    assert result.error is None
    assert result.service_id == "svc-1"


def test_railway_rejects_injection_in_variables(monkeypatch):
    """Values supplied via GraphQL variables cannot break query structure."""
    from unittest.mock import MagicMock, patch

    monkeypatch.setenv("DEPLOY_RAILWAY_API_KEY", "token-123")

    captured: list[dict] = []

    def fake_post(url, *, headers, json):
        captured.append(json)
        resp = MagicMock()
        resp.status_code = 200
        if "projectCreate" in json.get("query", ""):
            resp.json.return_value = {"data": {"projectCreate": {"id": "proj-1", "name": "demo"}}}
        elif "serviceCreate" in json.get("query", ""):
            resp.json.return_value = {"data": {"serviceCreate": {"id": "svc-1", "__typename": "Service"}}}
        elif "serviceInstanceDeploy" in json.get("query", ""):
            resp.json.return_value = {"data": {"serviceInstanceDeploy": {"id": "dep-1", "status": "SUCCESS"}}}
        else:
            resp.json.return_value = {}
        resp.raise_for_status = lambda: None
        return resp

    with patch("httpx.Client") as mock_client_class:
        instance = MagicMock()
        instance.post.side_effect = fake_post
        instance.__enter__ = MagicMock(return_value=instance)
        instance.__exit__ = MagicMock(return_value=False)
        mock_client_class.return_value = instance

        malicious_service_name = 'bad" } bad'
        malicious_image = 'app:latest" }) { __typename '
        deployer = RailwayDeployer(api_key="token-123")
        result = deployer.deploy(
            image_tag=malicious_image,
            project={"project_id": "demo", "language": "typescript"},
            config={"service_name": malicious_service_name},
        )

    assert result.error is None
    # Query string must remain structurally valid; payloads sent via variables.
    for payload in captured:
        if "variables" in payload:
            # The query template itself must not contain the injected value.
            assert malicious_service_name not in payload["query"]
            assert malicious_image not in payload["query"]
            # Service create carries the malicious name as a variable; deploy carries the image.
            if "serviceCreate" in payload["query"]:
                assert payload["variables"].get("name") == malicious_service_name
            if "serviceInstanceDeploy" in payload["query"]:
                assert payload["variables"].get("image") == malicious_image
