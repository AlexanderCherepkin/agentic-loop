"""Tests for runtime/analytics engine, categories and CSP builder."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import pytest

from runtime.analytics.categories import (
    ConsentCategory,
    JURISDICTION_DEFAULTS,
    category_for_provider,
    requires_consent,
)
from runtime.analytics.csp_helper import build_csp_directives, provider_csp_domains
from runtime.analytics.engine import AnalyticsIntegrationEngine, ProviderConfig


def test_category_for_provider():
    assert category_for_provider("ga4") == ConsentCategory.ANALYTICS
    assert category_for_provider("YANDEX") == ConsentCategory.ANALYTICS
    assert category_for_provider("unknown") == ConsentCategory.ANALYTICS


def test_requires_consent_under_gdpr():
    assert requires_consent("ga4", ["GDPR"]) is True
    assert requires_consent("ga4", ["CCPA"]) is False


def test_jurisdiction_defaults_shape():
    assert "GDPR" in JURISDICTION_DEFAULTS
    assert JURISDICTION_DEFAULTS["GDPR"]["default_deny"] is True
    assert ConsentCategory.MARKETING in JURISDICTION_DEFAULTS["GDPR"]["categories"]
    assert "CCPA" in JURISDICTION_DEFAULTS
    assert JURISDICTION_DEFAULTS["CCPA"].get("notice_required") is True


def test_provider_csp_domains():
    ga4 = provider_csp_domains("ga4")
    assert "https://www.googletagmanager.com" in ga4["script-src"]
    assert "https://www.google-analytics.com" in ga4["connect-src"]
    assert "https://www.google-analytics.com" in ga4["img-src"]


def test_build_csp_directives():
    directives = build_csp_directives(["ga4", "yandex"])
    assert "https://www.googletagmanager.com" in directives["script-src"]
    assert "https://mc.yandex.ru" in directives["connect-src"]
    assert "https://www.google-analytics.com" in directives["img-src"]


def test_provider_config_from_dict():
    cfg = ProviderConfig.from_dict(
        {"provider_id": "ga4", "tracking_id": "G-123", "events": ["click"], "consent_category": "analytics"}
    )
    assert cfg.provider_id == "ga4"
    assert cfg.tracking_id == "G-123"
    assert cfg.events == ["click"]
    assert cfg.consent_category == ConsentCategory.ANALYTICS


def test_analytics_engine_validates_missing_package(tmp_path):
    engine = AnalyticsIntegrationEngine(tmp_path, [ProviderConfig(provider_id="ga4")])
    result = engine.run()
    assert any("package.json" in e["reason"] for e in result.errors)


def test_analytics_engine_writes_files(tmp_path):
    (tmp_path / "package.json").write_text('{"name":"demo"}', encoding="utf-8")
    providers = [
        ProviderConfig(provider_id="ga4", tracking_id="G-123", events=["page_view"]),
        ProviderConfig(provider_id="yandex", tracking_id="12345", events=["reachGoal"]),
    ]
    engine = AnalyticsIntegrationEngine(tmp_path, providers, jurisdictions=["GDPR"])
    result = engine.run(
        consent_policies={"en": {"banner_title": "Cookies"}},
        event_registry=[{"name": "page_view"}],
    )
    assert not result.errors
    assert any("src/lib/consent-store.ts" in f for f in result.files_written)
    assert any("src/components/CookieConsent.tsx" in f for f in result.files_written)
    assert any("src/lib/analytics.ts" in f for f in result.files_written)
    assert any("src/lib/analytics/ga4.ts" in f for f in result.files_written)
    assert any("src/lib/analytics/yandex.ts" in f for f in result.files_written)
    assert any("src/lib/analytics/events.ts" in f for f in result.files_written)
    assert set(result.providers_installed) == {"ga4", "yandex"}


def test_analytics_engine_provider_disabled(tmp_path):
    (tmp_path / "package.json").write_text('{"name":"demo"}', encoding="utf-8")
    providers = [
        ProviderConfig(provider_id="ga4", enabled=True, tracking_id="G-1"),
        ProviderConfig(provider_id="mixpanel", enabled=False),
    ]
    engine = AnalyticsIntegrationEngine(tmp_path, providers)
    result = engine.run()
    assert not result.errors
    assert result.providers_installed == ["ga4"]


def test_analytics_engine_next_config_csp_patch(tmp_path):
    (tmp_path / "package.json").write_text('{"name":"demo"}', encoding="utf-8")
    (tmp_path / "next.config.js").write_text("/** @type {import('next').NextConfig} */\nmodule.exports = {};\n", encoding="utf-8")
    engine = AnalyticsIntegrationEngine(
        tmp_path,
        [ProviderConfig(provider_id="ga4", tracking_id="G-1")],
    )
    result = engine.run()
    assert not result.errors
    assert any(str(tmp_path / "next.config.js") == f for f in result.files_modified)
    config_text = (tmp_path / "next.config.js").read_text(encoding="utf-8")
    assert "analytics-csp-start" in config_text
    assert "Content-Security-Policy" in config_text
    assert "https://www.googletagmanager.com" in config_text


def test_analytics_engine_idempotent_csp_patch(tmp_path):
    (tmp_path / "package.json").write_text('{"name":"demo"}', encoding="utf-8")
    (tmp_path / "next.config.js").write_text("module.exports = {};\n", encoding="utf-8")
    engine = AnalyticsIntegrationEngine(
        tmp_path,
        [ProviderConfig(provider_id="ga4", tracking_id="G-1")],
    )
    engine.run()
    engine2 = AnalyticsIntegrationEngine(
        tmp_path,
        [ProviderConfig(provider_id="yandex", tracking_id="123")],
    )
    result2 = engine2.run()
    config_text = (tmp_path / "next.config.js").read_text(encoding="utf-8")
    markers = config_text.count("analytics-csp-start")
    assert markers == 1
    assert "https://mc.yandex.ru" in config_text
