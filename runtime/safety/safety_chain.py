from __future__ import annotations

import json
import re
import shlex
from dataclasses import dataclass, field
from enum import Enum
from pathlib import PurePath
from typing import Any


class SafetyLevel(str, Enum):
    CLEAR = "clear"
    WARNING = "warning"
    PAUSED = "paused"
    ABORTED = "aborted"


class SafetyVerdict(str, Enum):
    PROCEED = "proceed"
    RESUME_WITH_LIMITS = "resume_with_limits"
    ABORT_AND_REPORT = "abort_and_report"
    ESCALATE_TO_HUMAN = "escalate_to_human"


@dataclass
class GuardrailRule:
    name: str
    description: str
    severity: SafetyLevel
    evaluate: Any  # callable that returns bool when rule is triggered


@dataclass
class TriggeredRule:
    rule: GuardrailRule
    evidence: str
    severity: SafetyLevel


@dataclass
class SafetyResult:
    level: SafetyLevel
    verdict: SafetyVerdict
    triggered_rules: list[TriggeredRule] = field(default_factory=list)
    mitigations: list[str] = field(default_factory=list)


class SafetyChain:
    FORBIDDEN_PATTERNS = [
        (r"rm\s+-rf\s+/", SafetyLevel.ABORTED, "Recursive root deletion attempt"),
        (r"rm\s+(?:-\S+\s+)*\S*[\\/]", SafetyLevel.ABORTED, "Absolute-path deletion"),
        (r"rmdir\s+/s\s+", SafetyLevel.ABORTED, "Windows recursive directory deletion"),
        (r"del\s+/[fq]", SafetyLevel.ABORTED, "Windows force-delete flag"),
        (r"DROP\s+(TABLE|DATABASE)", SafetyLevel.PAUSED, "Database destruction command"),
        (r"curl\s+\S+", SafetyLevel.PAUSED, "Unreviewed network fetch"),
        (r"wget\s+\S+", SafetyLevel.PAUSED, "Unreviewed network fetch"),
        (r"curl.*\|\s*(ba)?sh", SafetyLevel.ABORTED, "Pipe-to-shell pattern"),
        (r"python\s+-c\s+", SafetyLevel.PAUSED, "Dynamic Python one-liner"),
        (r"python\s+-m\s+http\.server", SafetyLevel.PAUSED, "Ad-hoc HTTP server"),
        (r"eval\s*\(", SafetyLevel.ABORTED, "Dynamic code evaluation"),
        (r"exec\s*\(", SafetyLevel.ABORTED, "Dynamic code execution"),
        (r"os\.system\s*\(", SafetyLevel.ABORTED, "OS system call"),
        (r"subprocess\.(?:run|call|check_output|Popen)\s*\(", SafetyLevel.ABORTED, "Subprocess invocation"),
        (r"sudo\s+", SafetyLevel.PAUSED, "Privilege escalation attempt"),
        (r"/etc/(passwd|shadow)", SafetyLevel.ABORTED, "Access to system auth files"),
        (r"\.env", SafetyLevel.WARNING, "Access to environment secrets"),
        (r"mkfs", SafetyLevel.ABORTED, "Filesystem format"),
        (r"fdisk", SafetyLevel.ABORTED, "Partition manipulation"),
        (r"dd\s+if=/dev", SafetyLevel.ABORTED, "Disk overwrite"),
        (r">\s*/dev/[sh]da", SafetyLevel.ABORTED, "Disk overwrite"),
        (r":\(\)\s*{\s*:\|:", SafetyLevel.ABORTED, "Fork bomb"),
    ]

    FORBIDDEN_PATHS = [
        "/etc/", "/proc/", "/sys/", "/dev/",
        "C:\\Windows\\System32\\",
    ]

    ALLOWED_COMMANDS = {
        "git", "python", "python3", "pytest", "node", "npm", "pnpm", "yarn",
        "npx", "pip", "pipenv", "poetry", "mypy", "black", "ruff", "isort",
        "next", "tsc", "eslint", "prettier", "graphql-codegen", "prisma",
    }

    BLOCKED_COMMANDS = {
        "rm", "rmdir", "del", "erase", "format", "mkfs", "fdisk", "dd", "shred",
        "nc", "netcat", "nmap", "msfconsole", "sqlmap",
    }

    SHELL_INTERPRETERS = {"bash", "sh", "cmd", "powershell", "pwsh", "zsh", "fish"}

    def __init__(self, live_risk_threshold: float = 0.6):
        self.live_risk_threshold = live_risk_threshold
        self._rules = self._build_rules()
        self.triggered_rules: list[TriggeredRule] = []

    def _build_rules(self) -> list[GuardrailRule]:
        rules: list[GuardrailRule] = []
        for pattern, severity, desc in self.FORBIDDEN_PATTERNS:
            rules.append(GuardrailRule(
                name=f"forbidden_pattern:{desc}",
                description=desc,
                severity=severity,
                evaluate=lambda text, p=pattern: bool(re.search(p, str(text), re.IGNORECASE)),
            ))
        return rules

    def pre_check(self, user_input: str) -> SafetyResult:
        triggered = self._evaluate_text(user_input)
        result = self._compute_result(triggered)
        self.triggered_rules = result.triggered_rules
        return result

    def check_command(self, command: str, arguments: dict[str, Any] | list | None = None) -> SafetyResult:
        normalized = self._normalize_command(command, arguments)
        triggered = self._evaluate_text(normalized)
        triggered.extend(self._evaluate_command_base(command))

        result = self._compute_result(triggered)
        self.triggered_rules = result.triggered_rules
        return result

    def _normalize_command(self, command: str, arguments: dict[str, Any] | list | None) -> str:
        parts: list[str] = [str(command).strip()]
        if isinstance(arguments, dict):
            for key in sorted(arguments):
                parts.append(f"{key}={self._serialize_argument(arguments[key])}")
        elif isinstance(arguments, list):
            for arg in arguments:
                parts.append(self._serialize_argument(arg))
        return " ".join(parts)

    def _serialize_argument(self, value: Any) -> str:
        if value is None:
            return ""
        if isinstance(value, (dict, list)):
            return json.dumps(value, sort_keys=True, ensure_ascii=False)
        return shlex.quote(str(value))

    def _command_base(self, command: str) -> str:
        text = str(command).strip()
        # Strip common executable extensions and extract the last path segment.
        base = PurePath(text.split(None, 1)[0]).name
        for ext in (".exe", ".cmd", ".bat", ".ps1", ".py"):
            if base.lower().endswith(ext):
                base = base[: -len(ext)]
        return base.lower()

    def _evaluate_command_base(self, command: str) -> list[TriggeredRule]:
        base = self._command_base(command)
        if base in self.BLOCKED_COMMANDS:
            return [TriggeredRule(
                rule=GuardrailRule(name="blocked_command_base", description=f"Command '{base}' is in block-list", severity=SafetyLevel.ABORTED, evaluate=lambda x: True),
                evidence=f"blocked command base: {base}",
                severity=SafetyLevel.ABORTED,
            )]
        if base in self.SHELL_INTERPRETERS:
            return [TriggeredRule(
                rule=GuardrailRule(name="shell_interpreter", description=f"Shell interpreter '{base}' can execute arbitrary code", severity=SafetyLevel.PAUSED, evaluate=lambda x: True),
                evidence=f"shell interpreter: {base}",
                severity=SafetyLevel.PAUSED,
            )]
        if base not in self.ALLOWED_COMMANDS:
            return [TriggeredRule(
                rule=GuardrailRule(name="command_not_allowed", description=f"Command '{base}' is not in allow-list", severity=SafetyLevel.WARNING, evaluate=lambda x: True),
                evidence=f"command base: {base}",
                severity=SafetyLevel.WARNING,
            )]
        return []

    def _evaluate_text(self, text: str) -> list[TriggeredRule]:
        triggered: list[TriggeredRule] = []
        for rule in self._rules:
            try:
                if rule.evaluate(text):
                    triggered.append(TriggeredRule(rule=rule, evidence="Matched pattern in input", severity=rule.severity))
            except Exception:
                continue

        for path in self.FORBIDDEN_PATHS:
            if path.lower() in str(text).lower():
                triggered.append(TriggeredRule(
                    rule=GuardrailRule(name="forbidden_path", description=f"Access to {path}", severity=SafetyLevel.ABORTED, evaluate=lambda x: True),
                    evidence=f"Path reference: {path}",
                    severity=SafetyLevel.ABORTED,
                ))

        return triggered

    def post_check(self, output: str) -> SafetyResult:
        triggered: list[TriggeredRule] = []

        sensitive_patterns = [
            (r"api[_-]?key[:=]\s*\S+", "API key in output"),
            (r"token[:=]\s*\S+", "Token in output"),
            (r"password[:=]\s*\S+", "Password in output"),
            (r"secret[:=]\s*\S+", "Secret in output"),
        ]
        for pattern, desc in sensitive_patterns:
            if re.search(pattern, str(output), re.IGNORECASE):
                triggered.append(TriggeredRule(
                    rule=GuardrailRule(name="sensitive_data_leak", description=desc, severity=SafetyLevel.ABORTED, evaluate=lambda x: True),
                    evidence=f"Pattern: {pattern}",
                    severity=SafetyLevel.ABORTED,
                ))

        result = self._compute_result(triggered)
        self.triggered_rules = result.triggered_rules
        return result

    def check_content(self, content: str) -> SafetyResult:
        triggered: list[TriggeredRule] = []

        suspicious = [
            (r"<script[^>]*>", "XSS attempt"),
            (r"javascript\s*:\s*", "JS injection"),
            (r"onerror\s*=", "Event handler injection"),
        ]
        for pattern, desc in suspicious:
            if re.search(pattern, str(content), re.IGNORECASE):
                triggered.append(TriggeredRule(
                    rule=GuardrailRule(name="xss", description=desc, severity=SafetyLevel.ABORTED, evaluate=lambda x: True),
                    evidence=f"Pattern: {pattern}",
                    severity=SafetyLevel.ABORTED,
                ))

        result = self._compute_result(triggered)
        self.triggered_rules = result.triggered_rules
        return result

    def _compute_result(self, triggered: list[TriggeredRule]) -> SafetyResult:
        if not triggered:
            return SafetyResult(level=SafetyLevel.CLEAR, verdict=SafetyVerdict.PROCEED)

        severities = {r.severity for r in triggered}
        mitigations: list[str] = []

        if SafetyLevel.ABORTED in severities:
            return SafetyResult(
                level=SafetyLevel.ABORTED,
                verdict=SafetyVerdict.ABORT_AND_REPORT,
                triggered_rules=triggered,
                mitigations=["Operation aborted", "Preserved state before abort"],
            )

        if SafetyLevel.PAUSED in severities:
            return SafetyResult(
                level=SafetyLevel.PAUSED,
                verdict=SafetyVerdict.RESUME_WITH_LIMITS,
                triggered_rules=triggered,
                mitigations=["Execution paused", "Requesting plan adjustment"],
            )

        return SafetyResult(
            level=SafetyLevel.WARNING,
            verdict=SafetyVerdict.PROCEED,
            triggered_rules=triggered,
            mitigations=["Warnings logged for review"],
        )
