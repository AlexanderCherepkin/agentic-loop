"""SecurityScanner engine."""

from __future__ import annotations

import logging
import re
from typing import Any

from pydantic import BaseModel, Field

from .config import SecurityScannerConfig

logger = logging.getLogger(__name__)


class SecurityIssue(BaseModel):
    """One security issue."""

    file: str = Field(..., description="File path")
    severity: str = Field(..., description="critical | high | medium | low")
    category: str = Field(..., description="secret | sqli | xss | hardcoded | dependency | other")
    line: int | None = Field(None, description="Line number")
    title: str = Field(..., description="Issue title")
    description: str = Field(..., description="Issue description")
    fix: str | None = Field(None, description="Fix recommendation")


class SecurityScanResult(BaseModel):
    """Result of a security scan."""

    passed: bool = Field(..., description="True if no blocking issues")
    overall_risk: str = Field(..., description="low | medium | high | critical")
    issues: list[SecurityIssue] = Field(default_factory=list)
    dependency_vulnerabilities: list[dict[str, Any]] = Field(default_factory=list)


class SecurityScanner:
    """Local security scanner for generated codebases."""

    _SECRET_PATTERNS: list[tuple[str, re.Pattern[str], str]] = [
        (
            "AWS Access Key",
            re.compile(r"AKIA[0-9A-Z]{16}"),
            "AWS Access Key ID detected. Use environment variables / secret manager.",
        ),
        (
            "Private key",
            re.compile(r"-----BEGIN (RSA |EC |DSA |OPENSSH )?PRIVATE KEY-----"),
            "Private key detected. Never store keys in code.",
        ),
        (
            "GitHub token",
            re.compile(r"gh[pousr]_[A-Za-z0-9_]{36,}"),
            "GitHub token detected. Move to environment variables.",
        ),
        (
            "OpenAI API key",
            re.compile(r"sk-[a-zA-Z0-9]{48}"),
            "OpenAI API key detected. Use .env or secret manager.",
        ),
        (
            "Generic API key",
            re.compile(
                r"(?i)(api[_-]?key|apikey|secret[_-]?key|auth[_-]?token)\s*[:=]\s*[\"']?[a-zA-Z0-9_\-]{16,}[\"']?"
            ),
            "Potential API key / secret token. Move to environment variables.",
        ),
        (
            "Password in code",
            re.compile(r"(?i)(password|passwd|pwd)\s*[:=]\s*[\"'][^\"'\s]{4,}[\"']"),
            "Password in code. Use hashing and environment variables.",
        ),
    ]

    _SQLI_PATTERNS: list[tuple[re.Pattern[str], str]] = [
        (
            re.compile(
                r"(?i)(execute|cursor\.execute|\.query|raw_query)\s*\(\s*[\"'][^\"']*%s[^\"']*[\"']"
            ),
            "Possible SQL injection: string interpolation in SQL query.",
        ),
        (
            re.compile(r"(?i)f[\"']\s*SELECT\s+.*\{.*\}.*FROM"),
            "f-string in SQL query — SQL injection risk.",
        ),
        (
            re.compile(r"(?i)(SELECT|INSERT|UPDATE|DELETE).*(\+\s*\w+|%\s*\w+|\.format\s*\([^)]*\))"),
            "Concatenation / formatting in SQL query — potential SQLi.",
        ),
    ]

    _XSS_PATTERNS: list[tuple[re.Pattern[str], str]] = [
        (re.compile(r"(?i)innerHTML\s*=\s*[^;]+"), "innerHTML assignment without sanitization — XSS risk."),
        (re.compile(r"(?i)document\.write\s*\("), "document.write may lead to XSS."),
        (re.compile(r"(?i)dangerouslySetInnerHTML"), "dangerouslySetInnerHTML without checks — XSS risk."),
    ]

    _HARDCODED_PATTERNS: list[tuple[re.Pattern[str], str, str]] = [
        (
            re.compile(r"(?i)admin\s*[:=]\s*[\"'][^\"']+[\"']"),
            "Hardcoded admin credential",
            "Remove hardcoded credentials; use env / secret manager.",
        ),
        (
            re.compile(r"(?i)(localhost|127\.0\.0\.1).*root.*[\"'][^\"']+[\"']"),
            "Hardcoded DB credential",
            "Connection string with credentials in code. Use environment variables.",
        ),
    ]

    _RISK_ORDER = {"low": 0, "medium": 1, "high": 2, "critical": 3}

    def __init__(self, config: SecurityScannerConfig | None = None) -> None:
        self.config = config or SecurityScannerConfig()

    def scan(
        self,
        codebase: dict[str, str],
        manifest: str = "",
        brief: str = "",
    ) -> SecurityScanResult:
        """Scan a codebase and return a structured security report."""
        issues: list[SecurityIssue] = []
        for path, content in codebase.items():
            if self._is_excluded(path):
                continue
            issues.extend(self._scan_file(path, content))

        dep_vulns: list[dict[str, Any]] = []
        if self.config.scan_dependencies:
            dep_vulns = self._scan_dependencies(codebase)

        overall_risk = self._compute_risk(issues, dep_vulns)
        passed = self._RISK_ORDER[overall_risk] < self._RISK_ORDER[self.config.severity_threshold]

        logger.info(
            "Security scan: risk=%s, issues=%d, dep_vulns=%d, passed=%s",
            overall_risk,
            len(issues),
            len(dep_vulns),
            passed,
        )
        return SecurityScanResult(
            passed=passed,
            overall_risk=overall_risk,
            issues=issues,
            dependency_vulnerabilities=dep_vulns,
        )

    def _is_excluded(self, path: str) -> bool:
        return any(excluded in path for excluded in self.config.excluded_paths)

    def _scan_file(self, path: str, content: str) -> list[SecurityIssue]:
        issues: list[SecurityIssue] = []
        lines = content.splitlines()

        if self.config.scan_secrets:
            for name, pattern, fix in self._SECRET_PATTERNS:
                for line_no, line in enumerate(lines, start=1):
                    for match in pattern.finditer(line):
                        issues.append(
                            SecurityIssue(
                                file=path,
                                severity="critical",
                                category="secret",
                                line=line_no,
                                title=f"Secret leak: {name}",
                                description=f"Suspicious string: {match.group(0)[:40]}...",
                                fix=fix,
                            )
                        )

        if self.config.scan_sqli:
            for pattern, description in self._SQLI_PATTERNS:
                for line_no, line in enumerate(lines, start=1):
                    if pattern.search(line):
                        issues.append(
                            SecurityIssue(
                                file=path,
                                severity="high",
                                category="sqli",
                                line=line_no,
                                title="Potential SQL injection",
                                description=description,
                                fix="Use parameterized queries / ORM.",
                            )
                        )

        if self.config.scan_xss:
            for pattern, description in self._XSS_PATTERNS:
                for line_no, line in enumerate(lines, start=1):
                    if pattern.search(line):
                        issues.append(
                            SecurityIssue(
                                file=path,
                                severity="high",
                                category="xss",
                                line=line_no,
                                title="Potential XSS",
                                description=description,
                                fix="Sanitize output; use safe templating engines.",
                            )
                        )

        if self.config.scan_hardcoded:
            for pattern, title, fix in self._HARDCODED_PATTERNS:
                for line_no, line in enumerate(lines, start=1):
                    if pattern.search(line):
                        issues.append(
                            SecurityIssue(
                                file=path,
                                severity="medium",
                                category="hardcoded",
                                line=line_no,
                                title=title,
                                description=f"Suspicious string: {line.strip()[:80]}...",
                                fix=fix,
                            )
                        )

        return issues

    def _scan_dependencies(self, codebase: dict[str, str]) -> list[dict[str, Any]]:
        """Best-effort dependency vulnerability scan (placeholder)."""
        # Real scanning would require pip-audit/safety/bandit tools.
        # Returning empty list keeps the engine deterministic and lightweight.
        return []

    def _compute_risk(
        self,
        issues: list[SecurityIssue],
        dep_vulns: list[dict[str, Any]],
    ) -> str:
        max_risk = 0
        for issue in issues:
            max_risk = max(max_risk, self._RISK_ORDER.get(issue.severity, 0))
        for vuln in dep_vulns:
            severity = str(vuln.get("severity", "low")).lower()
            max_risk = max(max_risk, self._RISK_ORDER.get(severity, 0))
        for risk, order in self._RISK_ORDER.items():
            if order == max_risk:
                return risk
        return "low"
