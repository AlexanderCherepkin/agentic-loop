"""Unit tests for multi-page generation and SEO metadata in page_composer.py."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent
PAGE_COMPOSER_PATH = ROOT / "figma-agent-core" / "page_composer.py"


def _load_page_composer() -> Any:
    spec = importlib.util.spec_from_file_location("figma_page_composer", str(PAGE_COMPOSER_PATH))
    module = importlib.util.module_from_spec(spec)
    sys.modules["figma_page_composer"] = module
    spec.loader.exec_module(module)
    return module


page_composer = _load_page_composer()


def _minimal_page(name: str, children: list) -> dict:
    return {"type": "PAGE", "name": name, "children": children}


def test_compose_page_emits_full_metadata() -> None:
    ast = {
        "root": {
            "tag": "div",
            "children": [
                {"tag": "h1", "text": "Hero Title", "classes": ["text-2xl"]},
                {"tag": "p", "text": "This is a long enough description sentence for SEO metadata inference.", "classes": ["text-base"]},
            ],
        }
    }
    code = page_composer.compose_page(ast)
    assert 'export const metadata = {' in code
    assert 'title: "Hero Title"' in code
    assert 'description: "This is a long enough description sentence for SEO metadata inference."' in code
    assert "openGraph:" in code
    assert "twitter:" in code
    assert "alternates:" in code
    assert 'type="application/ld+json"' in code


def test_compose_page_client_drops_metadata() -> None:
    ast = {
        "root": {
            "tag": "div",
            "children": [
                {
                    "tag": "button",
                    "text": "Click",
                    "figma_id": "1:2",
                    "interactive": {
                        "state_key": "btnState",
                        "triggers": [{"event": "on_click", "type": "url", "url": "/x"}],
                    },
                },
            ],
        }
    }
    code = page_composer.compose_page(ast)
    assert '"use client"' in code
    assert "export const metadata" not in code


def test_compose_pages_detects_multiple_pages() -> None:
    doc = {
        "root": {
            "type": "DOCUMENT",
            "children": [
                _minimal_page("Home", [{"tag": "h1", "text": "Welcome", "classes": []}]),
                _minimal_page("Pricing", [{"tag": "h1", "text": "Pricing plans", "classes": []}]),
                _minimal_page("About us", [{"tag": "h1", "text": "About", "classes": []}]),
            ],
        }
    }
    pages = page_composer.compose_pages(doc, site_name="Acme", base_url="https://example.com")
    assert len(pages) == 3
    slugs = {p["slug"] for p in pages}
    assert slugs == {"home", "pricing", "about-us"}
    for page in pages:
        assert "export const metadata = {" in page["code"]
        assert page["metadata"]["canonical"].startswith("https://example.com")


def test_compose_pages_fallback_single_page() -> None:
    ast = {
        "root": {
            "tag": "div",
            "children": [
                {"tag": "h1", "text": "Single", "classes": []},
            ],
        }
    }
    pages = page_composer.compose_pages(ast, site_name="Site")
    assert len(pages) == 1
    assert pages[0]["slug"] == "page"


def test_write_pages_creates_app_directories(tmp_path: Path) -> None:
    pages = [
        {"slug": "home", "code": "export default function Page() { return <div>Home</div>; }", "title": "Home", "metadata": {}},
        {"slug": "pricing", "code": "export default function Page() { return <div>Pricing</div>; }", "title": "Pricing", "metadata": {}},
    ]
    written = page_composer.write_pages(pages, output_dir=str(tmp_path / "app"), root_dir=str(tmp_path))
    assert len(written) == 2
    assert (tmp_path / "app" / "page.tsx").exists()
    assert (tmp_path / "app" / "pricing" / "page.tsx").exists()


def test_compose_layout_has_seo_metadata() -> None:
    code = page_composer.compose_layout(
        "Acme",
        description="The best landing page.",
        site_name="Acme Inc",
        base_url="https://example.com",
    )
    assert "metadata: Metadata = {" in code
    assert 'metadataBase: new URL("https://example.com/")' in code
    assert "openGraph:" in code
    assert "twitter:" in code
    assert "robots:" in code
    assert "index: true" in code
