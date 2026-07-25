"""Adversarial tests for the sandbox execution engine."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from runtime.sandbox.config import SandboxBackend, SandboxConfig
from runtime.sandbox.engine import SandboxEngine, SandboxResult


class FakeCompletedProcess:
    def __init__(self, returncode: int, stdout: str = "", stderr: str = ""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


@pytest.fixture
def docker_config(tmp_path):
    return SandboxConfig(
        workspace_root=tmp_path,
        backend=SandboxBackend.DOCKER,
        image="python:3.11-slim",
        timeout_ms=10_000,
    )


@pytest.fixture
def wsl_config(tmp_path):
    return SandboxConfig(
        workspace_root=tmp_path,
        backend=SandboxBackend.WSL2,
        wsl_distro="Ubuntu",
        timeout_ms=10_000,
    )


@pytest.fixture
def engine_docker(docker_config):
    return SandboxEngine(docker_config)


class TestSandboxBackendSelection:
    def test_explicit_docker_backend(self, docker_config):
        engine = SandboxEngine(docker_config)
        assert engine._backend() == SandboxBackend.DOCKER

    def test_auto_selects_docker_when_available(self, tmp_path, monkeypatch):
        monkeypatch.setattr(SandboxConfig, "_docker_available", staticmethod(lambda: True))
        config = SandboxConfig(workspace_root=tmp_path, backend=SandboxBackend.AUTO)
        engine = SandboxEngine(config)
        assert engine._backend() == SandboxBackend.DOCKER

    def test_auto_falls_back_to_wsl_on_windows(self, tmp_path, monkeypatch):
        import platform

        monkeypatch.setattr(SandboxConfig, "_docker_available", staticmethod(lambda: False))
        monkeypatch.setattr(platform, "system", lambda: "Windows")
        monkeypatch.setattr(SandboxEngine, "_which", lambda self, name: "/usr/bin/wsl" if name == "wsl" else None)
        config = SandboxConfig(workspace_root=tmp_path, backend=SandboxBackend.AUTO)
        engine = SandboxEngine(config)
        assert engine._backend() == SandboxBackend.WSL2


class TestSandboxExecuteDocker:
    def test_execute_docker_command(self, engine_docker, monkeypatch):
        def fake_run(cmd, **kwargs):
            return FakeCompletedProcess(0, "hello\n", "")

        monkeypatch.setattr(subprocess, "run", fake_run)
        result = engine_docker.execute(["echo", "hello"])

        assert isinstance(result, SandboxResult)
        assert result.ok is True
        assert result.returncode == 0
        assert result.stdout == "hello\n"
        assert result.backend == "docker"
        assert result.command[0] == "docker"

    def test_execute_docker_timeout(self, engine_docker, monkeypatch):
        def fake_run(cmd, **kwargs):
            raise subprocess.TimeoutExpired(cmd, timeout=1, output="partial", stderr="")

        monkeypatch.setattr(subprocess, "run", fake_run)
        result = engine_docker.execute(["sleep", "10"])

        assert result.ok is False
        assert result.returncode is None
        assert "timed out" in result.errors[0].lower()

    def test_execute_docker_failure(self, engine_docker, monkeypatch):
        def fake_run(cmd, **kwargs):
            return FakeCompletedProcess(1, "", "error message")

        monkeypatch.setattr(subprocess, "run", fake_run)
        result = engine_docker.execute(["false"])

        assert result.ok is False
        assert result.returncode == 1
        assert result.stderr == "error message"

    def test_docker_mount_args_include_workspace(self, engine_docker):
        args = engine_docker._docker_mount_args()
        assert "-v" in args
        assert any(str(engine_docker.config.workspace_root) in a for a in args)


class TestSandboxExecuteWSL:
    def test_execute_wsl_unavailable(self, wsl_config, monkeypatch):
        engine = SandboxEngine(wsl_config)
        monkeypatch.setattr(engine, "_wsl_available", lambda: False)
        result = engine.execute(["echo", "hello"])

        assert result.ok is False
        assert "WSL2 is not available" in result.errors[0]

    def test_execute_wsl_command(self, wsl_config, monkeypatch):
        engine = SandboxEngine(wsl_config)
        captured_cmd: list[str] = []
        monkeypatch.setattr(engine, "_wsl_available", lambda: True)
        monkeypatch.setattr(SandboxEngine, "_host_path_to_wsl", staticmethod(lambda p: f"/mnt/c{p}"))

        def fake_run(cmd, **kwargs):
            captured_cmd[:] = cmd
            return FakeCompletedProcess(0, "wsl output\n", "")

        monkeypatch.setattr(subprocess, "run", fake_run)
        result = engine.execute(["echo", "hello"])

        assert result.ok is True
        assert result.returncode == 0
        assert result.stdout == "wsl output\n"
        assert result.backend == "wsl2"
        assert captured_cmd[0] == "wsl"


class TestSandboxRewriteLocalhost:
    def test_rewrites_localhost(self):
        assert SandboxEngine._rewrite_localhost_for_docker("http://localhost:3000") == "http://host.docker.internal:3000"

    def test_rewrites_127_0_0_1(self):
        assert SandboxEngine._rewrite_localhost_for_docker("http://127.0.0.1:3000") == "http://host.docker.internal:3000"


class TestSandboxHostPathToWSL:
    def test_windows_path(self):
        assert SandboxEngine._host_path_to_wsl(Path("C:/Users/test")) == "/mnt/c/Users/test"

    def test_posix_path_unchanged(self, monkeypatch):
        monkeypatch.setattr(Path, "resolve", lambda self: self)
        assert SandboxEngine._host_path_to_wsl(Path("/home/user")) == "/home/user"


class TestSandboxArtifacts:
    def test_collect_artifacts(self, docker_config, tmp_path, monkeypatch):
        (tmp_path / "out.txt").write_text("result", encoding="utf-8")
        config = docker_config
        config.artifact_paths = ["out.txt"]
        engine = SandboxEngine(config)

        result = SandboxResult()
        engine._collect_artifacts(result)

        assert "out.txt" in result.artifacts
        assert result.artifacts["out.txt"] == str((tmp_path / "out.txt").resolve())

    def test_collect_artifacts_no_patterns(self, docker_config, tmp_path):
        config = docker_config
        config.artifact_paths = []
        engine = SandboxEngine(config)
        result = SandboxResult()
        engine._collect_artifacts(result)
        assert result.artifacts == {}


class TestSandboxCleanup:
    def test_cleanup_stops_servers(self, docker_config, monkeypatch):
        engine = SandboxEngine(docker_config)
        stopped = []

        class FakeHandle:
            url = "http://127.0.0.1:8000"
            container_id = "abc123"

            def stop(self):
                stopped.append(self.url)
                return {"url": self.url, "stopped": True}

        handle = FakeHandle()
        handle.stop = lambda: stopped.append(handle.url) or {"url": handle.url, "stopped": True}
        engine._active_servers.append(handle)
        report = engine.cleanup()

        assert stopped == ["http://127.0.0.1:8000"]
        assert len(engine._active_servers) == 0
        assert report["stopped"]


class TestSandboxFindFreePort:
    def test_returns_positive_port(self):
        port = SandboxEngine._find_free_port()
        assert isinstance(port, int)
        assert port > 0
        assert port < 65536
