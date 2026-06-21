"""Unit tests for figma-agent-core/refinement_loop.py.

Loads the module via importlib because the directory name contains a hyphen.
All external module calls are injected via callbacks.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent
REFINEMENT_PATH = ROOT / "figma-agent-core" / "refinement_loop.py"


def _load_refinement() -> Any:
    spec = importlib.util.spec_from_file_location("figma_refinement", str(REFINEMENT_PATH))
    module = importlib.util.module_from_spec(spec)
    sys.modules["figma_refinement"] = module
    spec.loader.exec_module(module)
    return module


refinement = _load_refinement()


def test_module_loads() -> None:
    assert hasattr(refinement, "run_refinement_loop")
    assert hasattr(refinement, "RefinementReport")


def test_passes_on_first_iteration_if_visual_qa_passed(tmp_path: Path) -> None:
    ast_file = tmp_path / "layout_ast.json"
    ast_file.write_text('{"root": {"tag": "div", "classes": []}}', encoding="utf-8")

    def fake_compose(mod: Any, ast: Path, out: Path, title: Any) -> bool:
        return True

    def fake_qa(i: int, url: str, ast: Path, out: Path, ref: Any, qa_dir: Path) -> dict:
        return {"status": "passed", "diff_score": 0.01, "dom_assertions": [], "discrepancies": []}

    result = refinement.run_refinement_loop(
        page_url="http://localhost:3000",
        ast_path=str(ast_file),
        compose_output=str(tmp_path / "page.tsx"),
        report_output=str(tmp_path / "refinement_report.json"),
        on_compose=fake_compose,
        on_visual_qa=fake_qa,
    )
    assert result["status"] == "passed"
    assert result["iterations"] == 1


def test_runs_max_iterations_then_escalates(tmp_path: Path) -> None:
    ast_file = tmp_path / "layout_ast.json"
    ast_file.write_text('{"root": {"tag": "div", "classes": []}}', encoding="utf-8")

    def fake_compose(mod: Any, ast: Path, out: Path, title: Any) -> bool:
        return True

    calls = 0

    def fake_qa(i: int, url: str, ast: Path, out: Path, ref: Any, qa_dir: Path) -> dict:
        nonlocal calls
        calls += 1
        return {
            "status": "failed",
            "diff_score": 0.1,
            "dom_assertions": [],
            "discrepancies": ["padding mismatch"],
        }

    result = refinement.run_refinement_loop(
        page_url="http://localhost:3000",
        ast_path=str(ast_file),
        compose_output=str(tmp_path / "page.tsx"),
        max_iterations=2,
        report_output=str(tmp_path / "refinement_report.json"),
        on_compose=fake_compose,
        on_visual_qa=fake_qa,
    )
    assert result["status"] == "needs_human"
    assert result["iterations"] == 2
    assert "max iterations" in result["escalation_reason"].lower()
    assert calls == 2


def test_fails_fast_when_compose_fails(tmp_path: Path) -> None:
    ast_file = tmp_path / "layout_ast.json"
    ast_file.write_text('{"root": {"tag": "div", "classes": []}}', encoding="utf-8")

    def fake_compose(mod: Any, ast: Path, out: Path, title: Any) -> bool:
        return False

    result = refinement.run_refinement_loop(
        page_url="http://localhost:3000",
        ast_path=str(ast_file),
        compose_output=str(tmp_path / "page.tsx"),
        report_output=str(tmp_path / "refinement_report.json"),
        on_compose=fake_compose,
        on_visual_qa=lambda *args: {"status": "passed"},
    )
    assert result["status"] == "failed"
    assert "compose" in result["escalation_reason"].lower()


def test_blocked_visual_qa_triggers_refinement_then_human(tmp_path: Path) -> None:
    ast_file = tmp_path / "layout_ast.json"
    ast_file.write_text('{"root": {"tag": "div", "classes": []}}', encoding="utf-8")

    def fake_compose(mod: Any, ast: Path, out: Path, title: Any) -> bool:
        return True

    def fake_qa(i: int, url: str, ast: Path, out: Path, ref: Any, qa_dir: Path) -> dict:
        return {"status": "blocked", "discrepancies": ["Playwright not installed"]}

    result = refinement.run_refinement_loop(
        page_url="http://evil.example.com",
        ast_path=str(ast_file),
        compose_output=str(tmp_path / "page.tsx"),
        max_iterations=1,
        report_output=str(tmp_path / "refinement_report.json"),
        on_compose=fake_compose,
        on_visual_qa=fake_qa,
    )
    assert result["status"] == "needs_human"
    assert result["iterations"] == 1


def test_applies_deterministic_adjustments(tmp_path: Path) -> None:
    ast_file = tmp_path / "layout_ast.json"
    ast_file.write_text('{"root": {"tag": "div", "classes": []}}', encoding="utf-8")

    def fake_compose(mod: Any, ast: Path, out: Path, title: Any) -> bool:
        return True

    iterations = []

    def fake_qa(i: int, url: str, ast: Path, out: Path, ref: Any, qa_dir: Path) -> dict:
        iterations.append(i)
        if i == 1:
            return {
                "status": "failed",
                "diff_score": 0.12,
                "dom_assertions": [],
                "discrepancies": ["padding mismatch", "font size mismatch"],
            }
        return {"status": "passed", "diff_score": 0.02, "dom_assertions": [], "discrepancies": []}

    def fake_adjust(ast: dict, report: dict) -> list:
        ast["root"]["classes"].append("p-4")
        return [{"type": "padding", "reason": "padding mismatch"}]

    result = refinement.run_refinement_loop(
        page_url="http://localhost:3000",
        ast_path=str(ast_file),
        compose_output=str(tmp_path / "page.tsx"),
        max_iterations=3,
        report_output=str(tmp_path / "refinement_report.json"),
        on_compose=fake_compose,
        on_visual_qa=fake_qa,
        on_adjust=fake_adjust,
    )
    assert result["status"] == "passed"
    assert result["iterations"] == 2
    assert len(result["adjustments"]) >= 1
    assert result["adjustments"][0]["type"] == "padding"
    assert iterations == [1, 2]


def test_missing_ast_file_blocks_immediately(tmp_path: Path) -> None:
    result = refinement.run_refinement_loop(
        page_url="http://localhost:3000",
        ast_path=str(tmp_path / "missing.json"),
        compose_output=str(tmp_path / "page.tsx"),
        report_output=str(tmp_path / "refinement_report.json"),
    )
    assert result["status"] == "blocked"
    assert result["iterations"] == 0
    assert Path(tmp_path / "refinement_report.json").exists()


def test_dom_assertion_failure_triggers_refinement(tmp_path: Path) -> None:
    ast_file = tmp_path / "layout_ast.json"
    ast_file.write_text('{"root": {"tag": "div", "classes": []}}', encoding="utf-8")

    def fake_compose(mod: Any, ast: Path, out: Path, title: Any) -> bool:
        return True

    def fake_qa(i: int, url: str, ast: Path, out: Path, ref: Any, qa_dir: Path) -> dict:
        return {
            "status": "passed",
            "diff_score": 0.0,
            "dom_assertions": [
                {
                    "selector": "h1",
                    "expected": {"selector": "h1", "expected_count": 1},
                    "actual": {"count": 0},
                    "passed": False,
                    "discrepancies": ["expected 1 elements, found 0"],
                }
            ],
            "discrepancies": [],
        }

    result = refinement.run_refinement_loop(
        page_url="http://localhost:3000",
        ast_path=str(ast_file),
        compose_output=str(tmp_path / "page.tsx"),
        max_iterations=1,
        report_output=str(tmp_path / "refinement_report.json"),
        on_compose=fake_compose,
        on_visual_qa=fake_qa,
    )
    assert result["status"] == "needs_human"
    assert any(a["type"] == "add_node" for a in result["adjustments"])
