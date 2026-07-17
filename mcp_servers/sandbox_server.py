"""Sandbox MCP server.

Exposes the runtime/sandbox engine as MCP category `sandbox`. Runs commands,
builds and dev servers, and captures screenshots inside Docker or WSL2. When
neither backend is available the server reports `status: degraded` so the
ReAct loop can still plan around it.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

from .base import MCPServer


class SandboxMCPServer(MCPServer):
    """MCP server wrapping the Docker/WSL2 sandbox execution engine."""

    def __init__(self, workspace_root: str = "."):
        super().__init__(name="sandbox", version="1.0.0")
        self.workspace = Path(workspace_root).resolve()
        self._degraded_reason: str | None = None
        self._engine: Any | None = None
        self._register_tools()
        self._initialized = True

    def _register_tools(self) -> None:
        s = self._schema
        self.register(
            "sandbox_execute",
            "Execute a command inside a Docker or WSL2 sandbox",
            s({
                "command": "string",
                "args?": "array",
                "cwd?": "string",
                "timeout_ms?": "int",
                "env?": "object",
                "backend?": "string",
                "image?": "string",
                "wsl_distro?": "string",
                "network?": "string",
            }),
            self.sandbox_execute,
        )
        self.register(
            "sandbox_run_dev_server",
            "Run a dev server inside the sandbox and return its reachable URL",
            s({
                "command": "string",
                "port": "int",
                "args?": "array",
                "cwd?": "string",
                "timeout_ms?": "int",
                "env?": "object",
                "ready_pattern?": "string",
                "backend?": "string",
                "image?": "string",
                "wsl_distro?": "string",
            }),
            self.sandbox_run_dev_server,
        )
        self.register(
            "sandbox_screenshot",
            "Render a screenshot of a URL using Playwright inside the sandbox",
            s({
                "url": "string",
                "output_path": "string",
                "viewport_width?": "int",
                "viewport_height?": "int",
                "backend?": "string",
                "image?": "string",
                "wsl_distro?": "string",
            }),
            self.sandbox_screenshot,
        )
        self.register(
            "sandbox_cleanup",
            "Stop all active sandbox dev servers and remove transient containers",
            s({}),
            self.sandbox_cleanup,
        )
        self.register(
            "sandbox_status",
            "Check whether Docker or WSL2 sandbox backend is available",
            s({}),
            self.sandbox_status,
        )

    @staticmethod
    def _schema(props: dict[str, str]) -> dict[str, Any]:
        required = [k for k in props if not k.endswith("?")]
        properties: dict[str, Any] = {}
        type_map = {
            "string": "string",
            "int": "integer",
            "bool": "boolean",
            "float": "number",
            "array": "array",
            "object": "object",
        }
        for k, v in props.items():
            name = k.rstrip("?")
            properties[name] = {
                "type": type_map.get(v, "string"),
                "description": f"The {name} parameter",
            }
        return {"type": "object", "properties": properties, "required": required}

    def _load_engine(self) -> Any:
        """Lazy-load the runtime/sandbox engine."""
        if self._engine is not None:
            return self._engine
        try:
            from runtime.sandbox import SandboxConfig, SandboxEngine

            self._engine = SandboxEngine(
                SandboxConfig(workspace_root=str(self.workspace))
            )
            return self._engine
        except Exception as exc:
            self._degraded_reason = f"sandbox engine unavailable: {exc}"
            raise

    def _make_engine(self, overrides: dict[str, Any]) -> Any:
        from runtime.sandbox import SandboxBackend, SandboxConfig

        cfg = {
            "workspace_root": str(self.workspace),
            "backend": overrides.get("backend", "auto"),
            "image": overrides.get("image", "node:20-slim"),
            "wsl_distro": overrides.get("wsl_distro", "Ubuntu"),
        }
        if overrides.get("network"):
            cfg["network"] = overrides["network"]
        return SandboxEngine(SandboxConfig.from_dict(cfg))

    def _check_degraded(self) -> dict[str, Any] | None:
        if self._degraded_reason:
            return {
                "status": "degraded",
                "is_error": False,
                "degraded_reason": self._degraded_reason,
            }
        return None

    @staticmethod
    def _error_response(exc: Exception) -> dict[str, Any]:
        import traceback

        return {
            "status": "error",
            "is_error": True,
            "error": str(exc),
            "traceback": traceback.format_exc(),
        }

    def _coerce_command(
        self, command: str, args: list[str] | None
    ) -> list[str] | str:
        if args:
            return [command, *args]
        return command

    def sandbox_execute(
        self,
        command: str,
        args: list[str] | None = None,
        cwd: str = "",
        timeout_ms: int = 120_000,
        env: dict[str, str] | None = None,
        backend: str = "auto",
        image: str = "node:20-slim",
        wsl_distro: str = "Ubuntu",
        network: str = "bridge",
    ) -> dict[str, Any]:
        degraded = self._check_degraded()
        if degraded:
            return degraded

        try:
            engine = self._make_engine({
                "backend": backend,
                "image": image,
                "wsl_distro": wsl_distro,
                "network": network,
            })
            result = engine.execute(
                self._coerce_command(command, args),
                cwd=cwd or None,
                timeout_ms=timeout_ms,
                env=env,
            )
            return {
                "status": "success" if result.ok else "error",
                "is_error": not result.ok,
                **result.to_dict(),
            }
        except Exception as exc:
            return self._error_response(exc)

    def sandbox_run_dev_server(
        self,
        command: str,
        port: int,
        args: list[str] | None = None,
        cwd: str = "",
        timeout_ms: int = 30_000,
        env: dict[str, str] | None = None,
        ready_pattern: str = "Ready",
        backend: str = "auto",
        image: str = "node:20-slim",
        wsl_distro: str = "Ubuntu",
    ) -> dict[str, Any]:
        degraded = self._check_degraded()
        if degraded:
            return degraded

        try:
            engine = self._make_engine({
                "backend": backend,
                "image": image,
                "wsl_distro": wsl_distro,
            })
            result = engine.run_dev_server(
                self._coerce_command(command, args),
                port=port,
                cwd=cwd or None,
                timeout_ms=timeout_ms,
                env=env,
                ready_pattern=ready_pattern,
            )
            handle_data: dict[str, Any] | None = None
            if result.server_handle:
                handle_data = {
                    "url": result.server_handle.url,
                    "host_port": result.server_handle.host_port,
                    "sandbox_path": result.server_handle.sandbox_path,
                    "container_id": result.server_handle.container_id,
                    "wsl_pid": result.server_handle.wsl_pid,
                }
            return {
                "status": "success" if result.ok else "error",
                "is_error": not result.ok,
                **result.to_dict(),
                "server_handle": handle_data,
            }
        except Exception as exc:
            return self._error_response(exc)

    def sandbox_screenshot(
        self,
        url: str,
        output_path: str,
        viewport_width: int = 1280,
        viewport_height: int = 800,
        backend: str = "auto",
        image: str = "node:20-slim",
        wsl_distro: str = "Ubuntu",
    ) -> dict[str, Any]:
        degraded = self._check_degraded()
        if degraded:
            return degraded

        try:
            engine = self._make_engine({
                "backend": backend,
                "image": image,
                "wsl_distro": wsl_distro,
            })
            result = engine.screenshot(
                url,
                output_path,
                viewport={"width": viewport_width, "height": viewport_height},
            )
            return {
                "status": "success" if result.ok else "error",
                "is_error": not result.ok,
                **result.to_dict(),
            }
        except Exception as exc:
            return self._error_response(exc)

    def sandbox_cleanup(self) -> dict[str, Any]:
        degraded = self._check_degraded()
        if degraded:
            return degraded

        try:
            engine = self._load_engine()
            return {
                "status": "success",
                "is_error": False,
                **engine.cleanup(),
            }
        except Exception as exc:
            return self._error_response(exc)

    def sandbox_status(self) -> dict[str, Any]:
        docker = shutil.which("docker") or False
        wsl = shutil.which("wsl") or False
        if docker:
            try:
                proc = subprocess.run(
                    ["docker", "info"],
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
                docker_ok = proc.returncode == 0
            except Exception:
                docker_ok = False
        else:
            docker_ok = False

        available = docker_ok or bool(wsl)
        if self._degraded_reason:
            available = False

        return {
            "status": "success" if available else "degraded",
            "is_error": False,
            "available": available,
            "docker_available": docker_ok,
            "wsl_available": bool(wsl),
            "degraded_reason": self._degraded_reason,
        }

    async def ping(self) -> bool:
        return True
