from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any


@dataclass
class SnippetSpec:
    provider_id: str
    tracking_id: str | None = None
    consent_category: str = "analytics"
    load_strategy: str = "consent"  # "consent" | "lazy" | "immediate"
    custom_domain: str | None = None
    extra_config: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider_id": self.provider_id,
            "tracking_id": self.tracking_id,
            "consent_category": self.consent_category,
            "load_strategy": self.load_strategy,
            "custom_domain": self.custom_domain,
            "extra_config": self.extra_config or {},
        }


_SNIPPETS: dict[str, str] = {
    "gtm": """'use strict';

(function(){
  if (typeof window === 'undefined') return;
  var dataLayer = window.dataLayer = window.dataLayer || [];
  dataLayer.push({ 'gtm.start': new Date().getTime(), event: 'gtm.js' });
  var f = document.getElementsByTagName('script')[0];
  var j = document.createElement('script');
  j.async = true;
  j.src = 'https://www.googletagmanager.com/gtm.js?id=[TRACKING_ID]';
  f.parentNode.insertBefore(j, f);
})();
""",
    "ga4": """'use strict';

(function(){
  if (typeof window === 'undefined') return;
  window.dataLayer = window.dataLayer || [];
  function gtag(){ window.dataLayer.push(arguments); }
  window.gtag = gtag;
  gtag('js', new Date());
  gtag('config', '[TRACKING_ID]', { anonymize_ip: true, send_page_view: false });
})();
""",
    "plausible": """'use strict';

(function(){
  if (typeof window === 'undefined') return;
  var d = document, s = d.createElement('script');
  s.async = true;
  s.defer = true;
  s.setAttribute('data-domain', '[TRACKING_ID]');
  s.src = 'https://[CUSTOM_DOMAIN]/js/script.js';
  d.head.appendChild(s);
})();
""",
}


def build_snippet(spec: SnippetSpec) -> str:
    """Return the rendered script tag or JS file content for a provider."""
    template = _SNIPPETS.get(spec.provider_id.lower())
    if not template:
        return ""
    code = template.replace("[TRACKING_ID]", spec.tracking_id or "")
    domain = spec.custom_domain or ("plausible.io" if spec.provider_id.lower() == "plausible" else "")
    code = code.replace("[CUSTOM_DOMAIN]", domain)
    if spec.extra_config:
        code = code.replace("/*[EXTRA_CONFIG]*/", json.dumps(spec.extra_config))
    return code


def build_script_tags(specs: list[SnippetSpec]) -> dict[str, str]:
    """Map provider_id to inline <script> HTML for Next.js Script components."""
    tags: dict[str, str] = {}
    for spec in specs:
        code = build_snippet(spec)
        if not code:
            continue
        if spec.load_strategy == "consent":
            tags[spec.provider_id] = (
                f"<Script id=\"{spec.provider_id}-loader\" strategy=\"lazyOnload\">\n"
                f"{{`{code}`}}\n"
                "</Script>"
            )
        elif spec.load_strategy == "lazy":
            tags[spec.provider_id] = (
                f"<Script id=\"{spec.provider_id}-loader\" strategy=\"lazyOnload\">\n"
                f"{{`{code}`}}\n"
                "</Script>"
            )
        else:
            tags[spec.provider_id] = (
                f"<Script id=\"{spec.provider_id}-loader\" strategy=\"afterInteractive\">\n"
                f"{{`{code}`}}\n"
                "</Script>"
            )
    return tags


def build_privacy_policy_stub(
    jurisdictions: list[str] | None = None,
    providers: list[str] | None = None,
    contact_email: str = "privacy@example.com",
) -> str:
    """Generate a minimal, locale-agnostic privacy policy page stub for generated sites."""
    jurs = set(jurisdictions or [])
    provs = providers or []
    sections = [
        "# Privacy Policy",
        "",
        "Last updated: [DATE]",
        "",
        "This Privacy Policy describes how we collect, use, and protect your personal information.",
        "",
        "## Information We Collect",
        "",
        "- Usage data (pages visited, time on site, device type).",
        "- Cookies and similar technologies set by analytics and marketing tools.",
        "- Information you voluntarily provide through forms.",
        "",
        "## How We Use Your Information",
        "",
        "- To understand and improve our website.",
        "- To provide and maintain our services.",
        "- To comply with legal obligations.",
        "",
    ]
    if provs:
        sections += [
            "## Analytics and Third-Party Tools",
            "",
        ]
        for prov in provs:
            sections.append(f"- {prov}")
        sections += ["", "These tools may place cookies or collect data as described in their own privacy policies.", ""]
    if jurs:
        sections += [
            "## Your Rights",
            "",
        ]
        if "GDPR" in jurs or "ePrivacy" in jurs or "152-FZ" in jurs or "PIPL" in jurs:
            sections += [
                "- You can withdraw consent to non-essential cookies at any time via the cookie banner.",
                "- You may request access, correction, or deletion of your personal data by contacting us.",
            ]
        if "CCPA" in jurs:
            sections += [
                "- California residents may opt out of the sale or sharing of personal information.",
                "- Do Not Sell or Share My Personal Information request: contact us below.",
            ]
        sections += [""]
    sections += [
        "## Contact Us",
        "",
        f"For privacy questions, contact: [{contact_email}](mailto:{contact_email})",
        "",
    ]
    return "\n".join(sections)
