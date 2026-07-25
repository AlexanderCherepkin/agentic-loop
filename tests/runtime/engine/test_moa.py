"""Tests for MOA engine: advisors, aggregator, conflict handling, fuzz."""

from __future__ import annotations

import asyncio
import random
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))

from runtime.engine.moa import AdvisorConfig, MOAConfig, MOAEngine, MOAOutput

pytestmark = [pytest.mark.core, pytest.mark.runtime]


class FakeLLMEngine:
    """Deterministic LLM double for MOA tests."""

    def __init__(self, responses: dict[str, str]):
        self._responses = responses
        self._call_count = 0

    async def raw_chat_completion(
        self, system: str, user: str, max_tokens: int | None = None, temperature: float | None = None, **kwargs
    ) -> str:
        key = f"call_{self._call_count}"
        self._call_count += 1
        return self._responses.get(key, '{"answer": "default", "confidence": 0.5, "reasoning": "default"}')

    def _extract_json(self, text: str):
        import json

        text = text.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            lines = lines[1:] if lines[0].startswith("```") else lines
            if lines and lines[-1].startswith("```"):
                lines = lines[:-1]
            text = "\n".join(lines)
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            if "{" in text and "}" in text:
                try:
                    start = text.index("{")
                    end = text.rindex("}") + 1
                    return json.loads(text[start:end])
                except (json.JSONDecodeError, ValueError):
                    pass
            return None


def _make_engine(responses: dict[str, str]) -> MOAEngine:
    config = MOAConfig(
        advisors=[
            AdvisorConfig(advisor_id="a1", provider="anthropic", model="claude-sonnet-5"),
            AdvisorConfig(advisor_id="a2", provider="openai", model="gpt-4o-mini"),
            AdvisorConfig(advisor_id="a3", provider="google", model="gemini-flash-latest"),
        ],
    )
    return MOAEngine(config, engine=FakeLLMEngine(responses))


class TestMOAConfig:
    def test_max_advisors_enforced(self):
        with pytest.raises(ValueError):
            MOAConfig(
                advisors=[
                    AdvisorConfig(advisor_id=f"a{i}", provider="anthropic", model="x")
                    for i in range(6)
                ]
            )

    def test_min_valid_advisors_enforced(self):
        with pytest.raises(ValueError):
            MOAConfig(advisors=[])


class TestMOADryRun:
    def test_dry_run_returns_plan(self):
        engine = _make_engine({})
        plan = engine.dry_run("What is 2+2?")
        assert plan["dry_run"] is True
        assert plan["advisor_count"] == 3
        assert plan["estimated_total_tokens"] > 0
        assert plan["aggregator"]["model"] == "claude-opus-4-8"

    def test_run_without_approval_is_dry(self):
        engine = _make_engine({})
        output = asyncio.run(engine.run("q", approved=False))
        assert output.dry_run is True


class TestMOAAdvisors:
    def test_valid_advisors_produce_summary(self):
        responses = {
            "call_0": '{"answer": "4", "confidence": 0.9, "reasoning": "math"}',
            "call_1": '{"answer": "4", "confidence": 0.8, "reasoning": "addition"}',
            "call_2": '{"answer": "4", "confidence": 0.85, "reasoning": "simple"}',
            "call_3": '{"final_summary": "The answer is 4.", "dissent": [], "confidence": 0.95}',
        }
        engine = _make_engine(responses)
        output = asyncio.run(engine.run("What is 2+2?", approved=True))
        assert output.final_summary == "The answer is 4."
        assert output.dissent == []
        assert output.confidence == 0.95
        assert all(r.status == "valid" for r in output.advisor_outputs)

    def test_conflicting_advisors_surface_dissent(self):
        responses = {
            "call_0": '{"answer": "4", "confidence": 0.9, "reasoning": "math"}',
            "call_1": '{"answer": "5", "confidence": 0.6, "reasoning": "mistake"}',
            "call_2": '{"answer": "4", "confidence": 0.85, "reasoning": "simple"}',
            "call_3": '{"final_summary": "Most advisors say 4.", "dissent": [{"advisor_id": "a2", "summary": "answered 5 instead of 4"}], "confidence": 0.7}',
        }
        engine = _make_engine(responses)
        output = asyncio.run(engine.run("What is 2+2?", approved=True))
        assert "4" in output.final_summary
        assert any(d["advisor_id"] == "a2" for d in output.dissent)

    def test_broken_json_marked_invalid(self):
        responses = {
            "call_0": '{"answer": "4", "confidence": 0.9, "reasoning": "math"}',
            "call_1": "not json {{",
            "call_2": '{"answer": "4", "confidence": 0.85, "reasoning": "simple"}',
            "call_3": '{"final_summary": "The answer is 4.", "dissent": [], "confidence": 0.9}',
        }
        fake = FakeLLMEngine(responses)
        config = MOAConfig(
            advisors=[
                AdvisorConfig(advisor_id="a1", provider="anthropic", model="claude-sonnet-5"),
                AdvisorConfig(advisor_id="a2", provider="openai", model="gpt-4o-mini"),
                AdvisorConfig(advisor_id="a3", provider="google", model="gemini-flash-latest"),
            ],
        )
        engine = MOAEngine(config, engine=fake)
        output = asyncio.run(engine.run("What is 2+2?", approved=True))
        invalid = [r for r in output.advisor_outputs if r.status == "invalid"]
        assert len(invalid) == 1
        assert invalid[0].advisor_id == "a2"

    def test_empty_answer_marked_empty(self):
        responses = {
            "call_0": '{"answer": "", "confidence": 0.9, "reasoning": ""}',
            "call_1": '{"answer": "4", "confidence": 0.8, "reasoning": "addition"}',
            "call_2": '{"answer": "4", "confidence": 0.85, "reasoning": "simple"}',
            "call_3": '{"final_summary": "The answer is 4.", "dissent": [], "confidence": 0.85}',
        }
        engine = _make_engine(responses)
        output = asyncio.run(engine.run("What is 2+2?", approved=True))
        empty = [r for r in output.advisor_outputs if r.status == "empty"]
        assert len(empty) == 1
        assert empty[0].advisor_id == "a1"

    def test_insufficient_valid_returns_error(self):
        responses = {
            "call_0": "not json",
            "call_1": "also bad",
            "call_2": '{"answer": "4", "confidence": 0.8, "reasoning": "ok"}',
        }
        engine = _make_engine(responses)
        output = asyncio.run(engine.run("What is 2+2?", approved=True))
        assert "Insufficient valid advisor responses" in output.final_summary
        assert output.confidence == 0.0


class TestMOAFuzz:
    """Hand-crafted fuzz for the MOA aggregator and advisor parser."""

    def test_random_advisor_outputs_never_crash(self):
        rng = random.Random(42)
        valid_answers = ["4", "5", "approximately 4", "four"]
        for _ in range(100):
            responses: dict[str, str] = {}
            valid_count = 0
            for i in range(3):
                kind = rng.choice(["valid", "broken", "empty"])
                if kind == "valid":
                    ans = rng.choice(valid_answers)
                    conf = rng.random()
                    responses[f"call_{i}"] = (
                        f'{{"answer": "{ans}", "confidence": {conf:.2f}, "reasoning": "r{i}"}}'
                    )
                    valid_count += 1
                elif kind == "broken":
                    responses[f"call_{i}"] = rng.choice(
                        ['{"answer":', "not json", "{{bad}}", "", "null"]
                    )
                else:
                    responses[f"call_{i}"] = '{"answer": "", "confidence": 0.0, "reasoning": ""}'

            if valid_count >= 2:
                responses["call_3"] = '{"final_summary": "Summary.", "dissent": [], "confidence": 0.5}'
            engine = _make_engine(responses)
            output = asyncio.run(engine.run("fuzz", approved=True))
            assert isinstance(output, MOAOutput)
            assert len(output.advisor_outputs) == 3
