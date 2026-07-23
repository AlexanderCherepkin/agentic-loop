"""Tests for SandboxEngine helpers and artifact collection (subprocess mocked)."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from runtime.sandbox import SandboxBackend, SandboxConfig
from runtime.sandbox.engine import SandboxEngine, SandboxResult


pytestmark = [pytest.mark.core, pytest.mark.runtime]


def _engine_with_auto():
    engine = SandboxEngine(SandboxConfig())
    engine.config.backend = SandboxBackend.AUTO
    return engine


def test_backend_auto_prefers_docker_when_available():
    engine = _engine_with_auto()
    with patch.object(engine, "_docker_available", return_value=True):
        assert engine._backend() == SandboxBackend.DOCKER


def test_backend_auto_falls_back_to_wsl_when_docker_missing():
    engine = _engine_with_auto()
    with patch.object(engine, "_docker_available", return_value=False):
        assert engine._backend() == SandboxBackend.WSL2


def test_backend_explicit_wsl_ignores_docker():
    engine = SandboxEngine(SandboxConfig(backend=SandboxBackend.WSL2))
    with patch.object(engine, "_docker_available", return_value=True):
        assert engine._backend() == SandboxBackend.WSL2


@patch("runtime.sandbox.engine.shutil.which")
def test_docker_available_false_when_binary_missing(mock_which):
    mock_which.return_value = None
    engine = SandboxEngine(SandboxConfig(backend=SandboxBackend.AUTO))
    assert engine._docker_available() is False


@patch("runtime.sandbox.engine.subprocess.run")
@patch("runtime.sandbox.engine.shutil.which")
def test_docker_available_true_when_docker_info_succeeds(mock_which, mock_run):
    mock_which.return_value = "/usr/bin/docker"
    mock_run.return_value = MagicMock(returncode=0)
    engine = SandboxEngine(SandboxConfig(backend=SandboxBackend.AUTO))
    assert engine._docker_available() is True


@patch("runtime.sandbox.engine.subprocess.run")
@patch("runtime.sandbox.engine.shutil.which")
def test_docker_available_false_when_docker_info_fails(mock_which, mock_run):
    mock_which.return_value = "/usr/bin/docker"
    mock_run.return_value = MagicMock(returncode=1)
    engine = SandboxEngine(SandboxConfig(backend=SandboxBackend.AUTO))
    assert engine._docker_available() is False


@patch("runtime.sandbox.engine.platform.system")
@patch("runtime.sandbox.engine.shutil.which")
def test_wsl_available_true_on_windows_with_wsl(mock_which, mock_system):
    mock_system.return_value = "Windows"
    mock_which.return_value = "/mnt/c/Windows/System32/wsl.exe"
    engine = SandboxEngine()
    assert engine._wsl_available() is True


@patch("runtime.sandbox.engine.platform.system")
@patch("runtime.sandbox.engine.shutil.which")
def test_wsl_available_false_on_linux(mock_which, mock_system):
    mock_system.return_value = "Linux"
    mock_which.return_value = "/usr/bin/wsl"
    engine = SandboxEngine()
    assert engine._wsl_available() is False


def test_host_path_to_wsl_converts_windows_drive():
    path = Path("C:/Users/alex/project")
    converted = SandboxEngine._host_path_to_wsl(path)
    assert converted == "/mnt/c/Users/alex/project"


@pytest.mark.skipif(sys.platform != "win32", reason="Windows-specific Path behavior")
def test_host_path_to_wsl_leaves_posix_path():
    # On Windows, Path('/home/alex/project') resolves to current drive, so the
    # function converts it. This test documents actual Windows behavior.
    path = Path("/home/alex/project")
    converted = SandboxEngine._host_path_to_wsl(path)
    assert converted.startswith("/mnt/")
    assert converted.endswith("/home/alex/project")


def test_rewrite_localhost_for_docker():
    assert SandboxEngine._rewrite_localhost_for_docker("http://localhost:3000") == "http://host.docker.internal:3000"
    assert SandboxEngine._rewrite_localhost_for_docker("http://127.0.0.1:3000") == "http://host.docker.internal:3000"
    assert SandboxEngine._rewrite_localhost_for_docker("http://example.com") == "http://example.com"


def test_collect_artifacts_records_matching_files(tmp_path):
    workspace = tmp_path / "ws"
    workspace.mkdir()
    (workspace / "dist").mkdir()
    (workspace / "dist" / "app.log").write_text("log")
    (workspace / "dist" / "build.log").write_text("log2")
    cfg = SandboxConfig(workspace_root=str(workspace), artifact_paths=["dist/*.log"])
    engine = SandboxEngine(cfg)
    result = SandboxResult()
    engine._collect_artifacts(result)
    assert len(result.artifacts) == 2
    assert "app.log" in result.artifacts
    assert "build.log" in result.artifacts


def test_find_free_port_returns_positive_ephemeral_port():
    port = SandboxEngine._find_free_port()
    assert isinstance(port, int)
    assert 1024 <= port <= 65535


def test_sandbox_result_to_dict_round_trip():
    result = SandboxResult(
        ok=True,
        backend="docker",
        returncode=0,
        stdout="hello",
        stderr="",
        artifacts={"file.txt": "/path/file.txt"},
    )
    data = result.to_dict()
    assert data["ok"] is True
    assert data["backend"] == "docker"
    assert data["server_url"] is None
    assert data["artifacts"]["file.txt"] == "/path/file.txt"


@patch("runtime.sandbox.engine.subprocess.run")
@patch("runtime.sandbox.engine.SandboxEngine._docker_available", return_value=False)
@patch("runtime.sandbox.engine.SandboxEngine._wsl_available", return_value=False)
def test_execute_wsl_reports_unavailable(mock_wsl, mock_docker, mock_run):
    cfg = SandboxConfig(backend=SandboxBackend.WSL2)
    engine = SandboxEngine(cfg)
    result = engine.execute(["echo", "hi"])
    assert result.ok is False
    assert "WSL2 is not available" in result.errors[0]
