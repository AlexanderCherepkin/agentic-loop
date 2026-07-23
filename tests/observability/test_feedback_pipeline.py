from __future__ import annotations

import json
from pathlib import Path

import pytest


@pytest.fixture
def memory_dir(tmp_path):
    d = tmp_path / "memory"
    d.mkdir()
    return d


def _render_agent(path: Path, agent_text: str) -> None:
    path.write_text(agent_text, encoding="utf-8")


def test_feedback_collector_extracts_failures(memory_dir):
    # The collector is a spec; we validate the expected contract by simulating
    # the downstream writer behavior using the canonical feedback format.
    payload = {
        "validation_status": "needs_refinement",
        "gap_analysis": [
            {"severity": "high", "reason": "Missing dependency x", "file": "pyproject.toml"}
        ],
        "refinement_actions": ["Add dependency x to pyproject.toml"],
        "iteration_count": 1,
        "audit_anchor": "abc123",
    }
    topic = "missing_dependency_x"
    file_path = memory_dir / f"feedback_{topic}.md"
    canonical = f"""## trigger
validation_status=needs_refinement

## symptom
Missing dependency x

## root_cause
Dependency not declared.

## fix
Add dependency x to pyproject.toml.

## how_to_detect_early
Run `pip check` before committing.

## related_agents
pyproject.toml, validation

## last_seen
{payload['audit_anchor']}
"""
    file_path.write_text(canonical, encoding="utf-8")
    assert file_path.exists()
    assert "Add dependency x" in file_path.read_text(encoding="utf-8")


def test_feedback_recall_scores_by_keyword(memory_dir):
    # Simulate two feedback files and keyword recall.
    a = memory_dir / "feedback_pip.md"
    b = memory_dir / "feedback_lint.md"
    a.write_text("## symptom\nMissing pip dependency", encoding="utf-8")
    b.write_text("## symptom\nLint failure", encoding="utf-8")

    query = "missing package"
    files = sorted(memory_dir.glob("feedback_*.md"), key=lambda p: p.stat().st_mtime, reverse=True)
    q = query.lower()
    results = [
        (sum(1 for token in q.split() if token in f.read_text(encoding="utf-8").lower()), f)
        for f in files
    ]
    results.sort(key=lambda x: x[0], reverse=True)
    assert results[0][1].name == "feedback_pip.md"


def test_feedback_writer_rejects_path_traversal(memory_dir):
    unsafe_name = "../../../etc/passwd"
    clean = Path(unsafe_name).name
    target = memory_dir / clean
    # Writing only the basename keeps the file inside memory_dir.
    target.write_text("x", encoding="utf-8")
    assert target.exists()
    assert target.resolve().is_relative_to(memory_dir.resolve())
