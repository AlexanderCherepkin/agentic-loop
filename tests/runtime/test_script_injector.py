"""Tests for analytics script injector and privacy policy stub."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from runtime.analytics.script_injector import (
    SnippetSpec,
    build_privacy_policy_stub,
    build_script_tags,
    build_snippet,
)


def test_build_gtm_snippet_contains_id():
    spec = SnippetSpec(provider_id="gtm", tracking_id="GTM-123")
    code = build_snippet(spec)
    assert "gtm.js?id=GTM-123" in code
    assert "dataLayer" in code


def test_build_ga4_snippet():
    spec = SnippetSpec(provider_id="ga4", tracking_id="G-123")
    code = build_snippet(spec)
    assert "gtag('config', 'G-123'" in code
    assert "anonymize_ip" in code


def test_build_plausible_snippet():
    spec = SnippetSpec(provider_id="plausible", tracking_id="example.com")
    code = build_snippet(spec)
    assert "plausible.io" in code
    assert "data-domain" in code


def test_build_script_tags_include_consent_gated_script_component():
    specs = [
        SnippetSpec(provider_id="ga4", tracking_id="G-123"),
        SnippetSpec(provider_id="plausible", tracking_id="example.com"),
    ]
    tags = build_script_tags(specs)
    assert "ga4" in tags
    assert "plausible" in tags
    assert "Script" in tags["ga4"]
    assert "lazyOnload" in tags["plausible"]


def test_privacy_policy_stub_mentions_jurisdiction_rights():
    stub = build_privacy_policy_stub(
        jurisdictions=["GDPR", "CCPA"],
        providers=["ga4", "plausible"],
        contact_email="dpo@example.com",
    )
    assert "# Privacy Policy" in stub
    assert "ga4" in stub.lower()
    assert "plausible" in stub.lower()
    assert "dpo@example.com" in stub
    assert "Do Not Sell or Share" in stub
    assert "withdraw consent" in stub


def test_privacy_policy_stub_minimal():
    stub = build_privacy_policy_stub()
    assert "Privacy Policy" in stub
    assert "Contact Us" in stub
