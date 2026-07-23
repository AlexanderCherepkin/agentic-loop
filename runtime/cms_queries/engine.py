from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from runtime.safety.file_system_guard import safe_write_file

from .config import CmsSource, CmsSourceId


@dataclass
class CmsQueriesResult:
    files_written: list[str] = field(default_factory=list)
    files_modified: list[str] = field(default_factory=list)
    sources_installed: list[str] = field(default_factory=list)
    errors: list[dict[str, Any]] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


_DEPENDENCIES: dict[str, tuple[str, str]] = {
    "notion": ("@notionhq/client", "^2.2.15"),
    "contentful": ("contentful", "^10.6.0"),
    "prisma": ("@prisma/client", "^5.0.0"),
    "airtable": ("airtable", "^0.12.2"),
    "google_sheets": ("googleapis", "^140.0.0"),
}

_ENV_EXAMPLES: dict[str, list[str]] = {
    "local_markdown": ["# No external secrets required for local_markdown source"],
    "notion": ["NOTION_TOKEN=", "NOTION_DATABASE_ID="],
    "contentful": ["CONTENTFUL_SPACE_ID=", "CONTENTFUL_ACCESS_TOKEN=", "CONTENTFUL_ENVIRONMENT=master"],
    "strapi": ["STRAPI_API_URL=", "STRAPI_API_TOKEN="],
    "prisma": ["DATABASE_URL="],
    "airtable": ["AIRTABLE_API_KEY=", "AIRTABLE_BASE_ID=", "AIRTABLE_TABLE_NAME="],
    "google_sheets": ["GOOGLE_SHEETS_API_KEY=", "GOOGLE_SHEETS_DOC_ID=", "GOOGLE_SHEETS_SHEET_NAME="],
    "cms_api": ["CMS_API_URL=", "CMS_API_KEY="],
}


class CmsQueriesEngine:
    def __init__(self, target_dir: Path | str, source: CmsSource):
        self.target_dir = Path(target_dir)
        self.source = source
        self.result = CmsQueriesResult()
        self.source_id_value = source.source_id.value if isinstance(source.source_id, CmsSourceId) else source.source_id

    def run(self) -> CmsQueriesResult:
        validation_errors = self.source.validate()
        if validation_errors:
            for err in validation_errors:
                self.result.errors.append({"file": "", "reason": err})
            return self.result

        self._validate_project()
        if self.result.errors:
            return self.result

        if not self.source.enabled:
            self.result.notes.append(f"CMS source {self.source_id_value} is disabled; using static fallback")

        self._ensure_package_dep()
        self._write_cms_lib()
        self._write_local_markdown_loader()
        self._write_static_fallback()
        self._write_card_components()
        self._write_listing_pages()
        self._write_detail_pages()
        self._write_env_example()

        if self.source.enabled:
            self.result.sources_installed.append(self.source_id_value)
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

    def _ensure_package_dep(self) -> None:
        package_path = self.target_dir / "package.json"
        if not package_path.exists():
            return
        dep = _DEPENDENCIES.get(self.source_id_value)
        if not dep:
            return
        if not self.source.enabled:
            return
        try:
            data = json.loads(package_path.read_text(encoding="utf-8"))
            deps = data.setdefault("dependencies", {})
            name, version = dep
            if name not in deps:
                deps[name] = version
                package_path.write_text(_stable_json(data), encoding="utf-8")
                self.result.files_modified.append("package.json")
        except Exception as exc:
            self.result.errors.append({"file": "package.json", "reason": str(exc)})

    def _write_cms_lib(self) -> None:
        cms_path = self.target_dir / "src" / "lib" / "cms.ts"
        if cms_path.exists():
            self.result.notes.append("src/lib/cms.ts already exists; cms library not overwritten")
            return
        self._write_file("src/lib/cms.ts", _CMS_LIB_TS)

    def _write_local_markdown_loader(self) -> None:
        self._write_file("src/lib/cms/localMarkdown.ts", _LOCAL_MARKDOWN_TS)

    def _write_static_fallback(self) -> None:
        self._write_file("src/lib/cms/staticFallback.ts", _STATIC_FALLBACK_TS)

    def _write_card_components(self) -> None:
        self._write_file("src/components/cms/PostCard.tsx", _POST_CARD_TSX)
        self._write_file("src/components/cms/ProjectCard.tsx", _PROJECT_CARD_TSX)
        self._write_file("src/components/cms/CaseStudyCard.tsx", _CASE_STUDY_CARD_TSX)

    def _write_listing_pages(self) -> None:
        self._write_file("src/app/blog/page.tsx", _BLOG_LIST_TSX)
        self._write_file("src/app/portfolio/page.tsx", _PORTFOLIO_LIST_TSX)
        self._write_file("src/app/cases/page.tsx", _CASES_LIST_TSX)

    def _write_detail_pages(self) -> None:
        self._write_file("src/app/blog/[slug]/page.tsx", _BLOG_DETAIL_TSX)
        self._write_file("src/app/portfolio/[slug]/page.tsx", _PORTFOLIO_DETAIL_TSX)
        self._write_file("src/app/cases/[slug]/page.tsx", _CASES_DETAIL_TSX)

    def _write_env_example(self) -> None:
        lines = _ENV_EXAMPLES.get(self.source_id_value, ["# Add CMS connection variables here"])
        self._write_file(".env.local.example", "\n".join(lines) + "\n")


_CMS_LIB_TS = """import { getLocalEntries, getLocalEntry } from './cms/localMarkdown';
import { getStaticFallback } from './cms/staticFallback';

export type CmsItem = {
  slug: string;
  title: string;
  excerpt?: string;
  coverImage?: string;
  publishedAt?: string;
  content?: string;
  tags?: string[];
  [key: string]: unknown;
};

export type CmsOptions = { limit?: number; tag?: string };

export async function getEntries(entityType: string, options?: CmsOptions): Promise<CmsItem[]> {
  const source = process.env.CMS_SOURCE_ID || 'local_markdown';
  switch (source) {
    case 'local_markdown':
      return getLocalEntries(entityType, options);
    case 'notion':
      // TODO: wire Notion client using NOTION_TOKEN / NOTION_DATABASE_ID
      return getStaticFallback(entityType, options);
    case 'contentful':
      // TODO: wire Contentful client using CONTENTFUL_SPACE_ID / CONTENTFUL_ACCESS_TOKEN
      return getStaticFallback(entityType, options);
    case 'strapi':
      // TODO: wire Strapi REST API using STRAPI_API_URL / STRAPI_API_TOKEN
      return getStaticFallback(entityType, options);
    case 'prisma':
      // TODO: wire Prisma query using DATABASE_URL
      return getStaticFallback(entityType, options);
    case 'airtable':
      // TODO: wire Airtable API using AIRTABLE_API_KEY / AIRTABLE_BASE_ID
      return getStaticFallback(entityType, options);
    case 'google_sheets':
      // TODO: wire Google Sheets API using GOOGLE_SHEETS_API_KEY / GOOGLE_SHEETS_DOC_ID
      return getStaticFallback(entityType, options);
    case 'cms_api':
      // TODO: wire generic CMS API using CMS_API_URL / CMS_API_KEY
      return getStaticFallback(entityType, options);
    default:
      return getStaticFallback(entityType, options);
  }
}

export async function getEntry(entityType: string, slug: string): Promise<CmsItem | null> {
  const items = await getEntries(entityType);
  return items.find((item) => item.slug === slug) || null;
}
"""

_LOCAL_MARKDOWN_TS = """import fs from 'fs/promises';
import path from 'path';
import { CmsItem, CmsOptions } from '../cms';

function parseFrontmatter(raw: string): Record<string, unknown> {
  const match = raw.match(/^---\\n([\\s\\S]*?)\\n---\\n([\\s\\S]*)$/);
  if (!match) return { content: raw.trim() };
  const front = match[1];
  const content = match[2].trim();
  const meta: Record<string, unknown> = { content };
  for (const line of front.split('\\n')) {
    const idx = line.indexOf(':');
    if (idx === -1) continue;
    const key = line.slice(0, idx).trim();
    let value: unknown = line.slice(idx + 1).trim();
    const str = String(value);
    if ((str.startsWith('[') && str.endsWith(']')) || (str.startsWith('{') && str.endsWith('}'))) {
      try { value = JSON.parse(str); } catch {}
    } else if (str === 'true') {
      value = true;
    } else if (str === 'false') {
      value = false;
    } else if (str.length >= 2 && ((str.startsWith('"') && str.endsWith('"')) || (str.startsWith("'") && str.endsWith("'")))) {
      value = str.slice(1, -1);
    }
    meta[key] = value;
  }
  return meta;
}

export async function getLocalEntries(entityType: string, options?: CmsOptions): Promise<CmsItem[]> {
  const dir = path.join(process.cwd(), 'content', entityType);
  let files: string[] = [];
  try {
    files = (await fs.readdir(dir)).filter((f) => f.endsWith('.md'));
  } catch {
    return [];
  }
  const items = await Promise.all(
    files.map(async (file) => {
      const slug = file.replace(/\\.md$/, '');
      const raw = await fs.readFile(path.join(dir, file), 'utf-8');
      const meta = parseFrontmatter(raw);
      return { slug, ...meta } as CmsItem;
    })
  );
  let result = items.sort((a, b) => (b.publishedAt || '').localeCompare(a.publishedAt || ''));
  if (options?.tag) {
    result = result.filter((item) => item.tags?.includes(options.tag));
  }
  if (options?.limit) {
    result = result.slice(0, options.limit);
  }
  return result;
}

export async function getLocalEntry(entityType: string, slug: string): Promise<CmsItem | null> {
  const items = await getLocalEntries(entityType);
  return items.find((item) => item.slug === slug) || null;
}
"""

_STATIC_FALLBACK_TS = """import { CmsItem, CmsOptions } from '../cms';

const FALLBACKS: Record<string, CmsItem[]> = {
  blog: [
    {
      slug: 'hello',
      title: 'Hello world',
      excerpt: 'This is a fallback blog post used when the CMS is offline or disabled.',
      tags: ['news'],
      publishedAt: '2026-01-01',
      content: 'Replace this with live content from your CMS.',
    },
  ],
  project: [
    {
      slug: 'sample-project',
      title: 'Sample project',
      excerpt: 'Fallback project card used when the CMS is offline or disabled.',
      tags: ['work'],
    },
  ],
  case_study: [
    {
      slug: 'sample-case',
      title: 'Sample case study',
      excerpt: 'Fallback case study used when the CMS is offline or disabled.',
      tags: ['case'],
    },
  ],
};

export async function getStaticFallback(entityType: string, options?: CmsOptions): Promise<CmsItem[]> {
  let items = FALLBACKS[entityType] || [];
  if (options?.tag) {
    items = items.filter((item) => item.tags?.includes(options.tag));
  }
  if (options?.limit) {
    items = items.slice(0, options.limit);
  }
  return items;
}
"""

_POST_CARD_TSX = """import Link from 'next/link';
import { CmsItem } from '@/lib/cms';

export default function PostCard({ item }: { item: CmsItem }) {
  return (
    <article className="flex flex-col gap-2 rounded border p-4">
      <h2 className="text-lg font-semibold">
        <Link href={`/blog/${item.slug}`}>{item.title}</Link>
      </h2>
      {item.excerpt && <p className="text-sm text-slate-600">{item.excerpt}</p>}
      {item.publishedAt && <time className="text-xs text-slate-500">{item.publishedAt}</time>}
    </article>
  );
}
"""

_PROJECT_CARD_TSX = """import Link from 'next/link';
import { CmsItem } from '@/lib/cms';

export default function ProjectCard({ item }: { item: CmsItem }) {
  return (
    <article className="flex flex-col gap-2 rounded border p-4">
      <h2 className="text-lg font-semibold">
        <Link href={`/portfolio/${item.slug}`}>{item.title}</Link>
      </h2>
      {item.excerpt && <p className="text-sm text-slate-600">{item.excerpt}</p>}
      {item.tags && item.tags.length > 0 && (
        <div className="flex flex-wrap gap-1">
          {item.tags.map((tag) => (
            <span key={tag} className="rounded bg-slate-100 px-2 py-1 text-xs">{tag}</span>
          ))}
        </div>
      )}
    </article>
  );
}
"""

_CASE_STUDY_CARD_TSX = """import Link from 'next/link';
import { CmsItem } from '@/lib/cms';

export default function CaseStudyCard({ item }: { item: CmsItem }) {
  return (
    <article className="flex flex-col gap-2 rounded border p-4">
      <h2 className="text-lg font-semibold">
        <Link href={`/cases/${item.slug}`}>{item.title}</Link>
      </h2>
      {item.excerpt && <p className="text-sm text-slate-600">{item.excerpt}</p>}
      {item.publishedAt && <time className="text-xs text-slate-500">{item.publishedAt}</time>}
    </article>
  );
}
"""

_BLOG_LIST_TSX = """import { getEntries } from '@/lib/cms';
import PostCard from '@/components/cms/PostCard';

export const revalidate = 60;

export default async function BlogPage() {
  const posts = await getEntries('blog');
  return (
    <main className="mx-auto max-w-4xl p-6">
      <h1 className="mb-6 text-2xl font-bold">Blog</h1>
      <div className="grid gap-4">
        {posts.map((post) => (
          <PostCard key={post.slug} item={post} />
        ))}
      </div>
    </main>
  );
}
"""

_PORTFOLIO_LIST_TSX = """import { getEntries } from '@/lib/cms';
import ProjectCard from '@/components/cms/ProjectCard';

export const revalidate = 60;

export default async function PortfolioPage() {
  const projects = await getEntries('project');
  return (
    <main className="mx-auto max-w-4xl p-6">
      <h1 className="mb-6 text-2xl font-bold">Portfolio</h1>
      <div className="grid gap-4">
        {projects.map((project) => (
          <ProjectCard key={project.slug} item={project} />
        ))}
      </div>
    </main>
  );
}
"""

_CASES_LIST_TSX = """import { getEntries } from '@/lib/cms';
import CaseStudyCard from '@/components/cms/CaseStudyCard';

export const revalidate = 60;

export default async function CasesPage() {
  const cases = await getEntries('case_study');
  return (
    <main className="mx-auto max-w-4xl p-6">
      <h1 className="mb-6 text-2xl font-bold">Case studies</h1>
      <div className="grid gap-4">
        {cases.map((item) => (
          <CaseStudyCard key={item.slug} item={item} />
        ))}
      </div>
    </main>
  );
}
"""

_BLOG_DETAIL_TSX = """import Link from 'next/link';
import { getEntry } from '@/lib/cms';
import { notFound } from 'next/navigation';

type Props = { params: { slug: string } };

export const revalidate = 60;

export default async function BlogPostPage({ params }: Props) {
  const post = await getEntry('blog', params.slug);
  if (!post) notFound();
  return (
    <main className="mx-auto max-w-3xl p-6">
      <Link href="/blog" className="text-sm text-slate-600">← Back to blog</Link>
      <h1 className="mt-4 text-3xl font-bold">{post.title}</h1>
      {post.publishedAt && <time className="text-sm text-slate-500">{post.publishedAt}</time>}
      {post.content && <div className="prose mt-6">{post.content}</div>}
    </main>
  );
}
"""

_PORTFOLIO_DETAIL_TSX = """import Link from 'next/link';
import { getEntry } from '@/lib/cms';
import { notFound } from 'next/navigation';

type Props = { params: { slug: string } };

export const revalidate = 60;

export default async function ProjectPage({ params }: Props) {
  const project = await getEntry('project', params.slug);
  if (!project) notFound();
  return (
    <main className="mx-auto max-w-3xl p-6">
      <Link href="/portfolio" className="text-sm text-slate-600">← Back to portfolio</Link>
      <h1 className="mt-4 text-3xl font-bold">{project.title}</h1>
      {project.tags && project.tags.length > 0 && (
        <div className="mt-2 flex flex-wrap gap-1">
          {project.tags.map((tag) => (
            <span key={tag} className="rounded bg-slate-100 px-2 py-1 text-xs">{tag}</span>
          ))}
        </div>
      )}
      {project.content && <div className="prose mt-6">{project.content}</div>}
    </main>
  );
}
"""

_CASES_DETAIL_TSX = """import Link from 'next/link';
import { getEntry } from '@/lib/cms';
import { notFound } from 'next/navigation';

type Props = { params: { slug: string } };

export const revalidate = 60;

export default async function CaseStudyPage({ params }: Props) {
  const item = await getEntry('case_study', params.slug);
  if (!item) notFound();
  return (
    <main className="mx-auto max-w-3xl p-6">
      <Link href="/cases" className="text-sm text-slate-600">← Back to case studies</Link>
      <h1 className="mt-4 text-3xl font-bold">{item.title}</h1>
      {item.publishedAt && <time className="text-sm text-slate-500">{item.publishedAt}</time>}
      {item.content && <div className="prose mt-6">{item.content}</div>}
    </main>
  );
}
"""


def _stable_json(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, indent=2, sort_keys=True)
