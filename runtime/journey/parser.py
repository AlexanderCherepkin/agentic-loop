"""Read-only parser for memory/wiki/ and .claude/skills/."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime, time, timezone
from pathlib import Path
from typing import Any

from mcp_servers.path_guard import MCPPathGuard

from .config import JourneyConfig


@dataclass
class JourneyNode:
    """A single node in the journey graph."""

    id: str
    label: str
    type: str
    timestamp: datetime | None = None
    group: str = ""
    meta: dict[str, Any] = field(default_factory=dict)


@dataclass
class JourneyEdge:
    """A directed edge between two journey nodes."""

    source: str
    target: str
    label: str = ""


@dataclass
class JourneyGraph:
    """Parsed nodes and edges for the radial graph."""

    nodes: list[JourneyNode] = field(default_factory=list)
    edges: list[JourneyEdge] = field(default_factory=list)


class JourneyParser:
    """Parse wiki pages and skills into a graph."""

    _LINK_RE = re.compile(r"\[\[([^\]]+)\]\]")
    _FRONT_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)

    def __init__(self, config: JourneyConfig | None = None):
        self.config = config or JourneyConfig()
        self._wiki_guard = MCPPathGuard(self.config.wiki_root)
        self._skills_guard = MCPPathGuard(self.config.skills_root)

    def parse(self) -> JourneyGraph:
        """Return a read-only graph of the knowledge base."""
        graph = JourneyGraph()
        wiki_nodes, wiki_edges = self._parse_wiki()
        skill_nodes, skill_edges = self._parse_skills()
        graph.nodes.extend(wiki_nodes)
        graph.nodes.extend(skill_nodes)
        graph.edges.extend(wiki_edges)
        graph.edges.extend(skill_edges)
        if len(graph.nodes) > self.config.max_nodes:
            graph.nodes = graph.nodes[: self.config.max_nodes]
            allowed = {n.id for n in graph.nodes}
            graph.edges = [e for e in graph.edges if e.source in allowed and e.target in allowed]
        return graph

    def _parse_wiki(self) -> tuple[list[JourneyNode], list[JourneyEdge]]:
        nodes: list[JourneyNode] = []
        edges: list[JourneyEdge] = []
        if not self.config.wiki_root.exists():
            return nodes, edges
        for path in sorted(self.config.wiki_root.glob("*.md")):
            if path.name.startswith("_"):
                continue
            try:
                resolved = self._wiki_guard.read_path(str(path))
                content = resolved.read_text(encoding="utf-8")
            except Exception:
                continue
            front, body = self._split_frontmatter(content)
            node_id = self._node_id(path.stem)
            label = front.get("name", path.stem)
            node_type = "index" if path.stem == "index" else "wiki"
            timestamp = self._parse_timestamp(front.get("updated", front.get("created", "")))
            nodes.append(
                JourneyNode(
                    id=node_id,
                    label=label,
                    type=node_type,
                    timestamp=timestamp,
                    group=front.get("metadata", {}).get("type", "concept") if node_type != "index" else "index",
                    meta={"path": str(resolved), "description": front.get("description", "")},
                )
            )
            for raw_link in self._LINK_RE.findall(body):
                target = self._normalize_link(raw_link)
                edges.append(JourneyEdge(source=node_id, target=target, label=raw_link))
        return nodes, edges

    def _parse_skills(self) -> tuple[list[JourneyNode], list[JourneyEdge]]:
        nodes: list[JourneyNode] = []
        edges: list[JourneyEdge] = []
        if not self.config.skills_root.exists():
            return nodes, edges
        for skill_dir in sorted(self.config.skills_root.iterdir()):
            if not skill_dir.is_dir():
                continue
            skill_path = skill_dir / "SKILL.md"
            try:
                resolved = self._skills_guard.read_path(str(skill_path))
                content = resolved.read_text(encoding="utf-8")
            except Exception:
                continue
            front, body = self._split_frontmatter(content)
            node_id = self._node_id(skill_dir.name)
            label = front.get("name", skill_dir.name)
            timestamp = self._parse_timestamp(
                front.get("date", front.get("created", "")), fallback_mtime=resolved
            )
            nodes.append(
                JourneyNode(
                    id=node_id,
                    label=label,
                    type="skill",
                    timestamp=timestamp,
                    group="skill",
                    meta={"path": str(resolved), "description": front.get("description", "")},
                )
            )
            for raw_link in self._LINK_RE.findall(body):
                target = self._normalize_link(raw_link)
                edges.append(JourneyEdge(source=node_id, target=target, label=raw_link))
        return nodes, edges

    def _split_frontmatter(self, content: str) -> tuple[dict[str, Any], str]:
        match = self._FRONT_RE.match(content)
        if not match:
            return {}, content
        try:
            import yaml

            return yaml.safe_load(match.group(1)) or {}, content[match.end() :]
        except Exception:
            return {}, content

    def _parse_timestamp(self, value: str | datetime | date | None, fallback_mtime: Path | None = None) -> datetime | None:
        if isinstance(value, datetime):
            return value
        if isinstance(value, date):
            return datetime.combine(value, time())
        if value:
            for fmt in ("%Y-%m-%d", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%S%z"):
                try:
                    return datetime.strptime(value, fmt)
                except ValueError:
                    continue
        if fallback_mtime and fallback_mtime.exists():
            stat = fallback_mtime.stat()
            return datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc)
        return None

    def _normalize_link(self, raw: str) -> str:
        # Links may be "page-name" or "page-name|display text".
        name = raw.split("|", 1)[0].split("#", 1)[0].strip()
        return self._node_id(name)

    def _node_id(self, name: str) -> str:
        return re.sub(r"[^a-z0-9_-]+", "-", name.lower()).strip("-")[:64] or "node"
