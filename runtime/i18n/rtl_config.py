from __future__ import annotations


RTL_LOCALES = {
    "ar",  # Arabic
    "he",  # Hebrew
    "fa",  # Persian/Farsi
    "ur",  # Urdu
    "ks",  # Kashmiri
    "ps",  # Pashto
    "yi",  # Yiddish
    "sd",  # Sindhi
}


def is_rtl(locale: str) -> bool:
    """Return True if the locale (or its language base) is right-to-left."""
    if not locale:
        return False
    base = locale.split("-")[0].split("_")[0].lower()
    return base in RTL_LOCALES
