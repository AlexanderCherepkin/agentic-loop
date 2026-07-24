"""Tests for runtime/skill_automation engine and config."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from runtime.skill_automation import (
    GraphifyNeed,
    SkillAutomationConfig,
    SkillAutomationEngine,
    SkillAutomationResult,
    SourceCandidate,
)

pytestmark = [pytest.mark.core, pytest.mark.runtime]


def test_config_defaults_are_reasonable():
    cfg = SkillAutomationConfig()
    assert cfg.graphify_min_changed_files == 10
    assert cfg.source_min_words == 200
    assert ".md" in cfg.source_extensions
    assert "node_modules/" in cfg.excluded_patterns


def test_assess_source_value_skips_short_text():
    engine = SkillAutomationEngine(SkillAutomationConfig(source_min_words=50))
    assert engine.assess_source_value("short.md", "a few words") is None


def test_assess_source_value_detects_process_signals_and_steps():
    engine = SkillAutomationEngine(SkillAutomationConfig(source_min_words=10))
    text = (
        "# Deploy playbook\n\n"
        "1. Build the container.\n"
        "2. Push the image.\n"
        "3. Roll out the release.\n\n"
        "This workflow follows the release pipeline.\n"
    )
    candidate = engine.assess_source_value("deploy.md", text)
    assert candidate is not None
    assert candidate.path == "deploy.md"
    assert candidate.has_numbered_steps is True
    assert "pipeline" in candidate.process_signals
    assert candidate.estimated_reuse == "high"


def test_assess_source_value_rejects_plain_text():
    engine = SkillAutomationEngine(SkillAutomationConfig(source_min_words=10))
    text = (
        "Lorem ipsum dolor sit amet, consectetur adipiscing elit. "
        "Sed do eiusmod tempor incididunt ut labore et dolore magna aliqua. " * 15
    )
    assert engine.assess_source_value("note.md", text) is None


def test_is_excluded_respects_patterns():
    engine = SkillAutomationEngine(SkillAutomationConfig())
    assert engine._is_excluded("node_modules/pkg/readme.md") is True
    assert engine._is_excluded("src/process.md") is False


def test_detect_new_sources_caps_at_max_files(tmp_path: Path):
    cfg = SkillAutomationConfig(
        workspace_root=tmp_path,
        source_min_words=5,
        source_max_files_per_scan=2,
    )
    for i in range(4):
        path = tmp_path / f"guide{i}.md"
        path.write_text(f"# Guide {i}\n\n1. Step one.\n2. Step two.\n", encoding="utf-8")
    engine = SkillAutomationEngine(cfg)
    candidates = engine._detect_new_sources(set())
    assert len(candidates) == 2


def test_scan_records_state(tmp_path: Path):
    cfg = SkillAutomationConfig(workspace_root=tmp_path, source_min_words=5)
    (tmp_path / "process.md").write_text(
        "# Process\n\n1. Do this.\n2. Do that.\nworkflow.\n", encoding="utf-8"
    )
    engine = SkillAutomationEngine(cfg)
    result = engine.scan()
    assert isinstance(result, SkillAutomationResult)
    assert len(result.source_candidates) == 1
    assert result.source_candidates[0].path == "process.md"
    assert engine.state_path.exists()


def test_mark_proposed_prevents_redetection(tmp_path: Path):
    cfg = SkillAutomationConfig(workspace_root=tmp_path, source_min_words=5)
    (tmp_path / "process.md").write_text(
        "# Process\n\n1. Do this.\n2. Do that.\n", encoding="utf-8"
    )
    engine = SkillAutomationEngine(cfg)
    engine.mark_proposed("process.md")
    candidates = engine._detect_new_sources(engine._load_already_proposed())
    assert not any(c.path == "process.md" for c in candidates)


def test_detect_graphify_need_triggers_on_new_agent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    cfg = SkillAutomationConfig(workspace_root=tmp_path)
    engine = SkillAutomationEngine(cfg)

    def fake_changed():
        return [".agent_loop/tooll_subagents/planning/new_agent.md"]

    monkeypatch.setattr(engine, "_git_changed_files", fake_changed)
    (tmp_path / ".agent_loop" / "tooll_subagents" / "planning").mkdir(parents=True)
    (tmp_path / ".agent_loop" / "tooll_subagents" / "planning" / "new_agent.md").write_text(
        "# Agent\n\n## Role\n\n## Contract\n", encoding="utf-8"
    )
    need = engine._detect_graphify_need()
    assert need.needs_update is True
    assert need.new_agents_detected


def test_detect_graphify_need_respects_threshold(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    cfg = SkillAutomationConfig(workspace_root=tmp_path, graphify_min_changed_files=3)
    engine = SkillAutomationEngine(cfg)
    monkeypatch.setattr(engine, "_git_changed_files", lambda: ["a.py", "b.py", "c.py"])
    need = engine._detect_graphify_need()
    assert need.needs_update is True
    assert len(need.changed_files) == 3


def test_propose_actions_returns_both_types(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    cfg = SkillAutomationConfig(workspace_root=tmp_path, source_min_words=5)
    (tmp_path / "process.md").write_text(
        "# Process\n\n1. Do this.\n2. Do that.\n", encoding="utf-8"
    )
    engine = SkillAutomationEngine(cfg)
    monkeypatch.setattr(
        engine, "_git_changed_files", lambda: ["a.py"] * cfg.graphify_min_changed_files
    )
    actions = engine.propose_actions()
    assert any(a["type"] == "learn_from_source" for a in actions)
    assert any(a["type"] == "graphify_update" for a in actions)


def test_graphify_need_no_update_without_changes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    cfg = SkillAutomationConfig(workspace_root=tmp_path)
    engine = SkillAutomationEngine(cfg)
    monkeypatch.setattr(engine, "_git_changed_files", lambda: [])
    need = engine._detect_graphify_need()
    assert need.needs_update is False
    assert "no significant changes" in need.reason


def test_source_candidate_to_dict_round_trip():
    c = SourceCandidate(
        path="x.md",
        word_count=100,
        process_signals=["workflow"],
        has_numbered_steps=True,
        estimated_reuse="medium",
        reason="test",
    )
    data = c.to_dict()
    assert data["path"] == "x.md"
    assert data["estimated_reuse"] == "medium"


def test_result_to_dict_is_serializable():
    result = SkillAutomationResult(
        source_candidates=[SourceCandidate(path="x.md", word_count=10)],
        graphify_need=GraphifyNeed(True, changed_files=["a.py"], reason="test"),
    )
    data = result.to_dict()
    assert data["source_candidates"][0]["path"] == "x.md"
    assert data["graphify_need"]["needs_update"] is True
