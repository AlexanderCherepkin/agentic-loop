from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class RoutingStrategy(Enum):
    PREFIX = "prefix"
    DOMAIN = "domain"
    COOKIE = "cookie"
    SUBPATH = "subpath"


class LocalePrefixMode(Enum):
    ALWAYS = "always"
    AS_NEEDED = "as-needed"


class FallbackMode(Enum):
    DEFAULT_LOCALE = "default_locale"
    LANGUAGE_ONLY = "language_only"
    NONE = "none"


class TranslationScope(Enum):
    FULL = "full"
    UI_ONLY = "ui_only"
    KEYS_ONLY = "keys_only"
    NONE = "none"


class LoadStrategy(Enum):
    SSG = "ssg"
    DYNAMIC = "dynamic"
    LAZY_NAMESPACE = "lazy_namespace"
    FULL_BUNDLE = "full_bundle"


@dataclass
class I18nConfig:
    target_locales: list[str]
    default_locale: str
    rtl_locales: list[str] = field(default_factory=list)
    compliance_jurisdictions: list[str] = field(default_factory=list)
    fallback_mode: FallbackMode = FallbackMode.DEFAULT_LOCALE
    translation_scope: TranslationScope = TranslationScope.FULL
    locale_switcher_required: bool = True
    routing_strategy: RoutingStrategy = RoutingStrategy.PREFIX
    locale_prefix: LocalePrefixMode = LocalePrefixMode.AS_NEEDED
    load_strategy: LoadStrategy = LoadStrategy.SSG
    split_namespaces: list[str] = field(default_factory=list)
    preload_locales: list[str] = field(default_factory=list)

    @classmethod
    def from_requirements(cls, requirements: dict[str, Any]) -> "I18nConfig":
        target_locales = requirements.get("target_locales", ["en"])
        default_locale = requirements.get("default_locale", target_locales[0])
        rtl_locales = requirements.get("rtl_locales", [])
        compliance = requirements.get("compliance_jurisdictions", [])

        fallback_map = {
            "default_locale": FallbackMode.DEFAULT_LOCALE,
            "language_only": FallbackMode.LANGUAGE_ONLY,
            "none": FallbackMode.NONE,
        }
        scope_map = {
            "full": TranslationScope.FULL,
            "ui_only": TranslationScope.UI_ONLY,
            "keys_only": TranslationScope.KEYS_ONLY,
            "none": TranslationScope.NONE,
        }
        strategy_map = {
            "prefix": RoutingStrategy.PREFIX,
            "domain": RoutingStrategy.DOMAIN,
            "cookie": RoutingStrategy.COOKIE,
            "subpath": RoutingStrategy.SUBPATH,
        }
        prefix_map = {
            "always": LocalePrefixMode.ALWAYS,
            "as-needed": LocalePrefixMode.AS_NEEDED,
        }
        load_map = {
            "ssg": LoadStrategy.SSG,
            "dynamic": LoadStrategy.DYNAMIC,
            "lazy_namespace": LoadStrategy.LAZY_NAMESPACE,
            "full_bundle": LoadStrategy.FULL_BUNDLE,
        }

        return cls(
            target_locales=target_locales,
            default_locale=default_locale,
            rtl_locales=rtl_locales,
            compliance_jurisdictions=compliance,
            fallback_mode=fallback_map.get(
                requirements.get("fallback_mode", "default_locale"), FallbackMode.DEFAULT_LOCALE
            ),
            translation_scope=scope_map.get(
                requirements.get("translation_scope", "full"), TranslationScope.FULL
            ),
            locale_switcher_required=requirements.get("locale_switcher_required", True),
            routing_strategy=strategy_map.get(
                requirements.get("routing_strategy", "prefix"), RoutingStrategy.PREFIX
            ),
            locale_prefix=prefix_map.get(
                requirements.get("locale_prefix", "as-needed"), LocalePrefixMode.AS_NEEDED
            ),
            load_strategy=load_map.get(
                requirements.get("load_strategy", "ssg"), LoadStrategy.SSG
            ),
            split_namespaces=requirements.get("split_namespaces", []),
            preload_locales=requirements.get("preload_locales", []),
        )

    def to_next_intl_config(self) -> dict[str, Any]:
        return {
            "locales": self.target_locales,
            "defaultLocale": self.default_locale,
            "localePrefix": self.locale_prefix.value,
        }

    def validate(self) -> list[str]:
        errors: list[str] = []
        if not self.target_locales:
            errors.append("target_locales must not be empty")
        if self.default_locale not in self.target_locales:
            errors.append("default_locale must be in target_locales")
        for locale in self.target_locales:
            if not locale or not isinstance(locale, str):
                errors.append(f"invalid locale: {locale!r}")
        return errors
