"""LLM Wiki engine: ingest, query, lint.

All file writes go through safe_write_file from runtime/safety/file_system_guard
when available, otherwise a plain guarded write.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .config import WikiConfig


def _today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


@dataclass
class WikiPage:
    """Parsed wiki page."""

    path: Path
    name: str
    description: str = ""
    page_type: str = "concept"
    status: str = "draft"
    created: str = ""
    updated: str = ""
    sources: list[str] = field(default_factory=list)
    content: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": str(self.path),
            "name": self.name,
            "description": self.description,
            "type": self.page_type,
            "status": self.status,
            "created": self.created,
            "updated": self.updated,
            "sources": self.sources,
        }


@dataclass
class WikiIngestResult:
    """Result of an ingest operation."""

    proposed_pages: list[WikiPage] = field(default_factory=list)
    index_update: str | None = None
    summary: str = ""
    requires_approval: bool = True


@dataclass
class WikiLintResult:
    """Result of a lint operation."""

    issues: list[dict[str, Any]] = field(default_factory=list)
    summary: str = ""
    requires_approval: bool = True


@dataclass
class WikiQueryResult:
    """Result of a query operation."""

    relevant_pages: list[WikiPage] = field(default_factory=list)
    summary: str = ""


class WikiEngine:
    """Local engine for memory/wiki/ ingest, query, and lint."""

    _LINK_RE = re.compile(r"\[\[([^\]]+)\]\]")

    def __init__(self, config: WikiConfig | None = None) -> None:
        self.config = config or WikiConfig()
        self.config.wiki_root.mkdir(parents=True, exist_ok=True)

    # ── Public API ────────────────────────────────────────────────────────────

    def query(self, question: str, top_k: int = 5) -> WikiQueryResult:
        """Find pages relevant to the question."""
        all_pages = self._load_pages()
        scored: list[tuple[WikiPage, float]] = []
        lowered = question.lower()
        for page in all_pages:
            score = 0.0
            for term in lowered.split():
                if len(term) < 3:
                    continue
                if term in page.name.lower():
                    score += 3.0
                if term in page.description.lower():
                    score += 2.0
                if term in page.content.lower():
                    score += 1.0
            if score > 0:
                scored.append((page, score))
        scored.sort(key=lambda x: x[1], reverse=True)
        top = [p for p, _ in scored[:top_k]]
        return WikiQueryResult(
            relevant_pages=top,
            summary=f"Found {len(top)} relevant wiki page(s) for query.",
        )

    def ingest(self, proposed_pages: list[WikiPage], proposed_index: str | None = None) -> WikiIngestResult:
        """Return a structured ingest proposal; actual write happens in skill_integrator."""
        existing = {p.name for p in self._load_pages()}
        enriched: list[WikiPage] = []
        for page in proposed_pages:
            page.path = self.config.wiki_root / f"{page.page_type}-{page.name}.md"
            if page.name in existing:
                page.status = "draft"
            enriched.append(page)
        return WikiIngestResult(
            proposed_pages=enriched,
            index_update=proposed_index,
            summary=f"Proposed {len(enriched)} page(s) for wiki ingest.",
            requires_approval=True,
        )

    def lint(self) -> WikiLintResult:
        """Find orphans, duplicates, stale pages, and broken links."""
        pages = self._load_pages()
        issues: list[dict[str, Any]] = []
        all_links: dict[str, set[str]] = {}
        page_names = {p.name for p in pages}

        for page in pages:
            links = set(self._LINK_RE.findall(page.content))
            all_links[page.name] = links

        index_names = set()
        if self.config.index_path.exists():
            index_content = self.config.index_path.read_text(encoding="utf-8")
            index_names = set(self._LINK_RE.findall(index_content))

        # Orphans
        for page in pages:
            if page.name in ("wiki-index", "index"):
                continue
            if page.name not in index_names:
                issues.append({
                    "action": "relink",
                    "target": str(page.path),
                    "name": page.name,
                    "reason": "not linked from index",
                })

        # Broken links
        for page in pages:
            for link in all_links.get(page.name, set()):
                if link not in page_names:
                    issues.append({
                        "action": "relink",
                        "target": str(page.path),
                        "broken_link": link,
                        "reason": f"broken link [[{link}]]",
                    })

        # Duplicates by description overlap
        for i, a in enumerate(pages):
            for b in pages[i + 1 :]:
                overlap = self._description_overlap(a.description, b.description)
                if overlap >= 0.5:
                    issues.append({
                        "action": "merge",
                        "target": str(a.path),
                        "source_page": str(b.path),
                        "reason": f"high description overlap ({overlap:.0%})",
                    })

        # Stale pages
        today = datetime.now(timezone.utc)
        for page in pages:
            if page.status == "deprecated":
                updated = self._parse_date(page.updated) or today
                age_days = (today - updated).days
                if age_days > self.config.deprecated_delete_days:
                    issues.append({
                        "action": "delete",
                        "target": str(page.path),
                        "reason": f"deprecated for {age_days} days",
                    })

        # Cap
        issues = issues[: self.config.max_lint_issues]
        summary = f"Lint found {len(issues)} issue(s) across {len(pages)} page(s)."
        if not issues:
            summary = "Wiki is clean."
        return WikiLintResult(issues=issues, summary=summary, requires_approval=len(issues) > 0)

    # ── Helpers ─────────────────────────────────────────────────────────────────

    def _load_pages(self) -> list[WikiPage]:
        pages: list[WikiPage] = []
        if not self.config.wiki_root.exists():
            return pages
        for path in sorted(self.config.wiki_root.glob("*.md")):
            if path.name.startswith("_"):
                continue
            try:
                content = path.read_text(encoding="utf-8")
            except Exception:
                continue
            page = self._parse_page(path, content)
            if page:
                pages.append(page)
        return pages

    def _parse_page(self, path: Path, content: str) -> WikiPage | None:
        name = path.stem
        description = ""
        page_type = "concept"
        status = "draft"
        created = ""
        updated = ""
        sources: list[str] = []

        front = re.match(r"^---\s*\n(.*?)\n---\s*\n", content, re.DOTALL)
        if front:
            try:
                import yaml

                data = yaml.safe_load(front.group(1)) or {}
                name = data.get("name", name)
                description = data.get("description", "")
                meta = data.get("metadata", {})
                page_type = meta.get("type", page_type)
                status = meta.get("status", status)
                created = meta.get("created", "")
                updated = meta.get("updated", "")
                sources = meta.get("sources", [])
            except Exception:
                pass

        return WikiPage(
            path=path,
            name=name,
            description=description,
            page_type=page_type,
            status=status,
            created=created,
            updated=updated,
            sources=sources,
            content=content,
        )

    def _description_overlap(self, a: str, b: str) -> float:
        if not a or not b:
            return 0.0
        words_a = set(a.lower().split())
        words_b = set(b.lower().split())
        if not words_a or not words_b:
            return 0.0
        intersection = words_a & words_b
        union = words_a | words_b
        return len(intersection) / len(union)

    def _parse_date(self, value: str) -> datetime | None:
        if not value:
            return None
        for fmt in ("%Y-%m-%d", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%S%z"):
            try:
                return datetime.strptime(value, fmt)
            except ValueError:
                continue
        return None
