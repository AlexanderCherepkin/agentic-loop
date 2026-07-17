from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .base import MCPServer, MCPToolResult
from runtime.security_scanner import SecurityScanner, SecurityScannerConfig


class SecurityScannerMCPServer(MCPServer):
    """MCP server for security scanning generated codebases."""

    def __init__(self, workspace_root: str = "."):
        super().__init__(name="security_scanner", version="1.0.0")
        self.workspace = Path(workspace_root).resolve()
        self._register_all()

    def _schema(self, props: dict[str, str]) -> dict[str, Any]:
        required = [k for k in props if not k.endswith("?")]
        properties: dict[str, Any] = {}
        for k, v in props.items():
            name = k[:-1] if k.endswith("?") else k
            properties[name] = {"type": v}
        return {
            "type": "object",
            "properties": properties,
            "required": required,
        }

    def _register_all(self):
        self.register(
            "scan_codebase",
            "Scan a codebase dict for secrets, SQLi, XSS, and hardcoded credentials",
            self._schema({"codebase": "object"}),
            self.scan_codebase,
        )

    async def scan_codebase(self, codebase: dict[str, str]) -> dict[str, Any]:
        try:
            scanner = SecurityScanner(SecurityScannerConfig())
            result = scanner.scan(codebase)
            return {
                "status": "success",
                "passed": result.passed,
                "overall_risk": result.overall_risk,
                "issue_count": len(result.issues),
                "issues": [issue.model_dump() for issue in result.issues],
            }
        except Exception as exc:
            return {"status": "error", "detail": str(exc)}
