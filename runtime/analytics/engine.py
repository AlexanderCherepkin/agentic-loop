from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from runtime.safety.file_system_guard import safe_write_file

from .categories import ConsentCategory, category_for_provider, requires_consent
from .csp_helper import build_csp_directives
from .script_injector import SnippetSpec, build_privacy_policy_stub, build_script_tags, build_snippet


@dataclass
class ProviderConfig:
    provider_id: str
    enabled: bool = True
    tracking_id: str | None = None
    consent_category: ConsentCategory = ConsentCategory.ANALYTICS
    load_strategy: str = "consent"
    ip_anonymization: bool = True
    events: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ProviderConfig":
        cat = data.get("consent_category", "analytics")
        try:
            consent_category = ConsentCategory(cat)
        except ValueError:
            consent_category = category_for_provider(data.get("provider_id", ""))
        return cls(
            provider_id=data.get("provider_id", data.get("provider", "")),
            enabled=data.get("enabled", True),
            tracking_id=data.get("tracking_id"),
            consent_category=consent_category,
            load_strategy=data.get("load_strategy", "consent"),
            ip_anonymization=data.get("ip_anonymization", True),
            events=data.get("events", []),
        )


@dataclass
class AnalyticsIntegrationResult:
    files_written: list[str] = field(default_factory=list)
    files_modified: list[str] = field(default_factory=list)
    providers_installed: list[str] = field(default_factory=list)
    errors: list[dict[str, Any]] = field(default_factory=list)


class AnalyticsIntegrationEngine:
    def __init__(
        self,
        target_dir: Path | str,
        providers: list[ProviderConfig],
        consent_required: bool = True,
        jurisdictions: list[str] | None = None,
    ):
        self.target_dir = Path(target_dir)
        self.providers = providers
        self.consent_required = consent_required
        self.jurisdictions = jurisdictions or []
        self.result = AnalyticsIntegrationResult()

    def run(
        self,
        consent_policies: dict[str, dict[str, Any]] | None = None,
        event_registry: list[dict[str, Any]] | None = None,
    ) -> AnalyticsIntegrationResult:
        self._validate_project()
        self._write_consent_store()
        if consent_policies:
            self._write_cookie_consent(consent_policies)
        self._write_analytics_lib()
        self._write_provider_modules()
        self._write_script_snippets()
        self._write_privacy_policy()
        if event_registry:
            self._write_event_types(event_registry)
        self._update_next_config()
        self.result.providers_installed = [p.provider_id for p in self.providers if p.enabled]
        return self.result

    def _write_file(self, rel_path: str, content: str) -> None:
        try:
            safe_write_file(self.target_dir, rel_path, content)
            self.result.files_written.append(rel_path)
        except Exception as exc:
            self.result.errors.append({"file": rel_path, "reason": str(exc)})

    def _validate_project(self) -> None:
        package = self.target_dir / "package.json"
        if not package.exists():
            self.result.errors.append({"file": "package.json", "reason": "missing package.json; target_dir is not a Next.js project"})

    def _write_consent_store(self) -> None:
        categories = ["necessary", "analytics", "marketing", "functional"]
        defaults = {cat: cat == "necessary" for cat in categories}
        code = f"""'use client';

import {{ createContext, useContext, useEffect, useState }} from 'react';

export type ConsentCategory = {json.dumps(categories)}[number];

export type ConsentState = Record<ConsentCategory, boolean>;

export const defaultConsent: ConsentState = {json.dumps(defaults)};

const STORAGE_KEY = 'cookie-consent';

const ConsentContext = createContext<{{
  consent: ConsentState;
  setConsent: (state: ConsentState) => void;
  hasDecided: boolean;
}} | null>(null);

export function ConsentProvider({{ children }}: {{ children: React.ReactNode }}) {{
  const [consent, setStored] = useState<ConsentState>(defaultConsent);
  const [hasDecided, setHasDecided] = useState(false);

  useEffect(() => {{
    try {{
      const raw = localStorage.getItem(STORAGE_KEY);
      if (raw) {{
        setStored({{ ...defaultConsent, ...JSON.parse(raw) }});
        setHasDecided(true);
      }}
    }} catch {{}}
  }}, []);

  const setConsent = (state: ConsentState) => {{
    setStored(state);
    setHasDecided(true);
    try {{
      localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
    }} catch {{}}
    window.dispatchEvent(new CustomEvent('consent-change', {{ detail: state }}));
  }};

  return (
    <ConsentContext.Provider value={{ {{ consent, setConsent, hasDecided }} }}>
      {{children}}
    </ConsentContext.Provider>
  );
}}

export function useConsent() {{
  const ctx = useContext(ConsentContext);
  if (!ctx) throw new Error('useConsent must be used inside ConsentProvider');
  return ctx;
}}

export function hasConsent(category: ConsentCategory) {{
  if (typeof window === 'undefined') return category === 'necessary';
  try {{
    const raw = localStorage.getItem(STORAGE_KEY);
    const state = raw ? {{ ...defaultConsent, ...JSON.parse(raw) }} : defaultConsent;
    return state[category] ?? defaultConsent[category];
  }} catch {{
    return defaultConsent[category];
  }}
}}
"""
        self._write_file("src/lib/consent-store.ts", code)

    def _write_cookie_consent(self, policies: dict[str, dict[str, Any]]) -> None:
        policy = policies.get("en", next(iter(policies.values()), {}))
        code = f"""'use client';

import {{ useState }} from 'react';
import {{ useTranslations }} from 'next-intl';
import {{ useConsent, ConsentCategory }} from '@/lib/consent-store';

const CATEGORIES: ConsentCategory[] = ['necessary', 'analytics', 'marketing', 'functional'];

export default function CookieConsent() {{
  const {{ consent, setConsent, hasDecided }} = useConsent();
  const [open, setOpen] = useState(false);
  const t = useTranslations('cookieConsent');

  if (hasDecided && !open) return null;

  const acceptAll = () => {{
    const all = Object.fromEntries(CATEGORIES.map((c) => [c, true])) as Record<ConsentCategory, boolean>;
    setConsent(all);
  }};

  const rejectNonNecessary = () => {{
    setConsent({{
      necessary: true,
      analytics: false,
      marketing: false,
      functional: false,
    }});
  }};

  return (
    <div role="dialog" aria-live="polite" className="fixed bottom-0 left-0 right-0 z-50 border-t bg-white p-4 shadow-lg dark:bg-slate-900">
      <div className="mx-auto flex max-w-6xl flex-col gap-4 md:flex-row md:items-center md:justify-between">
        <div className="text-sm">
          <p className="font-semibold">{policy.get('banner_title', 'Cookie consent')}</p>
          <p>{policy.get('banner_description', 'We use cookies to improve your experience.')}</p>
        </div>
        <div className="flex gap-2">
          <button type="button" onClick={{rejectNonNecessary}} className="rounded border px-3 py-2 text-sm">
            {policy.get('reject_label', 'Reject')}
          </button>
          <button type="button" onClick={{acceptAll}} className="rounded bg-slate-900 px-3 py-2 text-sm text-white">
            {policy.get('accept_label', 'Accept')}
          </button>
        </div>
      </div>
    </div>
  );
}}
"""
        self._write_file("src/components/CookieConsent.tsx", code)

    def _write_analytics_lib(self) -> None:
        provider_imports = "\n".join(
            f"import * as {p.provider_id} from './analytics/{p.provider_id}';"
            for p in self.providers if p.enabled
        )
        provider_list = json.dumps([p.provider_id for p in self.providers if p.enabled])
        code = f"""'use client';

import {{ hasConsent }} from './consent-store';
{provider_imports}

const enabledProviders = {provider_list};

export type AnalyticsEvent = {{
  name: string;
  properties?: Record<string, unknown>;
}};

export function trackEvent(event: AnalyticsEvent) {{
  for (const providerId of enabledProviders) {{
    const mod = ({{ ga4, yandex, plausible, posthog, mixpanel }} as any)[providerId];
    if (mod && mod.track && hasConsent(mod.category || 'analytics')) {{
      try {{
        mod.track(event.name, event.properties);
      }} catch {{}}
    }}
  }}
}}

export function pageView(path: string) {{
  for (const providerId of enabledProviders) {{
    const mod = ({{ ga4, yandex, plausible, posthog, mixpanel }} as any)[providerId];
    if (mod && mod.pageView && hasConsent(mod.category || 'analytics')) {{
      try {{
        mod.pageView(path);
      }} catch {{}}
    }}
  }}
}}

export function consentAwareLoad(category: string) {{
  return hasConsent(category as any);
}}
"""
        self._write_file("src/lib/analytics.ts", code)

    def _write_provider_modules(self) -> None:
        templates = {
            "ga4": """'use client';

export const category = 'analytics';

export function pageView(path: string) {
  if (typeof window === 'undefined' || !(window as any).gtag) return;
  (window as any).gtag('config', '[TRACKING_ID]', { page_path: path, anonymize_ip: true });
}

export function track(name: string, properties?: Record<string, unknown>) {
  if (typeof window === 'undefined' || !(window as any).gtag) return;
  (window as any).gtag('event', name, properties);
}
""",
            "yandex": """'use client';

export const category = 'analytics';

export function pageView(path: string) {
  if (typeof window === 'undefined' || !(window as any).ym) return;
  (window as any).ym([TRACKING_ID], 'hit', path);
}

export function track(name: string, properties?: Record<string, unknown>) {
  if (typeof window === 'undefined' || !(window as any).ym) return;
  (window as any).ym([TRACKING_ID], 'reachGoal', name, properties);
}
""",
            "plausible": """'use client';

export const category = 'analytics';

export function pageView(path: string) {
  if (typeof window === 'undefined' || !(window as any).plausible) return;
  (window as any).plausible('pageview', { u: path });
}

export function track(name: string, properties?: Record<string, unknown>) {
  if (typeof window === 'undefined' || !(window as any).plausible) return;
  (window as any).plausible(name, { props: properties });
}
""",
            "posthog": """'use client';

export const category = 'analytics';

export function pageView(path: string) {
  if (typeof window === 'undefined' || !(window as any).posthog) return;
  (window as any).posthog.capture('$pageview', { $current_url: path });
}

export function track(name: string, properties?: Record<string, unknown>) {
  if (typeof window === 'undefined' || !(window as any).posthog) return;
  (window as any).posthog.capture(name, properties);
}
""",
            "mixpanel": """'use client';

export const category = 'analytics';

export function pageView(path: string) {
  if (typeof window === 'undefined' || !(window as any).mixpanel) return;
  (window as any).mixpanel.track('Page View', { path });
}

export function track(name: string, properties?: Record<string, unknown>) {
  if (typeof window === 'undefined' || !(window as any).mixpanel) return;
  (window as any).mixpanel.track(name, properties);
}
""",
        }
        for provider in self.providers:
            if not provider.enabled:
                continue
            template = templates.get(provider.provider_id, templates["ga4"])
            if provider.tracking_id:
                template = template.replace("[TRACKING_ID]", json.dumps(provider.tracking_id))
            self._write_file(f"src/lib/analytics/{provider.provider_id}.ts", template)

    def _write_script_snippets(self) -> None:
        specs = [
            SnippetSpec(
                provider_id=p.provider_id,
                tracking_id=p.tracking_id or "",
                consent_category=p.consent_category.value,
                load_strategy=p.load_strategy,
            )
            for p in self.providers
            if p.enabled and p.provider_id.lower() in {"gtm", "ga4", "plausible"}
        ]
        tags = build_script_tags(specs)
        for provider_id, tag_html in tags.items():
            code = f"'use client';\n\nimport Script from 'next/script';\n\nexport default function {provider_id.title()}Loader() {{\n  return (\n{tag_html}\n  );\n}}\n"
            self._write_file(f"src/components/analytics/{provider_id}Loader.tsx", code)

    def _write_privacy_policy(self) -> None:
        enabled = [p.provider_id for p in self.providers if p.enabled]
        stub = build_privacy_policy_stub(
            jurisdictions=self.jurisdictions,
            providers=enabled,
            contact_email="privacy@example.com",
        )
        self._write_file("src/app/privacy/page.mdx", stub)

    def _write_event_types(self, event_registry: list[dict[str, Any]]) -> None:
        event_names = sorted({e.get("name", "event") for e in event_registry})
        code = "export type KnownAnalyticsEvent =\n"
        code += "\n".join(f"  | '{name}'" for name in event_names) + ";\n"
        self._write_file("src/lib/analytics/events.ts", code)

    def _update_next_config(self) -> None:
        config_path = self.target_dir / "next.config.js"
        if not config_path.exists():
            return
        try:
            enabled = [p.provider_id for p in self.providers if p.enabled]
            directives = build_csp_directives(enabled)
            content = config_path.read_text(encoding="utf-8")
            marker = "// analytics-csp-start"
            end_marker = "// analytics-csp-end"
            csp_block = f"""
{marker}
  async headers() {{
    return [
      {{
        source: '/:path*',
        headers: [
          {{
            key: 'Content-Security-Policy',
            value: "default-src 'self'; script-src 'self' 'unsafe-eval' 'unsafe-inline' {(' '.join(directives.get('script-src', [])))}; connect-src 'self' {(' '.join(directives.get('connect-src', [])))}; img-src 'self' data: {(' '.join(directives.get('img-src', [])))};",
          }},
        ],
      }},
    ];
  }},
{end_marker}
"""
            if marker in content:
                content = re.sub(
                    rf"{re.escape(marker)}.*?{re.escape(end_marker)}",
                    csp_block,
                    content,
                    flags=re.DOTALL,
                )
            else:
                content = content.rstrip() + "\n" + csp_block + "\n"
            config_path.write_text(content, encoding="utf-8")
            self.result.files_modified.append(str(config_path))
        except Exception as exc:
            self.result.errors.append({"file": "next.config.js", "reason": str(exc)})
