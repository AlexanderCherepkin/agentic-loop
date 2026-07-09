"""Tests for runtime/cms_queries engine and config."""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from runtime.cms_queries.config import CmsSource, CmsSourceId
from runtime.cms_queries.engine import CmsQueriesEngine


def _make_project(tmp_path: Path) -> Path:
    (tmp_path / "package.json").write_text('{"name":"demo"}', encoding="utf-8")
    return tmp_path


def test_local_markdown_writes_pages_and_markdown_loader(tmp_path):
    root = _make_project(tmp_path)
    source = CmsSource(source_id=CmsSourceId.local_markdown)
    engine = CmsQueriesEngine(root, source)
    result = engine.run()

    assert not result.errors
    assert "local_markdown" in result.sources_installed
    assert any("src/lib/cms.ts" in f for f in result.files_written)
    assert any("src/lib/cms/localMarkdown.ts" in f for f in result.files_written)
    assert any("src/lib/cms/staticFallback.ts" in f for f in result.files_written)
    assert any("src/app/blog/page.tsx" in f for f in result.files_written)
    assert any("src/app/blog/[slug]/page.tsx" in f for f in result.files_written)
    assert any("src/app/portfolio/page.tsx" in f for f in result.files_written)
    assert any("src/app/portfolio/[slug]/page.tsx" in f for f in result.files_written)
    assert any("src/app/cases/page.tsx" in f for f in result.files_written)
    assert any("src/app/cases/[slug]/page.tsx" in f for f in result.files_written)

    cms_lib = (root / "src" / "lib" / "cms.ts").read_text(encoding="utf-8")
    assert "getLocalEntries" in cms_lib
    assert "getStaticFallback" in cms_lib
    assert "process.env.CMS_SOURCE_ID" in cms_lib

    local_md = (root / "src" / "lib" / "cms" / "localMarkdown.ts").read_text(encoding="utf-8")
    assert "content" in local_md
    assert "parseFrontmatter" in local_md
    assert "fs.readdir" in local_md



def test_notion_injects_dependency_and_env_example(tmp_path):
    root = _make_project(tmp_path)
    source = CmsSource(source_id=CmsSourceId.notion)
    engine = CmsQueriesEngine(root, source)
    result = engine.run()

    assert not result.errors
    assert "notion" in result.sources_installed
    assert any("package.json" in f for f in result.files_modified)

    package = json.loads((root / "package.json").read_text(encoding="utf-8"))
    assert package["dependencies"]["@notionhq/client"]

    env_example = (root / ".env.local.example").read_text(encoding="utf-8")
    assert "NOTION_TOKEN" in env_example
    assert "NOTION_DATABASE_ID" in env_example



def test_existing_cms_lib_not_overwritten(tmp_path):
    root = _make_project(tmp_path)
    (root / "src" / "lib").mkdir(parents=True, exist_ok=True)
    existing = "export const cms = 'existing';\n"
    (root / "src" / "lib" / "cms.ts").write_text(existing, encoding="utf-8")

    source = CmsSource(source_id=CmsSourceId.local_markdown)
    engine = CmsQueriesEngine(root, source)
    result = engine.run()

    assert not result.errors
    assert not any("src/lib/cms.ts" in f for f in result.files_written)
    assert any("src/lib/cms.ts already exists" in n for n in result.notes)
    assert (root / "src" / "lib" / "cms.ts").read_text(encoding="utf-8") == existing



def test_unsupported_source_records_validation_error():
    source = CmsSource(source_id="unknown_provider")
    errors = source.validate()
    assert any("unsupported cms source" in e for e in errors)
