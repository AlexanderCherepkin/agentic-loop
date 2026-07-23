from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class TemporalMemoryResult:
    """Structured output from a TemporalMemoryEngine operation."""

    status: str = "ok"
    operation: str = ""
    node_id: str | None = None
    query: str | None = None
    results: list[dict[str, Any]] = field(default_factory=list)
    contradictions: list[dict[str, Any]] = field(default_factory=list)
    summary: str | None = None
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "operation": self.operation,
            "node_id": self.node_id,
            "query": self.query,
            "results": self.results,
            "contradictions": self.contradictions,
            "summary": self.summary,
            "error": self.error,
        }
