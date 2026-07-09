"""Engine-level tests for GTM/GA4/Plausible snippets and privacy policy stub."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from runtime.analytics.engine import AnalyticsIntegrationEngine, ProviderConfig


def test_engine_writes_ga4_loader(tmp_path):
    (tmp_path / "package.json").write_text('{"name":"demo"}', encoding="utf-8")
    engine = AnalyticsIntegrationEngine(
        tmp_path,
        [ProviderConfig(provider_id="ga4", tracking_id="G-123")],
    )
    result = engine.run()
    assert not result.errors
    assert any("src/components/analytics/ga4Loader.tsx" in f for f in result.files_written)


def test_engine_writes_plausible_loader(tmp_path):
    (tmp_path / "package.json").write_text('{"name":"demo"}', encoding="utf-8")
    engine = AnalyticsIntegrationEngine(
        tmp_path,
        [ProviderConfig(provider_id="plausible", tracking_id="example.com")],
    )
    result = engine.run()
    assert not result.errors
    assert any("src/components/analytics/plausibleLoader.tsx" in f for f in result.files_written)


def test_engine_writes_gtm_loader(tmp_path):
    (tmp_path / "package.json").write_text('{"name":"demo"}', encoding="utf-8")
    engine = AnalyticsIntegrationEngine(
        tmp_path,
        [ProviderConfig(provider_id="gtm", tracking_id="GTM-123")],
    )
    result = engine.run()
    assert not result.errors
    assert any("src/components/analytics/gtmLoader.tsx" in f for f in result.files_written)


def test_engine_writes_privacy_policy_stub(tmp_path):
    (tmp_path / "package.json").write_text('{"name":"demo"}', encoding="utf-8")
    engine = AnalyticsIntegrationEngine(
        tmp_path,
        [ProviderConfig(provider_id="ga4", tracking_id="G-123")],
        jurisdictions=["GDPR"],
    )
    result = engine.run()
    assert not result.errors
    assert any("src/app/privacy/page.mdx" in f for f in result.files_written)
    content = (tmp_path / "src" / "app" / "privacy" / "page.mdx").read_text(encoding="utf-8")
    assert "Privacy Policy" in content
    assert "withdraw consent" in content


def test_engine_skips_yandex_loader(tmp_path):
    (tmp_path / "package.json").write_text('{"name":"demo"}', encoding="utf-8")
    engine = AnalyticsIntegrationEngine(
        tmp_path,
        [ProviderConfig(provider_id="yandex", tracking_id="12345")],
    )
    result = engine.run()
    assert not result.errors
    assert not any("src/components/analytics" in f for f in result.files_written)
