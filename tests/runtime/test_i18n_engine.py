"""Tests for runtime/i18n engine, config and key namespace."""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import pytest

from runtime.i18n.config import FallbackMode, I18nConfig, LocalePrefixMode, LoadStrategy, RoutingStrategy
from runtime.i18n.engine import I18nIntegrationEngine
from runtime.i18n.key_namespace import KeyNamespace, normalize_namespace
from runtime.i18n.rtl_config import RTL_LOCALES, is_rtl


def test_i18n_config_validation_ok():
    cfg = I18nConfig(target_locales=["en", "ru"], default_locale="en")
    assert cfg.validate() == []


def test_i18n_config_validation_fails_for_missing_default():
    cfg = I18nConfig(target_locales=["en", "ru"], default_locale="de")
    errors = cfg.validate()
    assert any("default_locale must be in target_locales" in e for e in errors)


def test_i18n_config_from_requirements():
    req = {
        "target_locales": ["en", "ar", "ru"],
        "default_locale": "en",
        "rtl_locales": ["ar"],
        "fallback_mode": "language_only",
        "routing_strategy": "prefix",
        "locale_prefix": "always",
        "load_strategy": "dynamic",
    }
    cfg = I18nConfig.from_requirements(req)
    assert cfg.target_locales == ["en", "ar", "ru"]
    assert cfg.default_locale == "en"
    assert cfg.rtl_locales == ["ar"]
    assert cfg.fallback_mode == FallbackMode.LANGUAGE_ONLY
    assert cfg.routing_strategy == RoutingStrategy.PREFIX
    assert cfg.locale_prefix == LocalePrefixMode.ALWAYS
    assert cfg.load_strategy == LoadStrategy.DYNAMIC


def test_is_rtl_detects_arabic_variants():
    assert is_rtl("ar") is True
    assert is_rtl("ar-SA") is True
    assert is_rtl("en") is False
    assert is_rtl("ru-RU") is False
    assert is_rtl("") is False


def test_rtl_locales_coverage():
    assert "ar" in RTL_LOCALES
    assert "he" in RTL_LOCALES
    assert "fa" in RTL_LOCALES


def test_normalize_namespace():
    assert normalize_namespace("Hero Section") == "hero_section"
    assert normalize_namespace("API-Key (v2)") == "api_key_v2"
    assert normalize_namespace("!!!") == "default"


def test_key_namespace_extracts_and_deduplicates():
    ns = KeyNamespace(namespace="ui")
    k1 = ns.add_text("Hello world", section="hero")
    k2 = ns.add_text("Hello world", section="hero")
    k3 = ns.add_text("Welcome back", section="hero")
    assert k1 is not None
    assert k1.key == k2.key
    assert k3 is not None
    assert k3.key != k1.key
    assert len(ns.keys) == 2
    assert len(ns.duplicates) >= 1


def test_key_namespace_skips_non_translatable():
    ns = KeyNamespace(namespace="ui")
    assert ns.add_text("https://example.com") is None
    assert ns.add_text("42") is None
    assert ns.add_text("user@example.com") is None
    assert len(ns.keys) == 0


def test_key_namespace_to_nested_dict():
    ns = KeyNamespace(namespace="ui")
    ns.add_text("Submit", section="form")
    ns.add_text("Cancel", section="form")
    nested = ns.to_nested_dict()
    assert nested == {"form": {"submit": "Submit", "cancel": "Cancel"}}


def test_i18n_engine_writes_files(tmp_path):
    cfg = I18nConfig(target_locales=["en", "ru"], default_locale="en", rtl_locales=[])
    engine = I18nIntegrationEngine(tmp_path, cfg)
    dictionaries = {
        "en": {"hero": {"title": "Hello"}},
        "ru": {"hero": {"title": "Привет"}},
    }
    result = engine.run(dictionaries)
    assert not result.errors
    assert any("src/i18n.ts" in f for f in result.files_written)
    assert any("src/i18n/routing.ts" in f for f in result.files_written)
    assert any("src/i18n/request.ts" in f for f in result.files_written)
    assert any("middleware.ts" in f for f in result.files_written)
    assert any("messages/en.json" in f for f in result.files_written)
    assert any("messages/ru.json" in f for f in result.files_written)
    assert any("src/app/[locale]/layout.tsx" in f for f in result.files_written)
    assert any("src/app/page.tsx" in f for f in result.files_written)


def test_i18n_engine_messages_written_correctly(tmp_path):
    cfg = I18nConfig(target_locales=["en", "ru"], default_locale="en")
    engine = I18nIntegrationEngine(tmp_path, cfg)
    dictionaries = {
        "en": {"hero": {"title": "Hello"}},
        "ru": {"hero": {"title": "Привет"}},
    }
    engine.run(dictionaries)
    en = json.loads((tmp_path / "messages" / "en.json").read_text(encoding="utf-8"))
    ru = json.loads((tmp_path / "messages" / "ru.json").read_text(encoding="utf-8"))
    assert en["hero"]["title"] == "Hello"
    assert ru["hero"]["title"] == "Привет"


def test_i18n_engine_locale_layout_has_rtl_logic(tmp_path):
    cfg = I18nConfig(target_locales=["en", "ar"], default_locale="en", rtl_locales=["ar"])
    engine = I18nIntegrationEngine(tmp_path, cfg)
    engine.run({"en": {}, "ar": {}})
    layout = (tmp_path / "src" / "app" / "[locale]" / "layout.tsx").read_text(encoding="utf-8")
    assert "isRtl(locale) ? 'rtl' : 'ltr'" in layout
    assert '"ar"' in layout


def test_i18n_engine_adds_next_intl_dependency(tmp_path):
    pkg = {"name": "demo", "dependencies": {"next": "14"}}
    (tmp_path / "package.json").write_text(json.dumps(pkg), encoding="utf-8")
    cfg = I18nConfig(target_locales=["en"], default_locale="en")
    engine = I18nIntegrationEngine(tmp_path, cfg)
    engine.run({"en": {}})
    updated = json.loads((tmp_path / "package.json").read_text(encoding="utf-8"))
    assert updated["dependencies"]["next-intl"] == "^3.0.0"


def test_i18n_engine_validation_returns_early(tmp_path):
    cfg = I18nConfig(target_locales=[], default_locale="en")
    engine = I18nIntegrationEngine(tmp_path, cfg)
    result = engine.run({})
    assert result.errors
    assert not result.files_written


def test_i18n_config_rejects_malicious_locale():
    cfg = I18nConfig(target_locales=["en", "../etc/passwd"], default_locale="en")
    errors = cfg.validate()
    assert any("../etc/passwd" in e and "forbidden" in e for e in errors)

    cfg2 = I18nConfig(target_locales=["en", "ru-RU"], default_locale="en")
    assert cfg2.validate() == []


def test_i18n_engine_sanitizes_locale_in_dynamic_import_config(tmp_path):
    cfg = I18nConfig(target_locales=["en", "ru"], default_locale="en")
    engine = I18nIntegrationEngine(tmp_path, cfg)
    engine.run({"en": {}, "ru": {}})
    i18n_ts = (tmp_path / "src" / "i18n.ts").read_text(encoding="utf-8")
    assert "const LOCALE_PATTERN = /^[a-zA-Z0-9_-]+$/;" in i18n_ts
    assert "!LOCALE_PATTERN.test(locale as string)" in i18n_ts
    assert "const messages = (await import(`../../messages/${locale}.json`)).default;" in i18n_ts


def test_i18n_engine_sanitizes_locale_in_dynamic_import_request(tmp_path):
    cfg = I18nConfig(target_locales=["en", "ru"], default_locale="en")
    engine = I18nIntegrationEngine(tmp_path, cfg)
    engine.run({"en": {}, "ru": {}})
    request_ts = (tmp_path / "src" / "i18n" / "request.ts").read_text(encoding="utf-8")
    assert "const LOCALE_PATTERN = /^[a-zA-Z0-9_-]+$/;" in request_ts
    assert "!LOCALE_PATTERN.test(locale as string)" in request_ts
    assert "const messages = (await import(`../../messages/${locale}.json`)).default;" in request_ts
