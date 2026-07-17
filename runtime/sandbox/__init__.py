"""Docker/WSL2 sandbox execution runtime.

Provides isolated command execution, dev-server hosting and screenshot
capture for the Agentic Loop ReAct cycle. Falls back from Docker to WSL2
when Docker is unavailable.
"""

from __future__ import annotations

from .config import SandboxBackend, SandboxConfig
from .engine import SandboxEngine, SandboxResult, SandboxServerHandle

__all__ = [
    "SandboxBackend",
    "SandboxConfig",
    "SandboxEngine",
    "SandboxResult",
    "SandboxServerHandle",
]