from __future__ import annotations

import pytest
import time

from runtime.temporal_memory import TemporalMemoryConfig, TemporalMemoryEngine, TemporalMemoryResult


@pytest.fixture
def engine(tmp_path):
    config = TemporalMemoryConfig(
        enabled=True,
        db_path=str(tmp_path / "graph.db"),
        auto_persist=False,
    )
    return TemporalMemoryEngine(config)


def test_record_fact(engine):
    r = engine.record_fact("price", "9.99 USD")
    assert r.status == "ok"
    assert r.node_id is not None
    assert r.results[0]["content"] == "9.99 USD"


def test_query_at_time_after_state_change(engine):
    t0 = time.time()
    old = engine.record_fact("price", "9.99 USD")
    time.sleep(0.01)
    mid = time.time()
    new = engine.record_state_change("price", "12.99 USD", previous_node_id=old.node_id)
    time.sleep(0.01)
    t2 = time.time()
    assert new.status == "ok"
    before = engine.query_at_time("price", mid)
    assert before.results[0]["content"] == "9.99 USD"
    after = engine.query_at_time("price", t2)
    assert after.results[0]["content"] == "12.99 USD"


def test_query_evolution(engine):
    a = engine.record_fact("status", "pending")
    time.sleep(0.01)
    b = engine.record_state_change("status", "active", previous_node_id=a.node_id)
    time.sleep(0.01)
    c = engine.record_state_change("status", "closed", previous_node_id=b.node_id)
    evo = engine.query_evolution("status")
    assert evo.status == "ok"
    assert len(evo.results) == 3
    assert evo.results[-1]["content"] == "closed"


def test_find_contradictions(engine):
    a = engine.record_fact("rate", "5%")
    b = engine.record_fact("rate", "7%")
    engine.add_relation(a.node_id, b.node_id, "contradicts")
    contradictions = engine.find_contradictions()
    assert contradictions.status == "ok"
    assert len(contradictions.contradictions) == 1


def test_consolidate(engine):
    a = engine.record_fact("plan", "basic")
    time.sleep(0.01)
    b = engine.record_state_change("plan", "pro", previous_node_id=a.node_id)
    time.sleep(0.01)
    engine.record_state_change("plan", "enterprise", previous_node_id=b.node_id)
    result = engine.consolidate("plan")
    assert result.status == "ok"
    assert result.results[0]["count"] == 3


def test_disabled_engine():
    engine = TemporalMemoryEngine(TemporalMemoryConfig(enabled=False))
    r = engine.record_fact("x", "y")
    assert r.status == "disabled"
