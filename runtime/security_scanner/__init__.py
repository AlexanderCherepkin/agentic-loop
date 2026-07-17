"""Security scanner runtime module.

Scans generated codebases locally for secrets, SQL injections, XSS vectors,
hardcoded credentials, and dependency vulnerabilities.
"""

from __future__ import annotations

from .config import SecurityScannerConfig
from .engine import SecurityIssue, SecurityScanResult, SecurityScanner

__all__ = [
    "SecurityIssue",
    "SecurityScanner",
    "SecurityScannerConfig",
    "SecurityScanResult",
]
