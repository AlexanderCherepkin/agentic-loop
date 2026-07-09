from __future__ import annotations


_PROVIDER_CSP = {
    "ga4": {
        "script-src": ["https://www.googletagmanager.com", "https://www.google-analytics.com"],
        "connect-src": ["https://www.google-analytics.com", "https://region1.google-analytics.com"],
        "img-src": ["https://www.google-analytics.com"],
    },
    "yandex": {
        "script-src": ["https://mc.yandex.ru", "https://yastatic.net"],
        "connect-src": ["https://mc.yandex.ru"],
        "img-src": ["https://mc.yandex.ru"],
    },
    "plausible": {
        "script-src": ["https://plausible.io", "https://*.plausible.io"],
        "connect-src": ["https://plausible.io", "https://*.plausible.io"],
        "img-src": [],
    },
    "posthog": {
        "script-src": ["https://*.posthog.com"],
        "connect-src": ["https://*.posthog.com"],
        "img-src": [],
    },
    "mixpanel": {
        "script-src": ["https://cdn.mxpnl.com"],
        "connect-src": ["https://*.mixpanel.com"],
        "img-src": [],
    },
}


def provider_csp_domains(provider_id: str) -> dict[str, list[str]]:
    return _PROVIDER_CSP.get(provider_id.lower(), {
        "script-src": [],
        "connect-src": [],
        "img-src": [],
    })


def build_csp_directives(enabled_providers: list[str]) -> dict[str, list[str]]:
    directives: dict[str, list[str]] = {
        "script-src": [],
        "connect-src": [],
        "img-src": [],
    }
    for provider in enabled_providers:
        for key, domains in provider_csp_domains(provider).items():
            directives.setdefault(key, [])
            for domain in domains:
                if domain not in directives[key]:
                    directives[key].append(domain)
    return directives
