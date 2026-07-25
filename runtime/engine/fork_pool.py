"""Local fork pool for background worker tasks.

Fork workers run inside the same terminal process as `asyncio.Task`s. They are
not exposed via MCP or web. Human approval is required before the pool starts.
"""

from __future__ import annotations

import asyncio
import json
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any


class WorkerStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    ERROR = "error"
    CANCELLED = "cancelled"


@dataclass
class WorkerResult:
    worker_id: str
    status: WorkerStatus
    output: Any = None
    error: str | None = None
    started_at: float | None = None
    finished_at: float | None = None


@dataclass
class WorkerSpec:
    """Description of a single fork worker."""

    task_description: str
    func: Callable[[], Any]
    worker_id: str = field(default_factory=lambda: f"worker_{uuid.uuid4().hex[:8]}")


class ForkPool:
    """Manage a bounded set of background worker tasks.

    Args:
        max_workers: Hard concurrency limit. Defaults to 8.
        dump_dir: Optional directory to dump worker results as JSON.
    """

    DEFAULT_MAX_WORKERS = 8

    def __init__(self, max_workers: int | None = None, dump_dir: str | Path | None = None):
        self.max_workers = max_workers or self.DEFAULT_MAX_WORKERS
        self._specs: list[WorkerSpec] = []
        self._results: dict[str, WorkerResult] = {}
        self._tasks: dict[str, asyncio.Task[Any]] = {}
        self._dump_dir = Path(dump_dir) if dump_dir else None

    @property
    def results(self) -> dict[str, WorkerResult]:
        """Read-only view of current worker results."""
        return dict(self._results)

    def add(self, task_description: str, func: Callable[[], Any], worker_id: str | None = None) -> str:
        """Add a worker spec to the pool without running it."""
        spec = WorkerSpec(
            task_description=task_description,
            func=func,
            worker_id=worker_id or f"worker_{uuid.uuid4().hex[:8]}",
        )
        if len(self._specs) >= self.max_workers:
            raise RuntimeError(
                f"Fork pool worker limit reached: {self.max_workers}. "
                "Refuse to spawn more workers to avoid token burn."
            )
        self._specs.append(spec)
        self._results[spec.worker_id] = WorkerResult(
            worker_id=spec.worker_id, status=WorkerStatus.PENDING
        )
        return spec.worker_id

    def status_table(self) -> list[dict[str, Any]]:
        """Return a list of worker status rows for the TUI panel."""
        return [
            {
                "worker_id": spec.worker_id,
                "description": spec.task_description,
                "status": self._results.get(spec.worker_id, WorkerResult(spec.worker_id, WorkerStatus.PENDING)).status,
                "elapsed": self._elapsed(spec.worker_id),
            }
            for spec in self._specs
        ]

    def _elapsed(self, worker_id: str) -> float:
        result = self._results.get(worker_id)
        if result is None:
            return 0.0
        if result.finished_at is not None and result.started_at is not None:
            return result.finished_at - result.started_at
        if result.started_at is not None:
            return time.perf_counter() - result.started_at
        return 0.0

    async def run(self, approved: bool = False) -> dict[str, WorkerResult]:
        """Run all workers concurrently.

        Args:
            approved: Must be ``True`` after human approval. If ``False``,
                the pool refuses to start.
        """
        if not approved:
            raise RuntimeError("Fork pool start denied: human approval required.")
        if not self._specs:
            return {}

        # Start all tasks at once; they will be bound by the max_workers limit
        # enforced at add() time.
        for spec in self._specs:
            task = asyncio.create_task(self._run_one(spec), name=spec.worker_id)
            self._tasks[spec.worker_id] = task

        if self._tasks:
            await asyncio.gather(*self._tasks.values(), return_exceptions=True)

        self._dump_results()
        return dict(self._results)

    async def _run_one(self, spec: WorkerSpec) -> WorkerResult:
        started = time.perf_counter()
        result = WorkerResult(
            worker_id=spec.worker_id,
            status=WorkerStatus.RUNNING,
            started_at=started,
        )
        self._results[spec.worker_id] = result
        try:
            if asyncio.iscoroutinefunction(spec.func):
                output = await spec.func()
            else:
                output = spec.func()
                if asyncio.iscoroutine(output):
                    output = await output
            result = WorkerResult(
                worker_id=spec.worker_id,
                status=WorkerStatus.DONE,
                output=output,
                started_at=started,
                finished_at=time.perf_counter(),
            )
        except asyncio.CancelledError:
            result = WorkerResult(
                worker_id=spec.worker_id,
                status=WorkerStatus.CANCELLED,
                started_at=started,
                finished_at=time.perf_counter(),
            )
            self._results[spec.worker_id] = result
            raise
        except Exception as exc:
            result = WorkerResult(
                worker_id=spec.worker_id,
                status=WorkerStatus.ERROR,
                error=str(exc),
                started_at=started,
                finished_at=time.perf_counter(),
            )
        self._results[spec.worker_id] = result
        return result

    async def cancel_all(self) -> None:
        """Cancel all running workers."""
        for task in self._tasks.values():
            if not task.done():
                task.cancel()
        if self._tasks:
            await asyncio.gather(*self._tasks.values(), return_exceptions=True)

    def _dump_results(self) -> None:
        if self._dump_dir is None:
            return
        self._dump_dir.mkdir(parents=True, exist_ok=True)
        path = self._dump_dir / f"fork_{int(time.time())}.json"
        payload = [
            {
                "worker_id": r.worker_id,
                "status": r.status,
                "output": r.output,
                "error": r.error,
                "started_at": r.started_at,
                "finished_at": r.finished_at,
            }
            for r in self._results.values()
        ]
        with path.open("w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, default=str)

    def reset(self) -> None:
        """Clear specs and results for a fresh pool."""
        self._specs.clear()
        self._results.clear()
        self._tasks.clear()
