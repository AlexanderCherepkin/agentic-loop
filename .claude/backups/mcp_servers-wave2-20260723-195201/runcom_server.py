from __future__ import annotations

import asyncio
import os
import platform
import shlex
import subprocess
import time
from pathlib import Path
from typing import Any

from .base import MCPServer
from runtime.safety.file_system_guard import FileSystemGuard, FSOperation, FSVerdict


class RuncomMCPServer(MCPServer):
    """MCP server for tools_runcom — command execution pipeline (sandboxed)."""

    # Base names of executables that may be launched directly. Shells and
    # interpreters with inline-code flags are excluded; see _blocked_inline_flags.
    DEFAULT_ALLOWED_EXECUTABLES: frozenset[str] = frozenset({
        "python", "python3", "py", "pytest", "pip", "pip3",
        "node", "npm", "npx", "yarn", "pnpm",
        "git",
        "echo", "ls", "cat", "mkdir", "rmdir", "cp", "mv", "rm", "touch",
        "find", "grep", "rg",
    })

    # Characters that imply shell interpretation / command chaining.
    SHELL_METACHARACTERS: set[str] = set(";|&`$()<>{}[]\\")

    # (executable, flag) pairs that allow arbitrary inline code execution.
    BLOCKED_INLINE_FLAGS: set[tuple[str, str]] = {
        ("python", "-c"), ("python3", "-c"), ("py", "-c"),
        ("node", "-e"), ("node", "--eval"),
    }

    def __init__(
        self,
        workspace_root: str = ".",
        sandbox_enabled: bool = True,
        allowed_executables: set[str] | None = None,
    ):
        super().__init__(name="tools_runcom", version="1.0.0")
        self.workspace = Path(workspace_root).resolve()
        self.sandbox_enabled = sandbox_enabled
        self.fs_guard = FileSystemGuard(self.workspace)
        self._allowed_executables = allowed_executables or set(self.DEFAULT_ALLOWED_EXECUTABLES)
        self._forbidden_commands = {"rm -rf /", "sudo ", "chmod 777 /", "mkfs.", "dd if=",
                                     ":(){ :|:& };:", "> /dev/sda"}
        self._command_history: list[dict[str, Any]] = []

        self.register("build_command", "Build a safe, optimized command string from parameters",
                       self._s({"executable": "string", "arguments": "array", "cwd?": "string"}),
                       self.build_command)
        self.register("optimize_command", "Optimize command for performance (batching, caching)",
                       self._s({"command": "string", "optimize_for?": "string"}),
                       self.optimize_command)
        self.register("setup_environment", "Setup environment variables for command execution",
                       self._s({"env_vars": "object", "cwd?": "string"}),
                       self.setup_environment)
        self.register("execute_command", "Execute a command with timeout and output capture (shell=False by default)",
                       self._s({"command": "string", "cwd?": "string", "timeout_ms?": "int",
                                "env?": "object", "shell?": "bool"}),
                       self.execute_command)
        self.register("sandbox_check", "Check if command is safe to execute in sandbox",
                       self._s({"command": "string"}), self.sandbox_check)
        self.register("capture_output", "Capture stdout/stderr from a running process",
                       self._s({"pid": "int"}), self.capture_output)
        self.register("handle_timeout", "Handle command timeout with graceful shutdown",
                       self._s({"pid": "int", "graceful_ms?": "int"}), self.handle_timeout)
        self.register("runcom_analyze_error", "Analyze command error output for known patterns",
                       self._s({"command": "string", "stderr": "string", "exit_code": "int"}),
                       self.analyze_error)
        self.register("get_history", "Get command execution history",
                       self._s({"limit?": "int"}), self.get_history)

    async def build_command(self, executable: str, arguments: list[str], cwd: str = "") -> dict[str, Any]:
        cmd = f"{executable} {' '.join(shlex.quote(a) for a in arguments)}"
        return {"command": cmd, "executable": executable, "arg_count": len(arguments),
                "estimated_length": len(cmd)}

    async def optimize_command(self, command: str, optimize_for: str = "speed") -> dict[str, Any]:
        optimizations: list[str] = []
        optimized = command
        if "&&" in command and optimize_for == "speed":
            optimizations.append("Parallel execution candidates detected (use & for independent commands)")
        if "|" in command:
            optimizations.append("Pipeline detected — consider buffering flags for large data")
        if optimize_for == "memory":
            optimizations.append("Memory optimization: use streaming where possible")
        return {"original": command, "optimized": optimized, "optimizations": optimizations,
                "optimize_for": optimize_for}

    async def setup_environment(self, env_vars: dict[str, str], cwd: str = "") -> dict[str, Any]:
        new_env = os.environ.copy()
        new_env.update(env_vars)
        work_dir = str(self.workspace / cwd) if cwd else str(self.workspace)
        return {"env_count": len(env_vars), "cwd": work_dir,
                "keys": list(env_vars.keys())}

    def _resolve_work_dir(self, cwd: str) -> str:
        """Resolve and validate cwd against the workspace via FileSystemGuard."""
        raw = str(self.workspace / cwd) if cwd else str(self.workspace)
        result = self.fs_guard.check(raw, FSOperation.EXECUTE)
        if result.verdict == FSVerdict.BLOCKED:
            raise PermissionError(f"cwd blocked: {result.reason}")
        if result.normalized_path:
            return result.normalized_path
        return raw

    def _validate_command_tokens(self, tokens: list[str]) -> dict[str, Any] | None:
        """Validate an already-tokenized command against the allow-list and inline-code flags."""
        if not tokens:
            return {"safe": False, "blocked": True, "reason": "Empty command"}

        executable = Path(tokens[0]).name
        if executable.lower() not in {e.lower() for e in self._allowed_executables}:
            return {"safe": False, "blocked": True,
                    "reason": f"Executable '{executable}' is not in the allow-list"}

        exe_lower = executable.lower()
        for idx, arg in enumerate(tokens[1:]):
            if not arg.startswith("-"):
                continue
            if (exe_lower, arg.lower()) in self.BLOCKED_INLINE_FLAGS:
                return {"safe": False, "blocked": True,
                        "reason": f"Inline execution flag '{arg}' is forbidden for {executable}"}
            # Block shell-style substitution / redirection markers sneaking into arguments.
            if any(ch in arg for ch in self.SHELL_METACHARACTERS):
                return {"safe": False, "blocked": True,
                        "reason": f"Argument '{arg}' contains shell metacharacters"}
        return None

    def _validate_command_string(self, command: str, shell: bool) -> dict[str, Any] | None:
        """Validate a raw command string. Returns a block dict if unsafe, else None."""
        cmd_lower = command.lower()
        for forbidden in self._forbidden_commands:
            if forbidden.lower() in cmd_lower:
                return {"safe": False, "blocked": True, "reason": f"Forbidden pattern: {forbidden}"}

        # Shell mode is deprecated and only accepted when the string is free of shell syntax.
        if shell and any(ch in command for ch in self.SHELL_METACHARACTERS):
            return {"safe": False, "blocked": True,
                    "reason": "shell=True with shell metacharacters is not permitted"}

        try:
            tokens = shlex.split(command)
        except ValueError as e:
            return {"safe": False, "blocked": True, "reason": f"Command parsing failed: {e}"}

        return self._validate_command_tokens(tokens)

    async def execute_command(self, command: str, cwd: str = "", timeout_ms: int = 30000,
                              env: dict[str, str] | None = None, shell: bool = False) -> dict[str, Any]:
        sandbox_result = await self.sandbox_check(command, shell=shell)
        if sandbox_result.get("blocked"):
            return {"error": sandbox_result["reason"], "blocked": True}

        try:
            work_dir = self._resolve_work_dir(cwd)
        except PermissionError as e:
            return {"error": str(e), "blocked": True}

        tokens = shlex.split(command)
        merged_env = os.environ.copy()
        if env:
            merged_env.update(env)

        t0 = time.perf_counter()
        try:
            proc = await asyncio.create_subprocess_exec(
                *tokens,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=work_dir,
                env=merged_env,
            )

            try:
                stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout_ms / 1000)
                timed_out = False
            except asyncio.TimeoutError:
                proc.kill()
                stdout, stderr = await proc.communicate()
                timed_out = True

            latency = (time.perf_counter() - t0) * 1000
            result = {
                "command": command,
                "exit_code": proc.returncode or (-1 if timed_out else 0),
                "stdout": stdout.decode("utf-8", errors="replace")[:50000],
                "stderr": stderr.decode("utf-8", errors="replace")[:10000],
                "timed_out": timed_out,
                "latency_ms": latency,
                "cwd": work_dir,
            }
        except FileNotFoundError:
            result = {"command": command, "exit_code": -1, "stdout": "", "stderr": "Command not found", "error": True}
        except Exception as e:
            result = {"command": command, "exit_code": -1, "stdout": "", "stderr": str(e), "error": True}

        self._command_history.append({"command": command, "exit_code": result.get("exit_code"),
                                       "timestamp": time.time()})
        return result

    async def sandbox_check(self, command: str, shell: bool = False) -> dict[str, Any]:
        return self._validate_command_string(command, shell=shell) or {"safe": True, "blocked": False}

    async def capture_output(self, pid: int) -> dict[str, Any]:
        return {"pid": pid, "available": False, "note": "Use execute_command for output capture"}

    async def handle_timeout(self, pid: int, graceful_ms: int = 3000) -> dict[str, Any]:
        return {"pid": pid, "action": "terminate", "graceful_ms": graceful_ms}

    async def analyze_error(self, command: str, stderr: str, exit_code: int) -> dict[str, Any]:
        patterns = {
            "command not found": {"type": "missing_executable", "fix": "Install the required program or check the path"},
            "permission denied": {"type": "permissions", "fix": "Check file permissions or use appropriate access level"},
            "no such file": {"type": "missing_file", "fix": "Verify the file path exists"},
            "out of memory": {"type": "oom", "fix": "Reduce data size or increase available memory"},
            "connection refused": {"type": "network", "fix": "Ensure the target service is running"},
            "syntax error": {"type": "syntax", "fix": "Check command syntax for errors"},
        }
        detected: list[dict[str, str]] = []
        stderr_lower = stderr.lower()
        for pattern, info in patterns.items():
            if pattern in stderr_lower:
                detected.append({"pattern": pattern, "type": info["type"], "fix": info["fix"]})

        return {"command": command, "exit_code": exit_code, "issues": detected, "count": len(detected)}

    async def get_history(self, limit: int = 20) -> dict[str, Any]:
        recent = self._command_history[-limit:]
        return {"history": recent, "total": len(self._command_history)}

    @staticmethod
    def _s(props: dict[str, str]) -> dict[str, Any]:
        required = [k for k in props if not k.endswith("?")]
        properties = {}
        for k, v in props.items():
            name = k.rstrip("?")
            type_map = {"string": "string", "int": "integer", "bool": "boolean", "float": "number", "array": "array", "object": "object"}
            properties[name] = {"type": type_map.get(v, "string"), "description": f"The {name} parameter"}
        return {"type": "object", "properties": properties, "required": required}
