"""Tests for the LLM Wiki engine."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from runtime.wiki.config import WikiConfig
from runtime.wiki.engine import WikiEngine, WikiPage


@pytest.fixture
def engine(tmp_path):
    return WikiEngine(
        WikiConfig(memory_root=tmp_path, wiki_dir="wiki", stale_days=90, deprecated_delete_days=180)
    )


class TestWikiConfig:
    def test_paths_resolve(self, tmp_path):
        config = WikiConfig(memory_root=tmp_path, wiki_dir="wiki")
        assert config.wiki_root == tmp_path / "wiki"
        assert config.index_path == tmp_path / "wiki" / "index.md"


class TestWikiQuery:
    def test_finds_relevant_page_by_name(self, engine, tmp_path):
        wiki_root = tmp_path / "wiki"
        wiki_root.mkdir(exist_ok=True)
        (wiki_root / "concept-auth.md").write_text(
            "---\nname: auth\ndescription: Authentication flow\n---\n\n# Auth\n\nLogin stuff.\n",
            encoding="utf-8",
        )
        result = engine.query("authentication flow")
        assert len(result.relevant_pages) >= 1
        assert result.relevant_pages[0].name == "auth"

    def test_no_match_returns_empty(self, engine):
        result = engine.query("something completely unrelated xyz")
        assert result.relevant_pages == []


class TestWikiIngest:
    def test_ingest_enriches_paths(self, engine, tmp_path):
        wiki_root = tmp_path / "wiki"
        wiki_root.mkdir(exist_ok=True)
        page = WikiPage(
            path=Path("auth.md"),
            name="auth",
            description="Auth flow",
            page_type="concept",
            content="# Auth",
        )
        result = engine.ingest([page])
        assert len(result.proposed_pages) == 1
        assert result.proposed_pages[0].path == wiki_root / "concept-auth.md"
        assert result.requires_approval is True

    def test_ingest_marks_existing_pages_as_draft(self, engine, tmp_path):
        wiki_root = tmp_path / "wiki"
        wiki_root.mkdir(exist_ok=True)
        (wiki_root / "concept-auth.md").write_text("x", encoding="utf-8")
        page = WikiPage(
            path=Path("auth.md"),
            name="auth",
            page_type="concept",
            content="c",
        )
        result = engine.ingest([page])
        assert result.proposed_pages[0].status == "draft"


class TestWikiLint:
    def test_clean_wiki_reports_no_issues(self, engine, tmp_path):
        wiki_root = tmp_path / "wiki"
        wiki_root.mkdir(exist_ok=True)
        (wiki_root / "index.md").write_text("# Wiki Index\n\n- [[auth]]\n", encoding="utf-8")
        (wiki_root / "concept-auth.md").write_text(
            "---\nname: auth\n---\n\n# Auth\n", encoding="utf-8"
        )
        result = engine.lint()
        assert result.issues == []
        assert "clean" in result.summary.lower()

    def test_detects_orphan_page(self, engine, tmp_path):
        wiki_root = tmp_path / "wiki"
        wiki_root.mkdir(exist_ok=True)
        (wiki_root / "index.md").write_text("# Wiki Index\n", encoding="utf-8")
        (wiki_root / "concept-auth.md").write_text(
            "---\nname: auth\n---\n\n# Auth\n", encoding="utf-8"
        )
        result = engine.lint()
        assert any(issue.get("name") == "auth" for issue in result.issues)

    def test_detects_broken_link(self, engine, tmp_path):
        wiki_root = tmp_path / "wiki"
        wiki_root.mkdir(exist_ok=True)
        (wiki_root / "concept-auth.md").write_text(
            "---\nname: auth\n---\n\n# Auth\n\nSee [[missing]].\n", encoding="utf-8"
        )
        result = engine.lint()
        assert any(issue.get("broken_link") == "missing" for issue in result.issues)

    def test_detects_duplicate_description(self, engine, tmp_path):
        wiki_root = tmp_path / "wiki"
        wiki_root.mkdir(exist_ok=True)
        (wiki_root / "concept-a.md").write_text(
            "---\nname: a\ndescription: same thing\n---\n\n# A\n", encoding="utf-8"
        )
        (wiki_root / "concept-b.md").write_text(
            "---\nname: b\ndescription: same thing\n---\n\n# B\n", encoding="utf-8"
        )
        result = engine.lint()
        assert any("overlap" in issue.get("reason", "") for issue in result.issues)

    def test_detects_deprecated_page_for_deletion(self, engine, tmp_path):
        wiki_root = tmp_path / "wiki"
        wiki_root.mkdir(exist_ok=True)
        old_date = "2020-01-01"
        (wiki_root / "concept-old.md").write_text(
            f"---\nname: old\nmetadata:\n  type: concept\n  status: deprecated\n  updated: {old_date}\n---\n\n# Old\n",
            encoding="utf-8",
        )
        result = engine.lint()
        assert any(issue.get("action") == "delete" for issue in result.issues)

    def test_lint_issue_cap(self, engine, tmp_path):
        config = WikiConfig(memory_root=tmp_path, max_lint_issues=2)
        engine = WikiEngine(config)
        wiki_root = tmp_path / "wiki"
        wiki_root.mkdir(exist_ok=True)
        # Create many orphan pages.
        for i in range(5):
            (wiki_root / f"concept-{i}.md").write_text(f"---\nname: p{i}\n---\n", encoding="utf-8")
        result = engine.lint()
        assert len(result.issues) == 2


class TestWikiPageToDict:
    def test_roundtrip(self):
        page = WikiPage(
            path=Path("x.md"),
            name="x",
            description="d",
            page_type="howto",
        )
        data = page.to_dict()
        assert data["name"] == "x"
        assert data["type"] == "howto"
