from __future__ import annotations

import ipaddress
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any
from urllib.parse import urlparse


class NetworkVerdict(str, Enum):
    ALLOWED = "allowed"
    BLOCKED = "blocked"
    ESCALATE = "escalate"


@dataclass
class NetworkGuardResult:
    url: str
    host: str | None
    scheme: str | None
    verdict: NetworkVerdict
    reason: str = ""
    matched_allow: str | None = None
    matched_block: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "url": self.url,
            "host": self.host,
            "scheme": self.scheme,
            "verdict": self.verdict.value,
            "reason": self.reason,
            "matched_allow": self.matched_allow,
            "matched_block": self.matched_block,
        }


class NetworkGuard:
    """Deterministic network egress guardrail for the autonomous agent runtime.

    Enforces:
    - Default-deny policy: only explicitly allowed domains/hosts may be reached.
    - Block-list for private/internal networks and known dangerous destinations.
    - URL scheme restriction (http/https only).
    - Human escalation for domains that are not obviously dangerous but not allow-listed.

    The guard is intentionally non-LLM and runs before any network MCP tool executes.
    """

    DEFAULT_ALLOWED_DOMAINS = {
        "api.figma.com",
        "www.figma.com",
        "fonts.googleapis.com",
        "fonts.gstatic.com",
        "github.com",
        "raw.githubusercontent.com",
        "pypi.org",
        "files.pythonhosted.org",
        "registry.npmjs.org",
        "unpkg.com",
        "cdn.jsdelivr.net",
        "fonts.google.com",
        "www.google.com",
        "docs.python.org",
        "developer.mozilla.org",
    }

    DEFAULT_BLOCKED_DOMAINS = {
        "localhost",
        "127.0.0.1",
        "0.0.0.0",
        "::1",
        "metadata.google.internal",
        "metadata.aws.internal",
        "169.254.169.254",  # cloud metadata endpoint
        "consul",
        "etcd",
        "kube-apiserver",
        "docker.sock",
    }

    PRIVATE_NETWORK_PATTERNS = (
        r"^10\.",
        r"^172\.(1[6-9]|2[0-9]|3[0-1])\.",
        r"^192\.168\.",
        r"^169\.254\.",
        r"^127\.",
        r"^0\.0\.0\.0$",
        r"^::1$",
        r"^fc00:",
        r"^fe80:",
    )

    def __init__(
        self,
        allowed_domains: set[str] | list[str] | None = None,
        blocked_domains: set[str] | list[str] | None = None,
        default_policy: str = "deny",
    ):
        self.allowed_domains = {d.lower() for d in (allowed_domains or self.DEFAULT_ALLOWED_DOMAINS)}
        self.blocked_domains = {d.lower() for d in (blocked_domains or self.DEFAULT_BLOCKED_DOMAINS)}
        self.default_policy = default_policy.lower()
        if self.default_policy not in ("allow", "deny"):
            self.default_policy = "deny"

    def check_url(self, raw_url: str) -> NetworkGuardResult:
        """Evaluate whether a URL may be accessed by the runtime."""
        raw = str(raw_url).strip()
        if not raw:
            return NetworkGuardResult(
                url=raw,
                host=None,
                scheme=None,
                verdict=NetworkVerdict.BLOCKED,
                reason="Empty URL",
            )

        try:
            parsed = urlparse(raw)
        except Exception as e:
            return NetworkGuardResult(
                url=raw,
                host=None,
                scheme=None,
                verdict=NetworkVerdict.BLOCKED,
                reason=f"URL parse error: {e}",
            )

        scheme = (parsed.scheme or "http").lower()
        host = (parsed.hostname or "").lower()
        if not host:
            return NetworkGuardResult(
                url=raw,
                host=None,
                scheme=scheme,
                verdict=NetworkVerdict.BLOCKED,
                reason="URL has no host",
            )

        if scheme not in ("http", "https"):
            return NetworkGuardResult(
                url=raw,
                host=host,
                scheme=scheme,
                verdict=NetworkVerdict.BLOCKED,
                reason=f"Scheme '{scheme}' is not allowed",
            )

        # 1. Explicit block list (domain exact or IP)
        if host in self.blocked_domains:
            return NetworkGuardResult(
                url=raw,
                host=host,
                scheme=scheme,
                verdict=NetworkVerdict.BLOCKED,
                reason=f"Host '{host}' is in the block-list",
                matched_block=host,
            )

        # 2. Private IP / loopback / metadata endpoint detection
        ip_block_reason = self._check_ip(host)
        if ip_block_reason:
            return NetworkGuardResult(
                url=raw,
                host=host,
                scheme=scheme,
                verdict=NetworkVerdict.BLOCKED,
                reason=ip_block_reason,
                matched_block=host,
            )

        # 3. Allowed domain matching: exact, suffix, or parent domain
        matched_allow = self._match_allowed(host)
        if matched_allow:
            return NetworkGuardResult(
                url=raw,
                host=host,
                scheme=scheme,
                verdict=NetworkVerdict.ALLOWED,
                reason=f"Host matches allowed domain: {matched_allow}",
                matched_allow=matched_allow,
            )

        # 4. Default policy
        if self.default_policy == "deny":
            return NetworkGuardResult(
                url=raw,
                host=host,
                scheme=scheme,
                verdict=NetworkVerdict.BLOCKED,
                reason=f"Host '{host}' is not in the allow-list and default policy is deny",
            )

        return NetworkGuardResult(
            url=raw,
            host=host,
            scheme=scheme,
            verdict=NetworkVerdict.ESCALATE,
            reason=f"Host '{host}' is not in the allow-list; requires human escalation",
        )

    def _check_ip(self, host: str) -> str | None:
        """Return a blocking reason if host is a private/loopback/metadata IP."""
        for pattern in self.PRIVATE_NETWORK_PATTERNS:
            if re.search(pattern, host, re.IGNORECASE):
                return f"Host '{host}' resolves to a private/loopback/metadata network"
        try:
            addr = ipaddress.ip_address(host)
            if addr.is_private or addr.is_loopback or addr.is_link_local or addr.is_multicast or addr.is_reserved:
                return f"Host '{host}' is a non-public IP address"
        except ValueError:
            pass
        return None

    def _match_allowed(self, host: str) -> str | None:
        """Return the matching allowed domain only on exact match.

        Suffix/parent matching is intentionally disabled: allowing github.com
        must not allow attacker.github.com. Use explicit allow-list entries for
        subdomains.
        """
        if host in self.allowed_domains:
            return host
        return None

    def is_allowed(self, raw_url: str) -> bool:
        return self.check_url(raw_url).verdict == NetworkVerdict.ALLOWED

    def to_dict(self) -> dict[str, Any]:
        return {
            "allowed_domains": sorted(self.allowed_domains),
            "blocked_domains": sorted(self.blocked_domains),
            "default_policy": self.default_policy,
        }
