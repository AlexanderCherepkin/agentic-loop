"""Tests for runtime/git_publisher engine and config."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from runtime.git_publisher import GitPublisherConfig, GitPublisherEngine


pytestmark = [pytest.mark.core, pytest.mark.runtime]


def test_config_defaults():
    cfg = GitPublisherConfig.from_dict({})
    assert cfg.provider == "github"
    assert cfg.private is True


def test_config_from_dict():
    cfg = GitPublisherConfig.from_dict(
        {"provider": "gitlab", "private": False, "project_id": "demo"}
    )
    assert cfg.provider == "gitlab"
    assert cfg.private is False


def test_publish_without_token_fails():
    engine = GitPublisherEngine(GitPublisherConfig(github_token=None, gitlab_token=None))
    result = engine.publish("demo", {"README.md": "# Demo"})
    assert not result.success
    assert "GITHUB_TOKEN" in result.error


def test_publish_gitlab_without_token_fails():
    engine = GitPublisherEngine(GitPublisherConfig(provider="gitlab"))
    result = engine.publish("demo", {"README.md": "# Demo"})
    assert not result.success
    assert "GITLAB_TOKEN" in result.error
