from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class TemporalMemoryConfig:
    """Runtime configuration for the temporal memory graph layer.

    The temporal graph tracks facts that change over time and answers
    "what was true at time T". It is fully local: networkx graph in memory
    with a SQLite-backed edge store. No external API is required.
    """

    enabled: bool = field(
        default_factory=lambda: os.getenv("TEMPORAL_MEMORY_ENABLED", "true").lower()
        not in ("false", "0", "off", "no")
    )
    db_path: str = field(
        default_factory=lambda: os.getenv(
            "TEMPORAL_MEMORY_DB_PATH",
            str(Path(".temporal_memory") / "graph.db"),
        )
    )
    graph_filename: str = field(default="temporal_graph.json")
    max_nodes_in_memory: int = 10_000
    auto_persist: bool = True
    timezone: str = field(default_factory=lambda: os.getenv("TZ", "UTC"))

    @classmethod
    def from_env(cls, overrides: dict[str, Any] | None = None) -> "TemporalMemoryConfig":
        config = cls()
        if overrides:
            for key, value in overrides.items():
                if hasattr(config, key):
                    setattr(config, key, value)
        return config
