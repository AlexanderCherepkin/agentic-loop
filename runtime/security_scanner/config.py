"""Configuration for the security scanner runtime module."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class SecurityScannerConfig:
    """Configuration for SecurityScanner."""

    scan_secrets: bool = True
    scan_sqli: bool = True
    scan_xss: bool = True
    scan_hardcoded: bool = True
    scan_dependencies: bool = False
    dependency_tools: tuple[str, ...] = ("pip-audit", "bandit")
    severity_threshold: str = "medium"  # low | medium | high | critical
    excluded_paths: tuple[str, ...] = (
        "node_modules/",
        ".venv/",
        "__pycache__/",
        ".git/",
        "dist/",
        "build/",
    )

    def to_dict(self) -> dict[str, Any]:
        return {
            "scan_secrets": self.scan_secrets,
            "scan_sqli": self.scan_sqli,
            "scan_xss": self.scan_xss,
            "scan_hardcoded": self.scan_hardcoded,
            "scan_dependencies": self.scan_dependencies,
            "dependency_tools": list(self.dependency_tools),
            "severity_threshold": self.severity_threshold,
            "excluded_paths": list(self.excluded_paths),
        }
