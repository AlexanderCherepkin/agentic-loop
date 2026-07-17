"""Docker/WSL2 sandbox execution engine.

Runs commands inside an isolated environment, captures output, copies
artifacts back to the host, supports long-running dev servers with port
forwarding, and can render screenshots via Playwright inside the container.
"""

from __future__ import annotations

import fnmatch
import os
import platform
import re
import shutil
import subprocess
import tempfile
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .config import SandboxBackend, SandboxConfig


@dataclass
class SandboxServerHandle:
    """Handle for a dev server running inside the sandbox."""

    url: str
    _engine: "SandboxEngine" = field(repr=False)
    container_id: str | None = None
    wsl_pid: int | None = None
    host_port: int = 0
    sandbox_path: str = "/workspace"

    def stop(self) -> dict[str, Any]:
        return self._engine._stop_server(self)


@dataclass
class SandboxResult:
    """Result of a sandboxed command or operation."""

    ok: bool = False
    backend: str = "unknown"
    command: list[str] = field(default_factory=list)
    returncode: int | None = None
    stdout: str = ""
    stderr: str = ""
    artifacts: dict[str, str] = field(default_factory=dict)
    server_handle: SandboxServerHandle | None = None
    errors: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    elapsed_ms: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "backend": self.backend,
            "command": self.command,
            "returncode": self.returncode,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "artifacts": self.artifacts,
            "server_url": self.server_handle.url if self.server_handle else None,
            "errors": self.errors,
            "notes": self.notes,
            "elapsed_ms": self.elapsed_ms,
        }


class SandboxEngine:
    """Execute commands in Docker or WSL2 and move artifacts back."""

    def __init__(self, config: SandboxConfig | None = None):
        self.config = config or SandboxConfig()
        self._active_servers: list[SandboxServerHandle] = []

    # ------------------------------------------------------------------
    # Backend probing
    # ------------------------------------------------------------------
    def _which(self, name: str) -> str | None:
        return shutil.which(name)

    def _backend(self) -> SandboxBackend:
        if self.config.backend == SandboxBackend.AUTO:
            return SandboxBackend.DOCKER if self._docker_available() else SandboxBackend.WSL2
        return self.config.backend

    def _docker_available(self) -> bool:
        docker = self._which("docker")
        if not docker:
            return False
        try:
            result = subprocess.run(
                [docker, "info"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            return result.returncode == 0
        except Exception:
            return False

    def _wsl_available(self) -> bool:
        if platform.system() != "Windows":
            return False
        return self._which("wsl") is not None

    def _base_command(self) -> list[str]:
        backend = self._backend()
        if backend == SandboxBackend.DOCKER:
            return ["docker", "run", "--rm", "-i"]
        if backend == SandboxBackend.WSL2:
            return ["wsl", "-d", self.config.wsl_distro, "--exec"]
        raise RuntimeError(f"Unsupported sandbox backend: {backend}")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def execute(
        self,
        command: list[str] | str,
        cwd: str | None = None,
        timeout_ms: int | None = None,
        env: dict[str, str] | None = None,
    ) -> SandboxResult:
        """Run a command in the sandbox and copy requested artifacts back."""
        timeout = timeout_ms if timeout_ms is not None else self.config.timeout_ms
        backend = self._backend()
        start = time.time()
        result = SandboxResult(backend=backend.value)

        if backend == SandboxBackend.DOCKER:
            result = self._execute_docker(command, cwd, timeout, env, result)
        elif backend == SandboxBackend.WSL2:
            result = self._execute_wsl(command, cwd, timeout, env, result)
        else:
            result.errors.append(f"Unsupported backend: {backend}")

        result.elapsed_ms = int((time.time() - start) * 1000)
        if result.returncode == 0 and not result.errors:
            result.ok = True
        return result

    def run_dev_server(
        self,
        command: list[str] | str,
        port: int,
        cwd: str | None = None,
        timeout_ms: int = 30_000,
        env: dict[str, str] | None = None,
        ready_pattern: str = "Ready",
    ) -> SandboxResult:
        """Start a long-running dev server inside the sandbox.

        For Docker: publishes container port to a random host port.
        For WSL2: starts the server in WSL and returns the WSL IP/port URL.
        """
        backend = self._backend()
        start = time.time()
        result = SandboxResult(backend=backend.value)

        if backend == SandboxBackend.DOCKER:
            handle, result = self._run_dev_server_docker(
                command, port, cwd, timeout_ms, env, ready_pattern, result
            )
        elif backend == SandboxBackend.WSL2:
            handle, result = self._run_dev_server_wsl(
                command, port, cwd, timeout_ms, env, ready_pattern, result
            )
        else:
            result.errors.append(f"Unsupported backend: {backend}")
            handle = None

        result.elapsed_ms = int((time.time() - start) * 1000)
        result.server_handle = handle
        if handle and not result.errors:
            result.ok = True
            self._active_servers.append(handle)
        return result

    def screenshot(self, url: str, output_path: str | Path, viewport: dict[str, int] | None = None) -> SandboxResult:
        """Capture a screenshot of `url` using Playwright inside the sandbox."""
        backend = self._backend()
        start = time.time()
        result = SandboxResult(backend=backend.value)

        width = viewport.get("width", 1280) if viewport else 1280
        height = viewport.get("height", 800) if viewport else 800
        out = Path(output_path).resolve()
        out.parent.mkdir(parents=True, exist_ok=True)

        script = (
            "from playwright.sync_api import sync_playwright; "
            f"p = sync_playwright().start(); "
            f"b = p.chromium.launch(); "
            f"page = b.new_page(viewport={{'width': {width}, 'height': {height}}}); "
            f"page.goto({url!r}, wait_until='networkidle'); "
            f"page.screenshot(path={str(out)!r}, full_page=True); "
            f"b.close(); p.stop()"
        )

        if backend == SandboxBackend.DOCKER:
            # If the URL points to localhost/127.0.0.1, rewrite to host.docker.internal
            internal_url = self._rewrite_localhost_for_docker(url)
            script = (
                "from playwright.sync_api import sync_playwright; "
                f"p = sync_playwright().start(); "
                f"b = p.chromium.launch(); "
                f"page = b.new_page(viewport={{'width': {width}, 'height': {height}}}); "
                f"page.goto({internal_url!r}, wait_until='networkidle'); "
                f"page.screenshot(path='/artifacts/screenshot.png', full_page=True); "
                f"b.close(); p.stop()"
            )
            cmd = [
                "python3",
                "-c",
                script,
            ]
            result = self._execute_docker(
                cmd,
                cwd="/workspace",
                timeout_ms=60_000,
                env=None,
                result=result,
                extra_args=["--add-host=host.docker.internal:host-gateway", "-v", f"{out.parent}:/artifacts"],
            )
            if result.returncode == 0:
                result.artifacts["screenshot"] = str(out)
        elif backend == SandboxBackend.WSL2:
            # For WSL, the URL should already be reachable via WSL IP if the server runs there.
            cmd = ["python3", "-c", script]
            result = self._execute_wsl(cmd, cwd=None, timeout_ms=60_000, env=None, result=result)
            if result.returncode == 0:
                result.artifacts["screenshot"] = str(out)
        else:
            result.errors.append(f"Unsupported backend: {backend}")

        result.elapsed_ms = int((time.time() - start) * 1000)
        result.ok = result.returncode == 0 and not result.errors
        return result

    def cleanup(self) -> dict[str, Any]:
        """Stop all active dev servers and remove transient containers."""
        stopped: list[dict[str, Any]] = []
        for handle in list(self._active_servers):
            stopped.append(handle.stop())
        self._active_servers.clear()
        return {"stopped": stopped}

    # ------------------------------------------------------------------
    # Docker implementation
    # ------------------------------------------------------------------
    def _docker_mount_args(self) -> list[str]:
        """Build -v flags for Docker from config mounts plus workspace root."""
        args: list[str] = []
        # Always mount workspace root into /workspace.
        args.extend(["-v", f"{self.config.workspace_root}:/workspace"])
        # Additional user mounts.
        for host, cont in self.config.mounts:
            host_path = Path(host).expanduser().resolve()
            args.extend(["-v", f"{host_path}:{cont}"])
        return args

    def _execute_docker(
        self,
        command: list[str] | str,
        cwd: str | None,
        timeout_ms: int,
        env: dict[str, str] | None,
        result: SandboxResult,
        extra_args: list[str] | None = None,
    ) -> SandboxResult:
        work_dir = cwd if cwd else "/workspace"
        cmd = self._base_command() + (extra_args or []) + self._docker_mount_args()
        if self.config.network:
            cmd.extend(["--network", self.config.network])
        if self.config.user:
            cmd.extend(["--user", self.config.user])
        for key, value in {**(env or {}), **self.config.env}.items():
            cmd.extend(["-e", f"{key}={value}"])
        cmd.extend(["-w", str(work_dir), self.config.image])
        if isinstance(command, str):
            cmd.extend(["sh", "-c", command])
        else:
            cmd.extend(command)

        result.command = cmd
        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout_ms / 1000,
            )
            result.returncode = proc.returncode
            result.stdout = proc.stdout
            result.stderr = proc.stderr
        except subprocess.TimeoutExpired as exc:
            result.returncode = None
            result.stdout = exc.stdout or ""
            result.stderr = exc.stderr or ""
            result.errors.append(f"Docker sandbox timed out after {timeout_ms}ms")
        except Exception as exc:
            result.errors.append(f"Docker sandbox failed: {exc}")

        self._collect_artifacts(result)
        return result

    def _run_dev_server_docker(
        self,
        command: list[str] | str,
        port: int,
        cwd: str | None,
        timeout_ms: int,
        env: dict[str, str] | None,
        ready_pattern: str,
        result: SandboxResult,
    ) -> tuple[SandboxServerHandle | None, SandboxResult]:
        work_dir = cwd if cwd else "/workspace"
        container_name = f"agentic-loop-sandbox-{uuid.uuid4().hex[:8]}"
        host_port = self._find_free_port()

        cmd = ["docker", "run", "--rm", "-d", "-i"]
        cmd.extend(self._docker_mount_args())
        if self.config.network:
            cmd.extend(["--network", self.config.network])
        for key, value in {**(env or {}), **self.config.env}.items():
            cmd.extend(["-e", f"{key}={value}"])
        cmd.extend(["-p", f"{host_port}:{port}", "-w", str(work_dir), "--name", container_name, self.config.image])
        if isinstance(command, str):
            cmd.extend(["sh", "-c", command])
        else:
            cmd.extend(command)

        result.command = cmd
        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=10,
            )
            if proc.returncode != 0:
                result.errors.append(f"Failed to start dev server container: {proc.stderr}")
                return None, result
            container_id = proc.stdout.strip()
            handle = SandboxServerHandle(
                url=f"http://127.0.0.1:{host_port}",
                container_id=container_id,
                host_port=host_port,
                sandbox_path=work_dir,
                _engine=self,
            )
            # Wait for the ready pattern in logs.
            ready = self._wait_for_docker_log(container_id, ready_pattern, timeout_ms)
            if not ready:
                result.errors.append("Dev server did not become ready in time")
                handle.stop()
                return None, result
            result.stdout = f"dev server listening on {handle.url}"
            return handle, result
        except subprocess.TimeoutExpired as exc:
            result.errors.append(f"Dev server start timed out: {exc.stderr or ''}")
        except Exception as exc:
            result.errors.append(f"Dev server start failed: {exc}")
        return None, result

    def _wait_for_docker_log(self, container_id: str, pattern: str, timeout_ms: int) -> bool:
        deadline = time.time() + timeout_ms / 1000
        while time.time() < deadline:
            logs = subprocess.run(
                ["docker", "logs", container_id],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if pattern in logs.stdout or pattern in logs.stderr:
                return True
            time.sleep(0.5)
        return False

    def _stop_server(self, handle: SandboxServerHandle) -> dict[str, Any]:
        if handle.container_id:
            try:
                subprocess.run(
                    ["docker", "stop", "-t", "5", handle.container_id],
                    capture_output=True,
                    text=True,
                    timeout=15,
                )
                return {"url": handle.url, "stopped": True}
            except Exception as exc:
                return {"url": handle.url, "stopped": False, "error": str(exc)}
        if handle.wsl_pid:
            try:
                subprocess.run(
                    ["wsl", "-d", self.config.wsl_distro, "--", "kill", "-TERM", str(handle.wsl_pid)],
                    capture_output=True,
                    text=True,
                    timeout=10,
                )
                return {"url": handle.url, "stopped": True}
            except Exception as exc:
                return {"url": handle.url, "stopped": False, "error": str(exc)}
        return {"url": handle.url, "stopped": False, "error": "unknown handle type"}

    # ------------------------------------------------------------------
    # WSL2 implementation
    # ------------------------------------------------------------------
    def _execute_wsl(
        self,
        command: list[str] | str,
        cwd: str | None,
        timeout_ms: int,
        env: dict[str, str] | None,
        result: SandboxResult,
    ) -> SandboxResult:
        if not self._wsl_available():
            result.errors.append("WSL2 is not available on this host")
            return result

        workspace_in_wsl = self._host_path_to_wsl(self.config.workspace_root)
        work_dir = self._host_path_to_wsl(Path(cwd).resolve()) if cwd else workspace_in_wsl

        cmd = ["wsl", "-d", self.config.wsl_distro, "--", "bash", "-c"]
        env_prefix = ""
        for key, value in {**(env or {}), **self.config.env}.items():
            env_prefix += f"export {key}={shlex.quote(value)}\n"
        if isinstance(command, str):
            shell_cmd = f"cd {shlex.quote(work_dir)}\n{env_prefix}{command}"
        else:
            shell_cmd = f"cd {shlex.quote(work_dir)}\n{env_prefix}{shlex.join(command)}"
        cmd.append(shell_cmd)

        result.command = cmd
        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout_ms / 1000,
            )
            result.returncode = proc.returncode
            result.stdout = proc.stdout
            result.stderr = proc.stderr
        except subprocess.TimeoutExpired as exc:
            result.returncode = None
            result.stdout = exc.stdout or ""
            result.stderr = exc.stderr or ""
            result.errors.append(f"WSL2 sandbox timed out after {timeout_ms}ms")
        except Exception as exc:
            result.errors.append(f"WSL2 sandbox failed: {exc}")

        self._collect_artifacts(result)
        return result

    def _run_dev_server_wsl(
        self,
        command: list[str] | str,
        port: int,
        cwd: str | None,
        timeout_ms: int,
        env: dict[str, str] | None,
        ready_pattern: str,
        result: SandboxResult,
    ) -> tuple[SandboxServerHandle | None, SandboxResult]:
        if not self._wsl_available():
            result.errors.append("WSL2 is not available on this host")
            return None, result

        workspace_in_wsl = self._host_path_to_wsl(self.config.workspace_root)
        work_dir = self._host_path_to_wsl(Path(cwd).resolve()) if cwd else workspace_in_wsl

        # Start server in background inside WSL, redirect logs to a file in workspace.
        log_file = self.config.workspace_root / f".sandbox-server-{uuid.uuid4().hex[:8]}.log"
        env_prefix = ""
        for key, value in {**(env or {}), **self.config.env}.items():
            env_prefix += f"export {key}={shlex.quote(value)}\n"
        if isinstance(command, str):
            server_cmd = f"cd {shlex.quote(work_dir)}\n{env_prefix}{command}"
        else:
            server_cmd = f"cd {shlex.quote(work_dir)}\n{env_prefix}{shlex.join(command)}"

        start_script = (
            f"nohup bash -c {shlex.quote(server_cmd)} "
            f"> {shlex.quote(str(self._host_path_to_wsl(log_file)))} 2>&1 &\n"
            "echo $!"
        )
        try:
            proc = subprocess.run(
                ["wsl", "-d", self.config.wsl_distro, "--", "bash", "-c", start_script],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if proc.returncode != 0:
                result.errors.append(f"Failed to start WSL dev server: {proc.stderr}")
                return None, result
            pid = int(proc.stdout.strip().splitlines()[-1].strip())
            wsl_ip = self._wsl_ip()
            handle = SandboxServerHandle(
                url=f"http://{wsl_ip}:{port}",
                wsl_pid=pid,
                host_port=port,
                sandbox_path=work_dir,
                _engine=self,
            )
            ready = self._wait_for_wsl_log(log_file, ready_pattern, timeout_ms)
            if not ready:
                result.errors.append("WSL dev server did not become ready in time")
                handle.stop()
                return None, result
            result.stdout = f"dev server listening on {handle.url}"
            return handle, result
        except subprocess.TimeoutExpired as exc:
            result.errors.append(f"WSL dev server start timed out: {exc.stderr or ''}")
        except Exception as exc:
            result.errors.append(f"WSL dev server start failed: {exc}")
        return None, result

    def _wait_for_wsl_log(self, log_file: Path, pattern: str, timeout_ms: int) -> bool:
        deadline = time.time() + timeout_ms / 1000
        while time.time() < deadline:
            if log_file.exists():
                text = log_file.read_text(encoding="utf-8", errors="ignore")
                if pattern in text:
                    return True
            time.sleep(0.5)
        return False

    @staticmethod
    def _host_path_to_wsl(path: Path) -> str:
        """Convert a Windows absolute path to a WSL /mnt/<drive>/... path."""
        p = path.resolve()
        drive = p.drive.lower().rstrip(":")
        posix = p.as_posix()
        # If path is already POSIX-style (e.g. from Git Bash), leave it.
        if re.match(r"^/", posix):
            return posix
        return f"/mnt/{drive}{posix.replace(str(p.drive), '')}"

    @staticmethod
    def _wsl_ip() -> str:
        try:
            result = subprocess.run(
                ["wsl", "hostname", "-I"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            return result.stdout.strip().split()[0]
        except Exception:
            return "127.0.0.1"

    # ------------------------------------------------------------------
    # Artifacts and helpers
    # ------------------------------------------------------------------
    def _collect_artifacts(self, result: SandboxResult) -> None:
        """Copy configured artifact paths from workspace into a temp dir and record them."""
        if not self.config.artifact_paths:
            return
        for pattern in self.config.artifact_paths:
            matches = list(self.config.workspace_root.rglob(pattern))
            for src in matches:
                if src.is_file():
                    result.artifacts[src.name] = str(src.resolve())

    @staticmethod
    def _find_free_port() -> int:
        import socket

        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(("127.0.0.1", 0))
            return int(s.getsockname()[1])

    @staticmethod
    def _rewrite_localhost_for_docker(url: str) -> str:
        return re.sub(r"\b(localhost|127\.0\.0\.1)\b", "host.docker.internal", url)
