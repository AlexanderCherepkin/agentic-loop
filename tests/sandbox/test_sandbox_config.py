"""Tests for SandboxConfig deterministic parsing and backend selection."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from runtime.sandbox import SandboxBackend, SandboxConfig


pytestmark = [pytest.mark.core, pytest.mark.runtime]


def test_config_defaults_resolve_workspace():
    cfg = SandboxConfig()
    assert isinstance(cfg.workspace_root, Path)
    assert cfg.workspace_root.is_absolute()
    # AUTO is resolved during post-init to a concrete backend.
    assert cfg.backend in {SandboxBackend.DOCKER, SandboxBackend.WSL2}
    assert cfg.image == "node:20-slim"
    assert cfg.timeout_ms == 120_000


def test_config_from_dict_parses_mounts():
    data = {
        "workspace_root": ".tmp/sandbox",
        "backend": "docker",
        "image": "python:3.11-slim",
        "mounts": [["./host", "/cont"], "./other:/other"],
        "artifact_paths": ["dist/*.log"],
        "keep_container": True,
    }
    cfg = SandboxConfig.from_dict(data)
    assert cfg.backend == SandboxBackend.DOCKER
    assert cfg.image == "python:3.11-slim"
    assert cfg.mounts == [("./host", "/cont"), ("./other", "/other")]
    assert cfg.artifact_paths == ["dist/*.log"]
    assert cfg.keep_container is True


def test_config_from_dict_ignores_invalid_mounts():
    data = {"mounts": ["no-colon", ["a"]]}
    cfg = SandboxConfig.from_dict(data)
    assert cfg.mounts == []


def test_config_backend_enum_values():
    assert SandboxBackend.AUTO == "auto"
    assert SandboxBackend.DOCKER == "docker"
    assert SandboxBackend.WSL2 == "wsl2"
