"""Tests for QualityEvaluator deterministic helpers and config."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from runtime.quality_evaluation import QualityEvaluationConfig, QualityEvaluator
from runtime.quality_evaluation.engine import _extract_json


pytestmark = [pytest.mark.core, pytest.mark.runtime]


def test_config_to_dict():
    cfg = QualityEvaluationConfig(min_score=7.5, max_refinement_rounds=3)
    data = cfg.to_dict()
    assert data["min_score"] == 7.5
    assert data["max_refinement_rounds"] == 3
    assert "relevance" in data["criteria"]


def test_extract_json_from_fence():
    text = 'Text\n```json\n{"overall_score": 8, "criteria": {"relevance": 9}, "feedback": "ok"}\n```'
    data = _extract_json(text)
    assert data["overall_score"] == 8
    assert data["criteria"]["relevance"] == 9


def test_extract_json_without_fence():
    text = 'Some {"overall_score": 7, "feedback": "ok"} trailing'
    data = _extract_json(text)
    assert data["overall_score"] == 7


def test_extract_json_invalid_returns_raw():
    text = "no json here"
    data = _extract_json(text)
    assert "raw_output" in data


@pytest.mark.asyncio
async def test_evaluate_parses_score_and_criteria():
    class DummyLLM:
        async def raw_chat_completion(self, *, system: str, user: str, temperature: float):
            return (
                '{"overall_score": 8.5, "criteria": {"relevance": 9, "completeness": 8}, '
                '"feedback": "Good but missing tests", "needs_refinement": false}'
            )

    evaluator = QualityEvaluator(llm=DummyLLM())  # type: ignore[arg-type]
    result = await evaluator.evaluate(
        brief="Build a blog",
        manifest="Use Next.js",
        codebase={"page.tsx": "export default function Page() {}"},
    )
    assert result.overall_score == 8.5
    assert result.criteria["relevance"] == 9.0
    assert result.criteria["completeness"] == 8.0
    assert result.feedback == "Good but missing tests"
    assert result.needs_refinement is False


@pytest.mark.asyncio
async def test_evaluate_flags_refinement_when_below_min_score():
    class DummyLLM:
        async def raw_chat_completion(self, *, system: str, user: str, temperature: float):
            return '{"overall_score": 4.0, "criteria": {}, "feedback": "Poor"}'

    evaluator = QualityEvaluator(
        llm=DummyLLM(),  # type: ignore[arg-type]
        config=QualityEvaluationConfig(min_score=6.0),
    )
    result = await evaluator.evaluate("brief", "manifest", {})
    assert result.needs_refinement is True


@pytest.mark.asyncio
async def test_evaluate_defaults_missing_criteria_to_zero():
    class DummyLLM:
        async def raw_chat_completion(self, *, system: str, user: str, temperature: float):
            return '{"overall_score": 7.0, "criteria": {"relevance": 7}, "feedback": "ok"}'

    evaluator = QualityEvaluator(llm=DummyLLM())  # type: ignore[arg-type]
    result = await evaluator.evaluate("brief", "manifest", {})
    assert result.criteria["relevance"] == 7.0
    assert result.criteria["completeness"] == 0.0
    assert result.criteria["code_quality"] == 0.0
    assert result.criteria["structure"] == 0.0
