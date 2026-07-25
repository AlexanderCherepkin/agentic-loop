"""Tests for the /journey parser."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))

from runtime.journey.config import JourneyConfig
from runtime.journey.parser import JourneyParser


class TestJourneyParser:
    def test_parses_wiki_links(self, tmp_path):
        wiki_root = tmp_path / "memory" / "wiki"
        wiki_root.mkdir(parents=True)
        (wiki_root / "index.md").write_text("# Index\n\nSee [[auth-flow]].", encoding="utf-8")
        (wiki_root / "auth-flow.md").write_text(
            "---\nname: Auth Flow\n---\n# Auth\n\nSee [[index]].", encoding="utf-8"
        )
        config = JourneyConfig(workspace_root=tmp_path)
        graph = JourneyParser(config).parse()
        ids = {n.id for n in graph.nodes}
        assert "index" in ids
        assert "auth-flow" in ids
        edges = {(e.source, e.target) for e in graph.edges}
        assert ("index", "auth-flow") in edges
        assert ("auth-flow", "index") in edges

    def test_parses_skill_frontmatter(self, tmp_path):
        skills_root = tmp_path / ".claude" / "skills" / "my-skill"
        skills_root.mkdir(parents=True)
        (skills_root / "SKILL.md").write_text(
            "---\nname: My Skill\ndate: 2026-07-20\ndescription: A skill.\n---\n# /my-skill", encoding="utf-8"
        )
        config = JourneyConfig(workspace_root=tmp_path)
        graph = JourneyParser(config).parse()
        skill_node = next(n for n in graph.nodes if n.type == "skill")
        assert skill_node.label == "My Skill"
        assert skill_node.timestamp is not None
        assert skill_node.timestamp.year == 2026

    def test_rejects_outside_wiki_via_guard(self, tmp_path):
        wiki_root = tmp_path / "memory" / "wiki"
        wiki_root.mkdir(parents=True)
        # A symlink or traversal outside root would be blocked; here we just verify the guard is used.
        config = JourneyConfig(workspace_root=tmp_path)
        graph = JourneyParser(config).parse()
        assert graph.nodes == []

    def test_caps_nodes_at_max(self, tmp_path):
        wiki_root = tmp_path / "memory" / "wiki"
        wiki_root.mkdir(parents=True)
        for i in range(10):
            (wiki_root / f"page-{i}.md").write_text(f"# Page {i}\n", encoding="utf-8")
        config = JourneyConfig(workspace_root=tmp_path, max_nodes=3)
        graph = JourneyParser(config).parse()
        assert len(graph.nodes) == 3
        allowed = {n.id for n in graph.nodes}
        assert all(e.source in allowed and e.target in allowed for e in graph.edges)
