from __future__ import annotations

import logging
import sqlite3
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .config import CostTrackingConfig, _estimate_tokens
from ..observability.metrics import MetricsCollector

logger = logging.getLogger(__name__)


@dataclass
class CostEstimate:
    model: str
    agent: str
    input_tokens: int
    output_tokens: int
    input_cost: float
    output_cost: float
    total_cost: float
    currency: str = "USD"


class CostBackend(ABC):
    @abstractmethod
    def record_spend(
        self,
        scope: str,
        model: str,
        agent: str,
        input_tokens: int,
        output_tokens: int,
        cost: float,
        currency: str = "USD",
    ) -> None:
        ...

    @abstractmethod
    def get_spent(self, scope: str, window_seconds: int | None = None) -> float:
        ...

    @abstractmethod
    def set_budget(self, scope: str, limit: float, currency: str = "USD") -> None:
        ...

    @abstractmethod
    def get_budget(self, scope: str) -> dict[str, Any] | None:
        ...

    @abstractmethod
    def list_scopes(self, limit: int = 100, offset: int = 0) -> list[dict[str, Any]]:
        ...

    @abstractmethod
    def get_usage_report(
        self,
        scope: str | None = None,
        window_seconds: int | None = None,
    ) -> dict[str, Any]:
        ...


class SQLiteCostBackend(CostBackend):
    def __init__(self, db_path: Path | str) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._ensure_tables()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _ensure_tables(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS cost_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    scope TEXT NOT NULL,
                    model TEXT NOT NULL,
                    agent TEXT NOT NULL,
                    input_tokens INTEGER NOT NULL,
                    output_tokens INTEGER NOT NULL,
                    cost REAL NOT NULL,
                    currency TEXT NOT NULL DEFAULT 'USD',
                    timestamp INTEGER NOT NULL
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_cost_events_scope_ts ON cost_events(scope, timestamp)"
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS budgets (
                    scope TEXT PRIMARY KEY,
                    limit_amount REAL NOT NULL,
                    currency TEXT NOT NULL DEFAULT 'USD',
                    updated_at INTEGER NOT NULL
                )
                """
            )

    def record_spend(
        self,
        scope: str,
        model: str,
        agent: str,
        input_tokens: int,
        output_tokens: int,
        cost: float,
        currency: str = "USD",
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO cost_events (scope, model, agent, input_tokens, output_tokens, cost, currency, timestamp)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (scope, model, agent, input_tokens, output_tokens, cost, currency, int(time.time())),
            )
        logger.info("Cost spend recorded for %s: %.6f %s", scope, cost, currency)

    def get_spent(self, scope: str, window_seconds: int | None = None) -> float:
        query = "SELECT SUM(cost) as total FROM cost_events WHERE scope = ?"
        params: list[Any] = [scope]
        if window_seconds:
            cutoff = int(time.time()) - window_seconds
            query += " AND timestamp >= ?"
            params.append(cutoff)
        with self._connect() as conn:
            row = conn.execute(query, params).fetchone()
        return row["total"] or 0.0

    def set_budget(self, scope: str, limit: float, currency: str = "USD") -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO budgets (scope, limit_amount, currency, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(scope) DO UPDATE SET
                    limit_amount=excluded.limit_amount,
                    currency=excluded.currency,
                    updated_at=excluded.updated_at
                """,
                (scope, limit, currency, int(time.time())),
            )

    def get_budget(self, scope: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM budgets WHERE scope = ?", (scope,)).fetchone()
        if row is None:
            return None
        return {
            "scope": row["scope"],
            "limit": row["limit_amount"],
            "currency": row["currency"],
            "updated_at": row["updated_at"],
        }

    def list_scopes(self, limit: int = 100, offset: int = 0) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT scope, SUM(cost) as spent, currency
                FROM cost_events
                GROUP BY scope, currency
                ORDER BY spent DESC
                LIMIT ? OFFSET ?
                """,
                (limit, offset),
            ).fetchall()
        return [
            {
                "scope": row["scope"],
                "spent": row["spent"] or 0.0,
                "currency": row["currency"],
            }
            for row in rows
        ]

    def get_usage_report(
        self,
        scope: str | None = None,
        window_seconds: int | None = None,
    ) -> dict[str, Any]:
        where: list[str] = []
        params: list[Any] = []
        if scope:
            where.append("scope = ?")
            params.append(scope)
        if window_seconds:
            where.append("timestamp >= ?")
            params.append(int(time.time()) - window_seconds)
        query = (
            "SELECT SUM(cost) as total, SUM(input_tokens) as input_tokens, "
            "SUM(output_tokens) as output_tokens, COUNT(*) as calls FROM cost_events"
        )
        if where:
            query += " WHERE " + " AND ".join(where)
        with self._connect() as conn:
            row = conn.execute(query, params).fetchone()
        return {
            "scope": scope,
            "window_seconds": window_seconds,
            "total_cost": row["total"] or 0.0,
            "input_tokens": row["input_tokens"] or 0,
            "output_tokens": row["output_tokens"] or 0,
            "calls": row["calls"] or 0,
        }


class CostTrackingEngine:
    """Estimate and record LLM call costs, with optional per-scope budgets."""

    def __init__(self, config: CostTrackingConfig | None = None):
        self.config = config or CostTrackingConfig()
        self._costs = self.config.load_costs()
        self._backend = SQLiteCostBackend(self.config.db_path)
        self._metrics = MetricsCollector()

    def get_model_cost(self, model: str) -> dict[str, float]:
        return self._costs.get(model) or self._costs.get("default", {"input": 0.0, "output": 0.0})

    def estimate(
        self,
        model: str,
        input_text: str,
        output_text: str,
        agent: str = "agent",
    ) -> CostEstimate:
        rates = self.get_model_cost(model)
        input_tokens = _estimate_tokens(input_text)
        output_tokens = _estimate_tokens(output_text)
        input_cost = rates.get("input", 0.0) * input_tokens / 1000.0
        output_cost = rates.get("output", 0.0) * output_tokens / 1000.0
        return CostEstimate(
            model=model,
            agent=agent,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            input_cost=input_cost,
            output_cost=output_cost,
            total_cost=input_cost + output_cost,
            currency=self.config.default_currency,
        )

    def record(self, scope: str, estimate: CostEstimate) -> None:
        self._backend.record_spend(
            scope=scope,
            model=estimate.model,
            agent=estimate.agent,
            input_tokens=estimate.input_tokens,
            output_tokens=estimate.output_tokens,
            cost=estimate.total_cost,
            currency=estimate.currency,
        )
        self._metrics.counter("cost_per_scope_usd", "Total estimated LLM cost per scope").inc(
            estimate.total_cost
        )

    def record_llm_response(
        self,
        scope: str,
        model: str,
        system_prompt: str,
        user_message: str,
        response_text: str,
        agent: str = "agent",
    ) -> CostEstimate:
        estimate = self.estimate(
            model=model,
            input_text=f"{system_prompt}\n\n{user_message}",
            output_text=response_text,
            agent=agent,
        )
        self.record(scope=scope, estimate=estimate)
        return estimate

    def check_budget(self, scope: str, extra_cost: float = 0.0) -> dict[str, Any]:
        budget = self._backend.get_budget(scope)
        spent = self._backend.get_spent(scope)
        allowed = True
        limit: float | None = None
        if budget is not None:
            limit = budget["limit"]
            if spent + extra_cost > limit:
                allowed = False
        return {
            "scope": scope,
            "spent": spent,
            "limit": limit,
            "currency": budget["currency"] if budget else self.config.default_currency,
            "allowed": allowed,
            "remaining": (limit - spent) if limit is not None else None,
        }

    def set_budget(self, scope: str, limit: float, currency: str | None = None) -> None:
        self._backend.set_budget(scope, limit, currency or self.config.default_currency)

    def get_report(self, scope: str | None = None, window_seconds: int | None = None) -> dict[str, Any]:
        return self._backend.get_usage_report(scope=scope, window_seconds=window_seconds)

    def list_scopes(self, limit: int = 100, offset: int = 0) -> list[dict[str, Any]]:
        return self._backend.list_scopes(limit=limit, offset=offset)
