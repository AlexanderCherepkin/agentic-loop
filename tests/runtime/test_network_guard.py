from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from runtime.safety.network_guard import NetworkGuard, NetworkVerdict


@pytest.fixture
def guard():
    return NetworkGuard()


class TestNetworkGuardDefaults:
    def test_allows_figma_api(self, guard):
        result = guard.check_url("https://api.figma.com/v1/files/abc")
        assert result.verdict == NetworkVerdict.ALLOWED
        assert "figma.com" in result.matched_allow

    def test_allows_github_raw(self, guard):
        result = guard.check_url("https://raw.githubusercontent.com/foo/bar/main/README.md")
        assert result.verdict == NetworkVerdict.ALLOWED
        assert result.matched_allow in ("github.com", "raw.githubusercontent.com")

    def test_blocks_localhost(self, guard):
        result = guard.check_url("http://localhost:8080/admin")
        assert result.verdict == NetworkVerdict.BLOCKED
        assert "localhost" in result.reason.lower()

    def test_blocks_127_0_0_1(self, guard):
        result = guard.check_url("http://127.0.0.1:3000/")
        assert result.verdict == NetworkVerdict.BLOCKED

    def test_blocks_private_ip_10(self, guard):
        result = guard.check_url("http://10.0.0.1/api")
        assert result.verdict == NetworkVerdict.BLOCKED
        assert "private" in result.reason.lower()

    def test_blocks_private_ip_192_168(self, guard):
        result = guard.check_url("https://192.168.1.1/router")
        assert result.verdict == NetworkVerdict.BLOCKED

    def test_blocks_metadata_endpoint(self, guard):
        result = guard.check_url("http://169.254.169.254/latest/meta-data/")
        assert result.verdict == NetworkVerdict.BLOCKED

    def test_blocks_unknown_domain_in_deny_mode(self, guard):
        result = guard.check_url("https://evil.example.com/data")
        assert result.verdict == NetworkVerdict.BLOCKED
        assert "not in the allow-list" in result.reason.lower()

    def test_blocks_non_http_scheme(self, guard):
        result = guard.check_url("file:///etc/passwd")
        assert result.verdict == NetworkVerdict.BLOCKED
        assert "scheme" in result.reason.lower() or "host" in result.reason.lower()

    def test_blocks_empty_url(self, guard):
        result = guard.check_url("")
        assert result.verdict == NetworkVerdict.BLOCKED


class TestNetworkGuardPolicies:
    def test_allow_mode_escalates_unknown(self):
        guard = NetworkGuard(default_policy="allow")
        result = guard.check_url("https://unknown.example.com/")
        assert result.verdict == NetworkVerdict.ESCALATE

    def test_custom_allowed_domain(self):
        guard = NetworkGuard(allowed_domains={"my-app.internal"})
        result = guard.check_url("https://my-app.internal/api")
        assert result.verdict == NetworkVerdict.ALLOWED

    def test_custom_blocked_domain(self):
        guard = NetworkGuard(blocked_domains={"banned.test"})
        result = guard.check_url("https://banned.test/x")
        assert result.verdict == NetworkVerdict.BLOCKED
        assert result.matched_block == "banned.test"


class TestNetworkGuardHelpers:
    def test_is_allowed(self, guard):
        assert guard.is_allowed("https://www.figma.com/design/abc") is True
        assert guard.is_allowed("http://localhost:3000") is False

    def test_to_dict_serializes(self, guard):
        data = guard.to_dict()
        assert data["default_policy"] == "deny"
        assert "api.figma.com" in data["allowed_domains"]
        assert "localhost" in data["blocked_domains"]
