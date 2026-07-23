"""Tests for runtime/multi_page engine and config."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from runtime.multi_page import MultiPageConfig, MultiPageEngine


pytestmark = [pytest.mark.core, pytest.mark.runtime]


def test_config_from_dict_defaults():
    cfg = MultiPageConfig.from_dict({})
    assert cfg.base_url == "/"
    assert cfg.app_router_dir == "src/app"
    assert cfg.write_pages is True
    assert cfg.generate_navigation is True


def test_config_validation_requires_pages(tmp_path):
    cfg = MultiPageConfig(target_dir=tmp_path)
    errors = cfg.validate()
    assert any("page" in e.lower() for e in errors)


def test_config_validation_invalid_slug(tmp_path):
    cfg = MultiPageConfig(
        target_dir=tmp_path,
        pages=[{"slug": "bad slug", "title": "Bad", "code": "export default function Page() {}"}],
    )
    errors = cfg.validate()
    assert any("slug" in e for e in errors)


def test_engine_writes_home_and_sub_pages(tmp_path):
    cfg = MultiPageConfig(
        target_dir=tmp_path,
        base_url="https://example.com",
        pages=[
            {"slug": "home", "title": "Home", "code": "export default function Home() { return <h1>Home</h1>; }"},
            {"slug": "about", "title": "About", "code": "export default function About() { return <h1>About</h1>; }"},
        ],
    )
    result = MultiPageEngine(tmp_path, cfg).run()
    assert not result.errors
    assert any("src/app/page.tsx" in f for f in result.files_written)
    assert any("src/app/about/page.tsx" in f for f in result.files_written)
    assert (tmp_path / "src" / "app" / "page.tsx").exists()
    assert (tmp_path / "src" / "app" / "about" / "page.tsx").exists()


def test_engine_generates_navigation_sitemap_robots(tmp_path):
    cfg = MultiPageConfig(
        target_dir=tmp_path,
        base_url="https://example.com",
        pages=[
            {"slug": "home", "title": "Home", "code": "export default function Home() { return <h1>Home</h1>; }"},
        ],
    )
    result = MultiPageEngine(tmp_path, cfg).run()
    assert any("src/app/components/Navigation.tsx" in f for f in result.files_written)
    assert any("src/app/sitemap.ts" in f for f in result.files_written)
    assert any("src/app/robots.ts" in f for f in result.files_written)


def test_engine_routing_only_does_not_write_pages(tmp_path):
    cfg = MultiPageConfig(
        target_dir=tmp_path,
        base_url="https://example.com",
        write_pages=False,
        pages=[
            {"slug": "home", "title": "Home", "code": "export default function Home() { return <h1>Home</h1>; }"},
        ],
    )
    result = MultiPageEngine(tmp_path, cfg).run()
    assert not any("page.tsx" in f for f in result.files_written)
    assert any("Navigation.tsx" in f for f in result.files_written)


def test_engine_reports_missing_code(tmp_path):
    cfg = MultiPageConfig(
        target_dir=tmp_path,
        pages=[{"slug": "empty", "title": "Empty"}],
    )
    result = MultiPageEngine(tmp_path, cfg).run()
    assert result.errors
    assert any("missing page code" in e["reason"] for e in result.errors)


def test_engine_blocks_path_traversal_write(tmp_path):
    cfg = MultiPageConfig(
        target_dir=tmp_path,
        base_url="https://example.com",
        pages=[
            {"slug": "home", "title": "Home", "code": "export default function Home() {}"},
        ],
    )
    engine = MultiPageEngine(tmp_path, cfg)
    engine._write_file("../../evil.tsx", "evil")
    assert any("Path escapes" in e["reason"] for e in engine.result.errors)
    assert not (tmp_path.parent / "evil.tsx").exists()
