"""Tests for runtime/security_scanner engine and config."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from runtime.security_scanner import SecurityScanner, SecurityScannerConfig


pytestmark = [pytest.mark.core, pytest.mark.runtime]


def test_config_to_dict_does_not_expose_dependency_fields():
    cfg = SecurityScannerConfig()
    data = cfg.to_dict()
    assert "scan_dependencies" not in data
    assert "dependency_tools" not in data
    assert data["scan_secrets"] is True


def test_scan_finds_secret_leak():
    scanner = SecurityScanner(SecurityScannerConfig())
    result = scanner.scan({"config.py": "API_KEY = 'sk-1234567890abcdef'"})
    assert not result.passed
    assert result.overall_risk == "critical"
    assert any(i.category == "secret" for i in result.issues)


def test_scan_clean_codebase_passes():
    scanner = SecurityScanner(SecurityScannerConfig())
    result = scanner.scan({"README.md": "# Clean project"})
    assert result.passed
    assert result.overall_risk == "low"
    assert not result.issues


def test_scan_ignores_excluded_paths():
    cfg = SecurityScannerConfig(excluded_paths=("node_modules/",))
    scanner = SecurityScanner(cfg)
    result = scanner.scan({"node_modules/leak.js": "API_KEY = 'sk-1234567890abcdef'"})
    assert result.passed
    assert not result.issues


def test_scan_disabled_secret_check_still_returns_result():
    cfg = SecurityScannerConfig(scan_secrets=False)
    scanner = SecurityScanner(cfg)
    result = scanner.scan({"config.py": "API_KEY = 'sk-1234567890abcdef'"})
    assert result.passed
    assert not result.issues
