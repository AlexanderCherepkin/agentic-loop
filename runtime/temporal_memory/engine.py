from __future__ import annotations

import json
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any
from uuid import uuid4

from .config import TemporalMemoryConfig
from .result import TemporalMemoryResult


class TemporalMemoryEngine:
    """Deterministic temporal memory graph for facts that change over time.

    Nodes represent facts, states, events, commitments, or profile fields.
    Edges carry a temporal validity window and a relationship type such as
    `replaces`, `supersedes`, `causes`, or `contradicts`. The engine can
    answer "what was true at time T" by following the replacement chain up
    to the requested timestamp.

    Persistence is optional. If `db_path` is writable, facts and edges are
    stored in SQLite; otherwise the engine falls back to an in-memory
    graph and keeps working.
    """

    _instances: dict[str, "TemporalMemoryEngine"] = {}
    _lock = threading.Lock()

    def __new__(cls, config: TemporalMemoryConfig | None = None) -> "TemporalMemoryEngine":
        config = config or TemporalMemoryConfig()
        key = config.db_path
        if key not in cls._instances:
            with cls._lock:
                if key not in cls._instances:
                    cls._instances[key] = super().__new__(cls)
                    cls._instances[key]._initialized = False
        return cls._instances[key]

    def __init__(self, config: TemporalMemoryConfig | None = None):
        if getattr(self, "_initialized", False):
            return
        self.config = config or TemporalMemoryConfig()
        self._graph: dict[str, dict[str, Any]] = {}
        self._edges: list[dict[str, Any]] = []
        self._db_ok = False
        self._ensure_db()
        self._initialized = True

    def _ensure_db(self) -> None:
        if not self.config.enabled:
            return
        try:
            db = Path(self.config.db_path)
            db.parent.mkdir(parents=True, exist_ok=True)
            self._conn = sqlite3.connect(str(db), check_same_thread=False)
            self._conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS nodes (
                    id TEXT PRIMARY KEY,
                    label TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    content TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    expires_at REAL,
                    metadata TEXT
                );
                CREATE TABLE IF NOT EXISTS edges (
                    id TEXT PRIMARY KEY,
                    source TEXT NOT NULL,
                    target TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    valid_from REAL NOT NULL,
                    valid_until REAL,
                    metadata TEXT,
                    FOREIGN KEY (source) REFERENCES nodes(id),
                    FOREIGN KEY (target) REFERENCES nodes(id)
                );
                CREATE INDEX IF NOT EXISTS idx_nodes_kind ON nodes(kind);
                CREATE INDEX IF NOT EXISTS idx_edges_source ON edges(source);
                CREATE INDEX IF NOT EXISTS idx_edges_target ON edges(target);
                """
            )
            self._conn.commit()
            self._db_ok = True
            self._load_from_db()
        except Exception as exc:
            self._db_ok = False
            self._last_db_error = str(exc)
            self._conn = None

    def _load_from_db(self) -> None:
        if not self._db_ok or self._conn is None:
            return
        cursor = self._conn.cursor()
        for row in cursor.execute("SELECT id, label, kind, content, created_at, expires_at, metadata FROM nodes"):
            self._graph[row[0]] = {
                "id": row[0],
                "label": row[1],
                "kind": row[2],
                "content": row[3],
                "created_at": row[4],
                "expires_at": row[5],
                "metadata": json.loads(row[6]) if row[6] else {},
            }
        for row in cursor.execute(
            "SELECT id, source, target, kind, valid_from, valid_until, metadata FROM edges"
        ):
            self._edges.append({
                "id": row[0],
                "source": row[1],
                "target": row[2],
                "kind": row[3],
                "valid_from": row[4],
                "valid_until": row[5],
                "metadata": json.loads(row[6]) if row[6] else {},
            })

    def _persist_node(self, node: dict[str, Any]) -> None:
        if not self._db_ok or self._conn is None:
            return
        self._conn.execute(
            """
            INSERT OR REPLACE INTO nodes (id, label, kind, content, created_at, expires_at, metadata)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                node["id"],
                node["label"],
                node["kind"],
                node["content"],
                node["created_at"],
                node.get("expires_at"),
                json.dumps(node.get("metadata", {}), ensure_ascii=False),
            ),
        )
        self._conn.commit()

    def _persist_edge(self, edge: dict[str, Any]) -> None:
        if not self._db_ok or self._conn is None:
            return
        self._conn.execute(
            """
            INSERT OR REPLACE INTO edges (id, source, target, kind, valid_from, valid_until, metadata)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                edge["id"],
                edge["source"],
                edge["target"],
                edge["kind"],
                edge["valid_from"],
                edge.get("valid_until"),
                json.dumps(edge.get("metadata", {}), ensure_ascii=False),
            ),
        )
        self._conn.commit()

    def record_fact(
        self,
        label: str,
        content: str,
        kind: str = "fact",
        valid_from: float | None = None,
        valid_until: float | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> TemporalMemoryResult:
        """Record a new fact node in the temporal graph."""
        if not self.config.enabled:
            return TemporalMemoryResult(
                status="disabled",
                operation="record_fact",
                error="Temporal memory is disabled.",
            )
        now = time.time()
        node_id = str(uuid4())
        node = {
            "id": node_id,
            "label": label,
            "kind": kind,
            "content": content,
            "created_at": now,
            "expires_at": valid_until,
            "metadata": metadata or {},
        }
        if valid_from is not None:
            node["metadata"]["valid_from"] = valid_from
        self._graph[node_id] = node
        self._persist_node(node)
        return TemporalMemoryResult(
            status="ok",
            operation="record_fact",
            node_id=node_id,
            results=[node],
        )

    def record_state_change(
        self,
        label: str,
        new_content: str,
        previous_node_id: str | None = None,
        kind: str = "state",
        valid_from: float | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> TemporalMemoryResult:
        """Record a new state that replaces or supersedes an older state."""
        prev = self._graph.get(previous_node_id) if previous_node_id else None
        now = time.time()
        # Add a tiny epsilon when no explicit valid_from is given so that the
        # new node is strictly later than any timestamp captured just before
        # the call, even on platforms with coarse time resolution.
        if valid_from is None:
            effective_from = now + 1e-6
        else:
            effective_from = valid_from
        if prev is not None and effective_from <= prev["created_at"]:
            effective_from = prev["created_at"] + 1e-6
        result = self.record_fact(
            label, new_content, kind=kind, valid_from=effective_from, metadata=metadata
        )
        if result.status != "ok":
            return result
        new_node_id = result.node_id
        assert new_node_id is not None
        new_node = self._graph[new_node_id]
        # Snap the new node to the effective transition time.
        if new_node["created_at"] < effective_from:
            new_node["created_at"] = effective_from
            if new_node["metadata"].get("valid_from") is None:
                new_node["metadata"]["valid_from"] = effective_from
            self._persist_node(new_node)
        edge = {
            "id": str(uuid4()),
            "source": previous_node_id,
            "target": new_node_id,
            "kind": "replaces",
            "valid_from": effective_from,
            "valid_until": None,
            "metadata": {"reason": metadata.get("reason") if metadata else None},
        }
        self._edges.append(edge)
        self._persist_edge(edge)
        # Mark the previous node as expired at the transition time.
        if prev and not prev.get("expires_at"):
            prev["expires_at"] = effective_from
            self._persist_node(prev)
        return TemporalMemoryResult(
            status="ok",
            operation="record_state_change",
            node_id=new_node_id,
            results=[new_node],
        )

    def query_at_time(
        self,
        label: str,
        at_time: float,
        kind: str | None = None,
    ) -> TemporalMemoryResult:
        """Return the most current fact/state matching `label` as of `at_time`."""
        if not self.config.enabled:
            return TemporalMemoryResult(
                status="disabled",
                operation="query_at_time",
                query=label,
                error="Temporal memory is disabled.",
            )
        candidates = [
            node
            for node in self._graph.values()
            if node["label"] == label
            and node["created_at"] <= at_time
            and (node.get("expires_at") is None or node["expires_at"] > at_time)
        ]
        if kind:
            candidates = [n for n in candidates if n["kind"] == kind]
        if not candidates:
            return TemporalMemoryResult(
                status="not_found",
                operation="query_at_time",
                query=label,
                results=[],
            )
        # Follow replacement chain forward while target is still <= at_time.
        current = max(candidates, key=lambda n: n["created_at"])
        improved = True
        while improved:
            improved = False
            for edge in self._edges:
                if (
                    edge["source"] == current["id"]
                    and edge["kind"] in ("replaces", "supersedes")
                    and edge["valid_from"] <= at_time
                    and (edge.get("valid_until") is None or edge["valid_until"] > at_time)
                ):
                    target = self._graph.get(edge["target"])
                    if target and target["created_at"] <= at_time:
                        current = target
                        improved = True
                        break
        return TemporalMemoryResult(
            status="ok",
            operation="query_at_time",
            query=label,
            results=[current],
        )

    def query_evolution(
        self,
        label: str,
        kind: str | None = None,
    ) -> TemporalMemoryResult:
        """Return the full replacement chain for a label, oldest first."""
        nodes = [n for n in self._graph.values() if n["label"] == label and (not kind or n["kind"] == kind)]
        if not nodes:
            return TemporalMemoryResult(
                status="not_found",
                operation="query_evolution",
                query=label,
                results=[],
            )
        # Build a simple chain via replaces edges.
        by_created = sorted(nodes, key=lambda n: n["created_at"])
        chain: list[dict[str, Any]] = []
        for node in by_created:
            entry = dict(node)
            entry["replaced_by"] = [
                edge["target"]
                for edge in self._edges
                if edge["source"] == node["id"] and edge["kind"] in ("replaces", "supersedes")
            ]
            chain.append(entry)
        return TemporalMemoryResult(
            status="ok",
            operation="query_evolution",
            query=label,
            results=chain,
        )

    def find_contradictions(
        self,
        label_prefix: str | None = None,
    ) -> TemporalMemoryResult:
        """Find pairs of contradicting facts that overlap in validity."""
        if not self.config.enabled:
            return TemporalMemoryResult(
                status="disabled",
                operation="find_contradictions",
                error="Temporal memory is disabled.",
            )
        contradictions: list[dict[str, Any]] = []
        for edge in self._edges:
            if edge["kind"] == "contradicts":
                source = self._graph.get(edge["source"])
                target = self._graph.get(edge["target"])
                if source and target:
                    if label_prefix is None or source["label"].startswith(label_prefix) or target["label"].startswith(label_prefix):
                        contradictions.append({
                            "edge_id": edge["id"],
                            "source": source,
                            "target": target,
                            "valid_from": edge["valid_from"],
                            "valid_until": edge.get("valid_until"),
                        })
        return TemporalMemoryResult(
            status="ok",
            operation="find_contradictions",
            contradictions=contradictions,
            results=contradictions,
        )

    def add_relation(
        self,
        source_id: str,
        target_id: str,
        kind: str,
        valid_from: float | None = None,
        valid_until: float | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> TemporalMemoryResult:
        """Add a typed temporal relation between two existing nodes."""
        if source_id not in self._graph or target_id not in self._graph:
            return TemporalMemoryResult(
                status="error",
                operation="add_relation",
                error="Source or target node not found.",
            )
        now = time.time()
        edge = {
            "id": str(uuid4()),
            "source": source_id,
            "target": target_id,
            "kind": kind,
            "valid_from": valid_from or now,
            "valid_until": valid_until,
            "metadata": metadata or {},
        }
        self._edges.append(edge)
        self._persist_edge(edge)
        return TemporalMemoryResult(
            status="ok",
            operation="add_relation",
            results=[edge],
        )

    def consolidate(
        self,
        label: str,
    ) -> TemporalMemoryResult:
        """Collapse a chain of replaced states into a summary node."""
        evo = self.query_evolution(label)
        if evo.status != "ok" or not evo.results:
            return evo
        chain = evo.results
        summary = {
            "label": label,
            "count": len(chain),
            "first_at": chain[0]["created_at"],
            "last_at": chain[-1]["created_at"],
            "current": chain[-1]["content"],
            "history": [{"at": n["created_at"], "content": n["content"]} for n in chain],
        }
        return TemporalMemoryResult(
            status="ok",
            operation="consolidate",
            query=label,
            results=[summary],
            summary=json.dumps(summary, ensure_ascii=False),
        )

    def stats(self) -> dict[str, Any]:
        return {
            "enabled": self.config.enabled,
            "db_ok": self._db_ok,
            "db_path": self.config.db_path,
            "node_count": len(self._graph),
            "edge_count": len(self._edges),
            "last_db_error": getattr(self, "_last_db_error", None),
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "enabled": self.config.enabled,
            "db_path": self.config.db_path,
            "node_count": len(self._graph),
            "edge_count": len(self._edges),
        }
