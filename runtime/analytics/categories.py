from __future__ import annotations

from enum import Enum


class ConsentCategory(Enum):
    NECESSARY = "necessary"
    ANALYTICS = "analytics"
    MARKETING = "marketing"
    FUNCTIONAL = "functional"


DEFAULT_DENY_CATEGORIES = {
    ConsentCategory.ANALYTICS,
    ConsentCategory.MARKETING,
    ConsentCategory.FUNCTIONAL,
}


JURISDICTION_DEFAULTS = {
    "GDPR": {"default_deny": True, "categories": [ConsentCategory.ANALYTICS, ConsentCategory.MARKETING]},
    "ePrivacy": {"default_deny": True, "categories": [ConsentCategory.ANALYTICS, ConsentCategory.MARKETING]},
    "152-FZ": {"default_deny": True, "categories": [ConsentCategory.ANALYTICS, ConsentCategory.MARKETING]},
    "PIPL": {"default_deny": True, "categories": [ConsentCategory.ANALYTICS, ConsentCategory.MARKETING]},
    "CCPA": {"default_deny": False, "categories": [ConsentCategory.MARKETING], "notice_required": True},
}


def category_for_provider(provider_id: str) -> ConsentCategory:
    mapping = {
        "ga4": ConsentCategory.ANALYTICS,
        "yandex": ConsentCategory.ANALYTICS,
        "plausible": ConsentCategory.ANALYTICS,
        "posthog": ConsentCategory.ANALYTICS,
        "mixpanel": ConsentCategory.ANALYTICS,
    }
    return mapping.get(provider_id.lower(), ConsentCategory.ANALYTICS)


def requires_consent(provider_id: str, jurisdictions: list[str]) -> bool:
    if category_for_provider(provider_id) == ConsentCategory.NECESSARY:
        return False
    for jur in jurisdictions:
        if jur in JURISDICTION_DEFAULTS and JURISDICTION_DEFAULTS[jur].get("default_deny"):
            return True
    return False
