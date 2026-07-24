"""LLM Wiki runtime module.

Implements the Karpathy-method wiki as a two-sided memory layer:
- ingest (raw material → wiki pages)
- query (read wiki before answering)
- lint (find orphans, duplicates, stale pages)

Wiki pages live in memory/wiki/ next to MEMORY.md.
"""

from __future__ import annotations

from .config import WikiConfig
from .engine import (
    WikiEngine,
    WikiIngestResult,
    WikiLintResult,
    WikiPage,
    WikiQueryResult,
)

__all__ = [
    "WikiConfig",
    "WikiEngine",
    "WikiIngestResult",
    "WikiLintResult",
    "WikiPage",
    "WikiQueryResult",
]
