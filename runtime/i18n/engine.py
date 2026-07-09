from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .config import I18nConfig
from .key_namespace import KeyNamespace, normalize_namespace
from .rtl_config import is_rtl


@dataclass
class I18nIntegrationResult:
    files_written: list[str] = field(default_factory=list)
    files_modified: list[str] = field(default_factory=list)
    locales_installed: list[str] = field(default_factory=list)
    errors: list[dict[str, Any]] = field(default_factory=list)


def _stable_json(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, indent=2, sort_keys=True)


class I18nIntegrationEngine:
    def __init__(self, target_dir: Path | str, config: I18nConfig):
        self.target_dir = Path(target_dir)
        self.config = config
        self.result = I18nIntegrationResult()

    def run(
        self,
        dictionaries: dict[str, dict[str, Any]],
        key_registry: dict[str, Any] | None = None,
    ) -> I18nIntegrationResult:
        validation_errors = self.config.validate()
        if validation_errors:
            for err in validation_errors:
                self.result.errors.append({"file": "", "reason": err})
            return self.result

        self._ensure_package_dep()
        self._write_i18n_config()
        self._write_i18n_routing()
        self._write_i18n_request()
        self._write_middleware()
        self._write_messages(dictionaries)
        self._write_locale_layout()
        self._update_root_page()
        if key_registry:
            self._apply_component_rewrites(key_registry)
        self.result.locales_installed = list(self.config.target_locales)
        return self.result

    def _write_file(self, rel_path: str, content: str) -> None:
        full_path = self.target_dir / rel_path
        try:
            full_path.parent.mkdir(parents=True, exist_ok=True)
            full_path.write_text(content, encoding="utf-8")
            self.result.files_written.append(rel_path)
        except Exception as exc:
            self.result.errors.append({"file": rel_path, "reason": str(exc)})

    def _ensure_package_dep(self) -> None:
        package_path = self.target_dir / "package.json"
        if not package_path.exists():
            return
        try:
            data = json.loads(package_path.read_text(encoding="utf-8"))
            deps = data.setdefault("dependencies", {})
            if "next-intl" not in deps:
                deps["next-intl"] = "^3.0.0"
                package_path.write_text(_stable_json(data), encoding="utf-8")
                self.result.files_modified.append("package.json")
        except Exception as exc:
            self.result.errors.append({"file": "package.json", "reason": str(exc)})

    def _write_i18n_config(self) -> None:
        config = self.config.to_next_intl_config()
        code = f"""import {{ getRequestConfig }} from 'next-intl/server';

export const locales = {json.dumps(config['locales'])};
export const defaultLocale = {json.dumps(config['defaultLocale'])};

export default getRequestConfig(async ({{ requestLocale }}) => {{
  let locale = await requestLocale;
  if (!locale || !locales.includes(locale as string)) {{
    locale = defaultLocale;
  }}
  const messages = (await import(`../../messages/${{locale}}.json`)).default;
  return {{
    locale,
    messages,
  }};
}});
"""
        self._write_file("src/i18n.ts", code)

    def _write_i18n_routing(self) -> None:
        prefix = "as-needed" if self.config.locale_prefix.name == "AS_NEEDED" else "always"
        code = f"""import {{ defineRouting }} from 'next-intl/routing';

export const routing = defineRouting({{
  locales: {json.dumps(self.config.target_locales)},
  defaultLocale: {json.dumps(self.config.default_locale)},
  localePrefix: {json.dumps(prefix)},
}});
"""
        self._write_file("src/i18n/routing.ts", code)

    def _write_i18n_request(self) -> None:
        code = """import { getRequestConfig } from 'next-intl/server';
import { routing } from './routing';

export default getRequestConfig(async ({ requestLocale }) => {
  let locale = await requestLocale;
  if (!locale || !routing.locales.includes(locale as string)) {
    locale = routing.defaultLocale;
  }

  const messages = (await import(`../../messages/${locale}.json`)).default;

  return {
    locale,
    messages,
  };
});
"""
        self._write_file("src/i18n/request.ts", code)

    def _write_middleware(self) -> None:
        matcher = "/((?!api|_next|_vercel|.*\\..*).*)"
        code = f"""import createMiddleware from 'next-intl/middleware';
import {{ routing }} from './src/i18n/routing';

export default createMiddleware(routing);

export const config = {{
  matcher: [{json.dumps(matcher)}],
}};
"""
        self._write_file("middleware.ts", code)

    def _write_messages(self, dictionaries: dict[str, dict[str, Any]]) -> None:
        for locale in self.config.target_locales:
            data = dictionaries.get(locale, {})
            if not data and self.config.default_locale in dictionaries:
                # Fallback to default locale skeleton
                data = dictionaries[self.config.default_locale]
            self._write_file(f"messages/{locale}.json", _stable_json(data))

    def _write_locale_layout(self) -> None:
        rtl_logic = "isRtl(locale) ? 'rtl' : 'ltr'"
        code = f"""import {{ NextIntlClientProvider }} from 'next-intl';
import {{ getMessages }} from 'next-intl/server';
import {{ notFound }} from 'next/navigation';
import {{ routing }} from '@/i18n/routing';

function isRtl(locale: string) {{
  return {json.dumps(list(self.config.rtl_locales))}.includes(locale);
}}

export default async function LocaleLayout({{
  children,
  params: {{ locale }},
}}: {{
  children: React.ReactNode;
  params: {{ locale: string }};
}}) {{
  if (!routing.locales.includes(locale as any)) {{
    notFound();
  }}

  const messages = await getMessages();

  return (
    <html lang={{locale}} dir={{{rtl_logic}}}>
      <body>
        <NextIntlClientProvider messages={{messages}}>
          {{children}}
        </NextIntlClientProvider>
      </body>
    </html>
  );
}}
"""
        self._write_file("src/app/[locale]/layout.tsx", code)

    def _update_root_page(self) -> None:
        code = """import { redirect } from 'next/navigation';
import { routing } from '@/i18n/routing';

export default function RootPage() {
  redirect(`/${routing.defaultLocale}`);
}
"""
        self._write_file("src/app/page.tsx", code)

    def _apply_component_rewrites(self, key_registry: dict[str, Any]) -> None:
        replacements = key_registry.get("replacements", {})
        imports_to_add = key_registry.get("imports_to_add", {})
        for file_path, reps in replacements.items():
            full_path = self.target_dir / file_path
            if not full_path.exists():
                continue
            try:
                content = full_path.read_text(encoding="utf-8")
                # Sort replacements by start position descending to preserve offsets
                sorted_reps = sorted(reps, key=lambda r: r.get("start", 0), reverse=True)
                for rep in sorted_reps:
                    old = rep.get("old_text", "")
                    new = rep.get("new_code", old)
                    if old and old in content:
                        content = content.replace(old, new, 1)
                if imports_to_add.get(file_path):
                    import_block = "\n".join(imports_to_add[file_path])
                    # Insert after first import or at top
                    if "import" in content:
                        idx = content.find("\n", content.find("import"))
                        content = content[:idx] + "\n" + import_block + content[idx:]
                    else:
                        content = import_block + "\n" + content
                full_path.write_text(content, encoding="utf-8")
                self.result.files_modified.append(file_path)
            except Exception as exc:
                self.result.errors.append({"file": file_path, "reason": str(exc)})

    def build_key_registry(
        self,
        texts: list[dict[str, Any]],
        namespace: str = "ui",
    ) -> KeyNamespace:
        ns = KeyNamespace(namespace=normalize_namespace(namespace))
        collision_counter: dict[str, int] = {}
        for item in texts:
            ns.add_text(
                text=item.get("text", ""),
                section=item.get("section", "ui"),
                context=item.get("context", ""),
                figma_node_id=item.get("figma_node_id"),
                collision_counter=collision_counter,
            )
        return ns
