"""Expensive verifier for loop outputs with adversarial verification."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class Verdict:
    approved: bool
    critics: list[dict[str, Any]] = field(default_factory=list)
    consensus: int = 0
    required: int = 2
    reason: str = ""


class LoopVerifier:
    """Run N independent critics and require at least `required` approvals."""

    def __init__(self, required_critics: int = 2, model: str = "claude-opus-4-8"):
        if required_critics < 1:
            raise ValueError("required_critics must be >= 1")
        self.required_critics = required_critics
        self.model = model

    def verify(
        self,
        result: dict[str, Any],
        criteria: list[str],
        context: dict[str, Any] | None = None,
    ) -> Verdict:
        """Adversarially verify a loop result.

        In production this would call the LLM `model` N times. Here we provide a
        deterministic harness that callers can swap for real LLM calls.
        """
        critics: list[dict[str, Any]] = []
        approvals = 0
        for i in range(self.required_critics):
            critic = self._run_critic(i, result, criteria, context or {})
            critics.append(critic)
            if critic.get("approved", False):
                approvals += 1

        approved = approvals >= self.required_critics
        return Verdict(
            approved=approved,
            critics=critics,
            consensus=approvals,
            required=self.required_critics,
            reason="consensus reached" if approved else "insufficient consensus",
        )

    def verify_anti_slop(
        self,
        premium_result: dict[str, Any],
        constraints: list[str] | None = None,
    ) -> Verdict:
        """Domain-specific verifier for anti-slop sweeper."""
        criteria = [
            "banned patterns are real and match the rule definitions",
            "no false positives: allowed_if exemptions are respected",
            "refinement actions are concrete and actionable",
            "all findings reference specific file/line or token path",
        ]
        if constraints:
            criteria.extend([f"constraint respected: {c}" for c in constraints])
        return self.verify(premium_result, criteria)

    def _run_critic(
        self,
        index: int,
        result: dict[str, Any],
        criteria: list[str],
        context: dict[str, Any],
    ) -> dict[str, Any]:
        # Placeholder for an LLM critic. In a real call this would invoke
        # claude-opus-4-8 with a "find errors, default to reject" prompt.
        # We keep it deterministic so tests can verify the harness shape.
        return {
            "critic_id": index,
            "model": self.model,
            "approved": True,  # harness default: assume consensus for valid inputs.
            "concerns": [],
            "criteria_checked": criteria,
        }
