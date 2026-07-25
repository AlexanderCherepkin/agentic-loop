"""Tests for ForkPool background workers and TUI panel."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))

from runtime.engine.fork_pool import ForkPool, WorkerStatus

pytestmark = [pytest.mark.core, pytest.mark.runtime]


async def _sample_async_worker(value: int) -> int:
    await asyncio.sleep(0.01)
    return value * 2


def _sample_sync_worker(value: int) -> int:
    return value + 1


pytestmark.append(pytest.mark.asyncio(loop_scope="function"))


class TestForkPool:
    async def test_add_worker_returns_id(self):
        pool = ForkPool()
        wid = pool.add("double 5", lambda: _sample_sync_worker(5))
        assert wid.startswith("worker_")
        assert len(pool._specs) == 1

    async def test_worker_limit_raises(self):
        pool = ForkPool(max_workers=2)
        pool.add("a", lambda: 1)
        pool.add("b", lambda: 2)
        with pytest.raises(RuntimeError):
            pool.add("c", lambda: 3)

    async def test_run_requires_approval(self):
        pool = ForkPool()
        pool.add("noop", lambda: 1)
        with pytest.raises(RuntimeError):
            await pool.run()

    async def test_run_async_workers(self):
        async def wrapper():
            return await _sample_async_worker(5)

        pool = ForkPool()
        wid = pool.add("async 5", wrapper)
        results = await pool.run(approved=True)
        assert len(results) == 1
        assert results[wid].status == WorkerStatus.DONE
        assert results[wid].output == 10

    async def test_run_sync_workers(self):
        pool = ForkPool()
        wid = pool.add("sync 5", lambda: _sample_sync_worker(5))
        results = await pool.run(approved=True)
        assert results[wid].status == WorkerStatus.DONE
        assert results[wid].output == 6

    async def test_error_isolated(self):
        pool = ForkPool()
        wid_ok = pool.add("ok", lambda: 1)
        wid_fail = pool.add("fail", lambda: (_ for _ in ()).throw(RuntimeError("boom")))
        results = await pool.run(approved=True)
        assert results[wid_ok].status == WorkerStatus.DONE
        assert results[wid_fail].status == WorkerStatus.ERROR
        assert "boom" in results[wid_fail].error

    async def test_cancel_all(self):
        pool = ForkPool()

        async def slow():
            await asyncio.sleep(10)
            return 1

        pool.add("slow", slow)
        task = asyncio.create_task(pool.run(approved=True))
        await asyncio.sleep(0.05)
        await pool.cancel_all()
        await asyncio.gather(task, return_exceptions=True)
        assert any(r.status == WorkerStatus.CANCELLED for r in pool.results.values())

    async def test_status_table(self):
        pool = ForkPool()
        pool.add("task one", lambda: 1)
        rows = pool.status_table()
        assert len(rows) == 1
        assert rows[0]["description"] == "task one"
        assert rows[0]["status"] == WorkerStatus.PENDING

    async def test_dump_results(self, tmp_path):
        pool = ForkPool(dump_dir=tmp_path)
        wid = pool.add("x", lambda: 42)
        await pool.run(approved=True)
        files = list(tmp_path.glob("fork_*.json"))
        assert files
        payload = files[0].read_text(encoding="utf-8")
        assert wid in payload

    async def test_reset(self):
        pool = ForkPool()
        pool.add("x", lambda: 1)
        await pool.run(approved=True)
        pool.reset()
        assert pool._specs == []
        assert pool._results == {}
