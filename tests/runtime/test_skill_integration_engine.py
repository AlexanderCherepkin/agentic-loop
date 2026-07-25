"""Tests for the SkillIntegrationEngine write gate."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from runtime.skill_integration.config import SkillIntegrationConfig
from runtime.skill_integration.engine import (
    IntegrationResult,
    SkillIntegrationEngine,
    SkillProposal,
    WikiProposal,
)


@pytest.fixture
def engine(tmp_path):
    config = SkillIntegrationConfig(
        workspace_root=tmp_path,
        skills_dir=".claude/skills",
        wiki_dir="memory/wiki",
        audit_log_dir=".audit",
    )
    return SkillIntegrationEngine(config)


class TestSkillIntegrationConfig:
    def test_to_dict(self):
        config = SkillIntegrationConfig()
        data = config.to_dict()
        assert "create_skill" in data["allowed_operations"]
        assert ".env" in data["blocked_components"]


class TestPrepareSkillProposal:
    def test_normalizes_name(self, engine):
        proposal = engine.prepare_skill_proposal(
            name="My Skill",
            trigger="when asked",
            description="A skill",
        )
        assert proposal.name == "my-skill"
        assert proposal.trigger == "when asked"

    def test_truncates_long_name(self, engine):
        proposal = engine.prepare_skill_proposal(
            name="a" * 100,
            trigger="x",
            description="y",
        )
        assert len(proposal.name) == 64


class TestPrepareWikiProposals:
    def test_prepares_new_page(self, engine, tmp_path):
        (tmp_path / "memory/wiki").mkdir(parents=True)
        proposals = engine.prepare_wiki_proposals(
            [
                {
                    "name": "Auth Flow",
                    "type": "concept",
                    "description": "How auth works.",
                    "links": ["sessions"],
                }
            ]
        )
        assert len(proposals) == 1
        assert proposals[0].name == "auth-flow"
        assert proposals[0].page_type == "concept"
        assert "[[sessions]]" in proposals[0].content
        assert proposals[0].existing is False

    def test_detects_existing_page(self, engine, tmp_path):
        wiki_root = tmp_path / "memory/wiki"
        wiki_root.mkdir(parents=True)
        (wiki_root / "concept-auth-flow.md").write_text("# old", encoding="utf-8")
        proposals = engine.prepare_wiki_proposals(
            [{"name": "Auth Flow", "type": "concept", "description": "x"}]
        )
        assert proposals[0].existing is True


class TestApplyApprovalGate:
    def test_unknown_operation_returns_error(self, engine):
        result = engine.apply("destroy_all", "approved")
        assert result.status == "error"
        assert "Unknown operation" in result.summary

    def test_missing_approval_rejects(self, engine):
        result = engine.apply("create_skill", "pending")
        assert result.status == "rejected"
        assert "approval" in result.summary.lower()

    def test_create_skill_writes_file(self, engine):
        result = engine.apply(
            "create_skill",
            "approved",
            skill_candidate={
                "name": "test skill",
                "trigger": "when needed",
                "description": "A test skill.",
                "decision_flow": ["step 1"],
            },
        )
        assert result.status == "created"
        assert len(result.written_paths) == 1
        assert Path(result.written_paths[0]).as_posix().endswith(".claude/skills/test-skill/SKILL.md")
        assert len(result.memory_notes) == 1

    def test_create_skill_rejects_existing_without_modify(self, engine):
        engine.apply(
            "create_skill",
            "approved",
            skill_candidate={"name": "dup", "trigger": "t", "description": "d"},
        )
        result = engine.apply(
            "create_skill",
            "approved",
            skill_candidate={"name": "dup", "trigger": "t", "description": "d"},
        )
        assert result.status == "rejected"
        assert "already exists" in result.summary

    def test_update_skill_requires_modify(self, engine):
        result = engine.apply(
            "update_skill",
            "approved",
            skill_candidate={"name": "x", "trigger": "t", "description": "d"},
        )
        assert result.status == "rejected"

    def test_ingest_wiki_writes_pages(self, engine):
        result = engine.apply(
            "ingest_wiki",
            "approved",
            wiki_updates=[
                {
                    "name": "Auth Flow",
                    "type": "concept",
                    "description": "How auth works.",
                }
            ],
        )
        assert result.status == "created"
        assert len(result.written_paths) == 1
        assert Path(result.written_paths[0]).as_posix().endswith("memory/wiki/concept-auth-flow.md")
        assert result.summary.startswith("Ingested")

    def test_ingest_wiki_rejects_path_outside_wiki(self, engine):
        result = engine.apply(
            "ingest_wiki",
            "approved",
            wiki_updates=[
                {
                    "name": "escape",
                    "type": "../secret",
                    "description": "bad",
                }
            ],
        )
        assert result.status == "error"
        assert result.rejected_paths

    def test_lint_wiki_delete(self, engine, tmp_path):
        wiki_root = tmp_path / "memory/wiki"
        wiki_root.mkdir(parents=True)
        target = wiki_root / "orphan.md"
        target.write_text("x", encoding="utf-8")
        result = engine.apply(
            "lint_wiki",
            "approved",
            lint_plan=[{"action": "delete", "target": "orphan.md"}],
        )
        assert result.status == "created"
        assert not target.exists()

    def test_lint_wiki_deprecate(self, engine, tmp_path):
        wiki_root = tmp_path / "memory/wiki"
        wiki_root.mkdir(parents=True)
        target = wiki_root / "old.md"
        target.write_text("# Old", encoding="utf-8")
        result = engine.apply(
            "lint_wiki",
            "approved",
            lint_plan=[{"action": "mark_deprecated", "target": "old.md"}],
        )
        assert result.status == "created"
        assert "status: deprecated" in target.read_text(encoding="utf-8")


class TestSkillProposalRender:
    def test_render_includes_frontmatter(self):
        proposal = SkillProposal(
            name="my-skill",
            trigger="when asked",
            description="Does things.",
            decision_flow=["Analyze", "Execute"],
            failure_modes=[{"condition": "No input", "response": "Ask user"}],
        )
        rendered = proposal.render()
        assert "name: my-skill" in rendered
        assert "## Decision Flow" in rendered
        assert "## Failure Modes" in rendered
        assert "1. Analyze" in rendered


class TestWikiProposal:
    def test_to_dict(self):
        proposal = WikiProposal(
            name="auth-flow",
            page_type="concept",
            description="x",
            content="y",
        )
        assert proposal.to_dict()["type"] == "concept"
