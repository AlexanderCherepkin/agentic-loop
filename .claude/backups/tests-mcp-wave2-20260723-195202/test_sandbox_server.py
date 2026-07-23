"""pytest tests for the Sandbox MCP server.

Tests avoid real Docker/WSL calls by monkeypatching the runtime/sandbox engine.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import pytest

from mcp_servers.sandbox_server import SandboxMCPServer


@pytest.fixture
def server(tmp_path: Path) -> SandboxMCPServer:
    return SandboxMCPServer(str(tmp_path))


def test_server_initializes(server: SandboxMCPServer) -> None:
    assert server.name == "sandbox"
    assert server._initialized is True
    tools = server.get_tools_list()
    assert len(tools) == 5
    names = {t["name"] for t in tools}
    assert names == {
        "sandbox_execute",
        "sandbox_run_dev_server",
        "sandbox_screenshot",
        "sandbox_cleanup",
        "sandbox_status",
    }


def test_tool_schemas(server: SandboxMCPServer) -> None:
    for tool in server.get_tools_list():
        assert "name" in tool
        assert "description" in tool
        assert "inputSchema" in tool
        schema = tool["inputSchema"]
        assert schema.get("type") == "object"
        assert "properties" in schema


def test_status_reports_degraded_when_no_docker_or_wsl(server: SandboxMCPServer, monkeypatch: Any) -> None:
    monkeypatch.setattr("shutil.which", lambda name: None)
    result = server.sandbox_status()
    assert result["is_error"] is False
    assert result["available"] is False
    assert result["status"] == "degraded"
    assert result["docker_available"] is False
    assert result["wsl_available"] is False


def test_status_reports_success_when_docker_available(server: SandboxMCPServer, monkeypatch: Any) -> None:
    monkeypatch.setattr("shutil.which", lambda name: "/usr/bin/docker" if name == "docker" else None)

    class CompletedProcess:
        returncode = 0
        stdout = ""
        stderr = ""

    def fake_run(*args: Any, **kwargs: Any) -> Any:
        return CompletedProcess()

    monkeypatch.setattr("subprocess.run", fake_run)
    result = server.sandbox_status()
    assert result["is_error"] is False
    assert result["available"] is True
    assert result["status"] == "success"
    assert result["docker_available"] is True


def test_execute_uses_engine(server: SandboxMCPServer, monkeypatch: Any) -> None:
    calls: list[dict[str, Any]] = []

    class FakeResult:
        ok = True
        backend = "docker"
        command = ["echo", "hi"]
        returncode = 0
        stdout = "hi"
        stderr = ""
        artifacts: dict[str, str] = {}
        server_handle = None
        errors: list[str] = []
        notes: list[str] = []
        elapsed_ms = 7

        def to_dict(self) -> dict[str, Any]:
            return {
                "ok": self.ok,
                "backend": self.backend,
                "command": self.command,
                "returncode": self.returncode,
                "stdout": self.stdout,
                "stderr": self.stderr,
                "artifacts": self.artifacts,
                "server_url": None,
                "errors": self.errors,
                "notes": self.notes,
                "elapsed_ms": self.elapsed_ms,
            }

    class FakeEngine:
        def execute(self, command: Any, cwd: Any = None, timeout_ms: int = 0, env: Any = None) -> FakeResult:
            calls.append({"command": command, "cwd": cwd, "timeout_ms": timeout_ms, "env": env})
            return FakeResult()

    def fake_make_engine(overrides: dict[str, Any]) -> FakeEngine:
        calls.append({"make_engine_overrides": overrides})
        return FakeEngine()

    monkeypatch.setattr(server, "_make_engine", fake_make_engine)

    result = server.sandbox_execute("echo", args=["hi"], cwd="src", timeout_ms=5000, env={"X": "1"})
    assert result["status"] == "success"
    assert result["is_error"] is False
    assert result["stdout"] == "hi"
    assert calls[0]["make_engine_overrides"]["backend"] == "auto"
    assert calls[1]["command"] == ["echo", "hi"]
    assert calls[1]["cwd"] == "src"
    assert calls[1]["timeout_ms"] == 5000


def test_run_dev_server_uses_engine(server: SandboxMCPServer, monkeypatch: Any) -> None:
    calls: list[dict[str, Any]] = []

    class FakeHandle:
        url = "http://127.0.0.1:4321"
        host_port = 4321
        sandbox_path = "/workspace"
        container_id = "abc"
        wsl_pid = None

    class FakeResult:
        ok = True
        backend = "docker"
        command = ["npm", "run", "dev"]
        returncode = 0
        stdout = "dev server listening on http://127.0.0.1:4321"
        stderr = ""
        artifacts: dict[str, str] = {}
        server_handle = FakeHandle()
        errors: list[str] = []
        notes: list[str] = []
        elapsed_ms = 100

        def to_dict(self) -> dict[str, Any]:
            return {
                "ok": self.ok,
                "backend": self.backend,
                "command": self.command,
                "returncode": self.returncode,
                "stdout": self.stdout,
                "stderr": self.stderr,
                "artifacts": self.artifacts,
                "server_url": self.server_handle.url,
                "errors": self.errors,
                "notes": self.notes,
                "elapsed_ms": self.elapsed_ms,
            }

    class FakeEngine:
        def run_dev_server(self, command: Any, **kwargs: Any) -> FakeResult:
            calls.append({"command": command, **kwargs})
            return FakeResult()

    monkeypatch.setattr(server, "_make_engine", lambda _overrides: FakeEngine())

    result = server.sandbox_run_dev_server("npm", port=3000, args=["run", "dev"], ready_pattern="Ready")
    assert result["status"] == "success"
    assert result["server_handle"]["url"] == "http://127.0.0.1:4321"
    assert result["server_handle"]["container_id"] == "abc"
    assert calls[0]["command"] == ["npm", "run", "dev"]
    assert calls[0]["port"] == 3000


def test_screenshot_uses_engine(server: SandboxMCPServer, monkeypatch: Any) -> None:
    calls: list[dict[str, Any]] = []

    class FakeResult:
        ok = True
        backend = "docker"
        returncode = 0
        stdout = ""
        stderr = ""
        artifacts = {"screenshot": "/tmp/out.png"}
        server_handle = None
        errors: list[str] = []
        notes: list[str] = []
        elapsed_ms = 200

        def to_dict(self) -> dict[str, Any]:
            return {
                "ok": self.ok,
                "backend": self.backend,
                "command": [],
                "returncode": self.returncode,
                "stdout": self.stdout,
                "stderr": self.stderr,
                "artifacts": self.artifacts,
                "server_url": None,
                "errors": self.errors,
                "notes": self.notes,
                "elapsed_ms": self.elapsed_ms,
            }

    class FakeEngine:
        def screenshot(self, url: str, output_path: str, viewport: dict[str, int] | None = None) -> FakeResult:
            calls.append({"url": url, "output_path": output_path, "viewport": viewport})
            return FakeResult()

    monkeypatch.setattr(server, "_make_engine", lambda _overrides: FakeEngine())

    result = server.sandbox_screenshot("http://localhost:3000", "/tmp/out.png", viewport_width=1920, viewport_height=1080)
    assert result["status"] == "success"
    assert result["artifacts"]["screenshot"] == "/tmp/out.png"
    assert calls[0]["viewport"] == {"width": 1920, "height": 1080}


def test_cleanup_uses_engine(server: SandboxMCPServer, monkeypatch: Any) -> None:
    calls: list[int] = []

    class FakeEngine:
        def cleanup(self) -> dict[str, Any]:
            calls.append(1)
            return {"stopped": []}

    monkeypatch.setattr(server, "_load_engine", lambda: FakeEngine())
    result = server.sandbox_cleanup()
    assert result["status"] == "success"
    assert result["is_error"] is False
    assert calls == [1]


def test_ping(server: SandboxMCPServer) -> None:
    assert asyncio.run(server.ping()) is True
