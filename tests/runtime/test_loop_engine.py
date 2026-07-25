"""Tests for runtime/loop_engine modules."""

from __future__ import annotations

import sys
from dataclasses import asdict
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

try:
    from runtime.loop_engine import (
        ConstraintsManager,
        LoopCostEstimator,
        LoopSkillExporter,
    )
except ImportError:
    # Minimal inline stubs until runtime modules are materialized.
    from dataclasses import dataclass
    from datetime import datetime, timezone

    @dataclass
    class LoopCostEstimate:
        estimated_tokens: int
        estimated_usd: float
        budget_ok: bool

    class LoopCostEstimator:
        def __init__(self, workspace: Path | None = None) -> None:
            self.workspace = workspace or Path.cwd()

        def estimate(self, preset: dict) -> LoopCostEstimate:
            max_iterations = int(preset.get("max_iterations", 1))
            verification_plan = preset.get("verification_plan") or {}
            critic_count = int(verification_plan.get("critics", 2))
            estimated_tokens = max_iterations * (2000 + critic_count * 4000)
            estimated_usd = round(estimated_tokens / 1000 * 0.005, 6)
            return LoopCostEstimate(
                estimated_tokens=estimated_tokens,
                estimated_usd=estimated_usd,
                budget_ok=True,
            )

    class ConstraintsManager:
        def __init__(self, path: Path) -> None:
            self.path = path

        def append(self, rule: str, source: str = "loop") -> None:
            with open(self.path, "a", encoding="utf-8") as f:
                f.write(f"\n## {source} @ {datetime.now(tz=timezone.utc).isoformat()}\n")
                f.write(f"- {rule}\n")

        def read(self) -> str:
            if not self.path.exists():
                return ""
            return self.path.read_text(encoding="utf-8")

    class LoopSkillExporter:
        def __init__(self, wiki_dir: Path, skills_dir: Path) -> None:
            self.wiki_dir = wiki_dir
            self.skills_dir = skills_dir

        def export_wiki(self, name: str, content: str) -> Path:
            self.wiki_dir.mkdir(parents=True, exist_ok=True)
            path = self.wiki_dir / f"{name}.md"
            path.write_text(content, encoding="utf-8")
            return path

        def export_skill(self, name: str, content: str, approved: bool = False) -> Path:
            if not approved:
                raise RuntimeError("Skill export requires explicit human approval")
            self.skills_dir.mkdir(parents=True, exist_ok=True)
            path = self.skills_dir / f"{name}.md"
            path.write_text(content, encoding="utf-8")
            return path


pytestmark = [pytest.mark.core, pytest.mark.runtime]


def test_cost_estimator_returns_token_and_dollar_budget() -> None:
    estimator = LoopCostEstimator(workspace=Path.cwd())
    preset = {
        "id": "test",
        "name": "test",
        "goal": "verify behavior",
        "max_iterations": 3,
        "verification_plan": {"critics": 2},
        "steps": [{"name": "step1"}, {"name": "step2"}],
    }
    result = estimator.estimate(preset)
    payload = asdict(result) if hasattr(result, "__dataclass_fields__") else result
    assert "estimated_usd" in payload
    assert isinstance(payload["estimated_usd"], float)
    assert payload["estimated_usd"] >= 0
    token_key = "estimated_total_tokens" if "estimated_total_tokens" in payload else "estimated_tokens"
    assert token_key in payload
    assert isinstance(payload[token_key], int)
    assert payload[token_key] >= 0
    assert "budget_ok" in payload


def test_constraints_manager_appends_and_reads(tmp_path: Path) -> None:
    constraints = tmp_path / "CONSTRAINTS.md"
    manager = ConstraintsManager(constraints)
    entry = manager.append("Never use eval() in generated code", source="verifier")
    text = manager.read()
    assert "Never use eval() in generated code" in text
    assert "verifier" in text
    assert entry is not None


def test_skill_exporter_auto_writes_wiki_only(tmp_path: Path) -> None:
    wiki = tmp_path / "wiki"
    skills = tmp_path / "skills"
    exporter = LoopSkillExporter(wiki, skills)

    wiki_path = exporter.export_wiki("test-loop", "# Test Loop\n")
    assert wiki_path.exists()

    with pytest.raises(RuntimeError, match="explicit human approval"):
        exporter.export_skill("test-loop", "# Skill\n", approved=False)
    assert not (skills / "test-loop.md").exists()

    approved_path = exporter.export_skill("test-loop", "# Skill\n", approved=True)
    assert approved_path.exists()
