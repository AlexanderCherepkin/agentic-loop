"""Mixture of Agents (MOA) engine.

Runs a panel of advisors (≤5) and an Opus-level aggregator that synthesizes a
final answer from structured JSON advisor outputs.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from .llm_engine import LLMEngine


@dataclass(frozen=True)
class AdvisorConfig:
    """Configuration for a single MOA advisor."""

    advisor_id: str
    provider: str
    model: str
    system_prompt: str = ""
    temperature: float = 0.2
    max_tokens: int = 2048


@dataclass(frozen=True)
class MOAConfig:
    """Configuration for the MOA panel."""

    advisors: list[AdvisorConfig] = field(default_factory=list)
    aggregator_provider: str = "anthropic"
    aggregator_model: str = "claude-opus-4-8"
    aggregator_max_tokens: int = 4096
    max_advisors: int = 5
    min_valid_advisors: int = 2

    def __post_init__(self):
        if len(self.advisors) > self.max_advisors:
            raise ValueError(
                f"Too many advisors: {len(self.advisors)} > {self.max_advisors}"
            )
        if len(self.advisors) < self.min_valid_advisors:
            raise ValueError(
                f"Need at least {self.min_valid_advisors} advisors, got {len(self.advisors)}"
            )


@dataclass
class AdvisorResult:
    """Structured output from one advisor."""

    advisor_id: str
    model: str
    answer: str = ""
    confidence: float = 0.0
    reasoning: str = ""
    status: str = "valid"  # valid | invalid | empty
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "advisor_id": self.advisor_id,
            "model": self.model,
            "answer": self.answer,
            "confidence": self.confidence,
            "reasoning": self.reasoning,
            "status": self.status,
            "error": self.error,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AdvisorResult:
        return cls(
            advisor_id=str(data.get("advisor_id", "")),
            model=str(data.get("model", "")),
            answer=str(data.get("answer", "")),
            confidence=float(data.get("confidence", 0.0)),
            reasoning=str(data.get("reasoning", "")),
            status=str(data.get("status", "valid")),
            error=data.get("error"),
        )


@dataclass
class MOAOutput:
    """Final output from the MOA engine."""

    advisor_outputs: list[AdvisorResult] = field(default_factory=list)
    final_summary: str = ""
    dissent: list[dict[str, Any]] = field(default_factory=list)
    confidence: float = 0.0
    dry_run: bool = False


class MOAEngine:
    """Run advisors and aggregate their structured outputs."""

    _ADVISOR_SCHEMA = """You are an advisor in a Mixture of Agents panel. Answer the user's question and respond ONLY with valid JSON matching this exact shape:

{
  "answer": "your concise answer",
  "confidence": 0.0 to 1.0,
  "reasoning": "one-line reasoning for your answer"
}

Rules:
- No markdown outside the JSON.
- Confidence must be a number between 0 and 1.
- If uncertain, set confidence below 0.5 and explain why."""

    _AGGREGATOR_PROMPT = """You are a senior aggregator. You have received answers from a panel of advisors. Synthesize a final answer and highlight any dissent.

Respond ONLY with valid JSON matching this exact shape:

{
  "final_summary": "concise synthesized answer",
  "dissent": [
    {"advisor_id": "...", "summary": "how this answer differs"}
  ],
  "confidence": 0.0 to 1.0
}

Rules:
- No markdown outside the JSON.
- If advisors disagree, list dissent entries. If they agree, return an empty list.
- Confidence reflects how well the answers converge, not your personal certainty."""

    def __init__(self, config: MOAConfig, engine: LLMEngine | None = None):
        self.config = config
        self.engine = engine or LLMEngine()

    def dry_run(self, question: str) -> dict[str, Any]:
        """Return a cost/execution plan without making API calls."""
        plan = {
            "question": question,
            "advisor_count": len(self.config.advisors),
            "max_advisors": self.config.max_advisors,
            "aggregator": {
                "provider": self.config.aggregator_provider,
                "model": self.config.aggregator_model,
            },
            "advisors": [
                {
                    "advisor_id": a.advisor_id,
                    "provider": a.provider,
                    "model": a.model,
                    "estimated_tokens": a.max_tokens,
                }
                for a in self.config.advisors
            ],
            "estimated_total_tokens": sum(a.max_tokens for a in self.config.advisors)
            + self.config.aggregator_max_tokens,
            "dry_run": True,
        }
        return plan

    async def run(self, question: str, approved: bool = False) -> MOAOutput:
        """Run the MOA panel and aggregate results.

        Args:
            question: User question to pose to advisors.
            approved: Must be ``True`` after ``dry_run()`` review.

        Returns:
            ``MOAOutput`` with advisor outputs, final summary, and dissent list.
        """
        if not approved:
            return MOAOutput(dry_run=True)

        advisor_results = await self._run_advisors(question)
        valid_results = [r for r in advisor_results if r.status == "valid"]
        if len(valid_results) < self.config.min_valid_advisors:
            return MOAOutput(
                advisor_outputs=advisor_results,
                final_summary="Insufficient valid advisor responses to synthesize a summary.",
                dissent=[],
                confidence=0.0,
            )

        final = await self._aggregate(valid_results)
        return MOAOutput(
            advisor_outputs=advisor_results,
            final_summary=final.get("final_summary", ""),
            dissent=final.get("dissent", []),
            confidence=float(final.get("confidence", 0.0)),
        )

    async def _run_advisors(self, question: str) -> list[AdvisorResult]:
        import asyncio

        tasks = [self._call_advisor(a, question) for a in self.config.advisors]
        return await asyncio.gather(*tasks)

    async def _call_advisor(self, advisor: AdvisorConfig, question: str) -> AdvisorResult:
        system = advisor.system_prompt or self._ADVISOR_SCHEMA
        try:
            raw = await self.engine.raw_chat_completion(
                system=system,
                user=question,
                max_tokens=advisor.max_tokens,
                temperature=advisor.temperature,
            )
            parsed = self.engine._extract_json(raw)
            if parsed is None:
                return AdvisorResult(
                    advisor_id=advisor.advisor_id,
                    model=advisor.model,
                    status="invalid",
                    error="Advisor response was not valid JSON.",
                )
            if not isinstance(parsed, dict):
                return AdvisorResult(
                    advisor_id=advisor.advisor_id,
                    model=advisor.model,
                    status="invalid",
                    error="Advisor response was not a JSON object.",
                )
            answer = str(parsed.get("answer", "")).strip()
            if not answer:
                return AdvisorResult(
                    advisor_id=advisor.advisor_id,
                    model=advisor.model,
                    status="empty",
                    error="Advisor returned an empty answer.",
                )
            return AdvisorResult(
                advisor_id=advisor.advisor_id,
                model=advisor.model,
                answer=answer,
                confidence=float(parsed.get("confidence", 0.0)),
                reasoning=str(parsed.get("reasoning", "")),
                status="valid",
            )
        except Exception as exc:
            return AdvisorResult(
                advisor_id=advisor.advisor_id,
                model=advisor.model,
                status="invalid",
                error=str(exc),
            )

    async def _aggregate(self, results: list[AdvisorResult]) -> dict[str, Any]:
        payload = json.dumps([r.to_dict() for r in results], ensure_ascii=False, indent=2)
        try:
            raw = await self.engine.raw_chat_completion(
                system=self._AGGREGATOR_PROMPT,
                user=payload,
                max_tokens=self.config.aggregator_max_tokens,
                temperature=0.2,
            )
            parsed = self.engine._extract_json(raw) or {}
            if not isinstance(parsed, dict):
                return {
                    "final_summary": "Aggregator returned invalid JSON.",
                    "dissent": [],
                    "confidence": 0.0,
                }
            return {
                "final_summary": str(parsed.get("final_summary", "")),
                "dissent": parsed.get("dissent") or [],
                "confidence": float(parsed.get("confidence", 0.0)),
            }
        except Exception as exc:
            return {
                "final_summary": f"Aggregator failed: {exc}",
                "dissent": [],
                "confidence": 0.0,
            }
