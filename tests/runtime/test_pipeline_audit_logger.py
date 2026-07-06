"""Integration tests for AuditLogger wired into PipelineRunner."""

from __future__ import annotations

import asyncio
import json
import sys
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import pytest

from runtime.engine.agent_loader import AgentLoader
from runtime.engine.llm_engine import LLMConfig, LLMEngine, LLMProvider
from runtime.engine.message_bus import MessageBus
from runtime.engine.pipeline_runner import PipelineRunner, SessionMetrics, TerminationStatus
from runtime.engine.state_manager import StateManager
from runtime.safety.audit_logger import AuditLogger


def _today_str() -> str:
    return datetime.utcnow().strftime("%Y-%m-%d")


def _audit_file(workspace_root: Path) -> Path:
    return workspace_root / ".audit" / f"audit_{_today_str()}.jsonl"


def _make_runner(workspace_root: Path, mcp_enabled: bool = True) -> PipelineRunner:
    config = LLMConfig(provider=LLMProvider.MOCK, mcp_enabled=mcp_enabled)
    llm = LLMEngine(config=config)
    return PipelineRunner(
        loader=AgentLoader(".agent_loop"),
        llm=llm,
        bus=MessageBus(),
        state=StateManager(),
        workspace_root=str(workspace_root),
    )


def _read_entries(workspace_root: Path) -> list[dict]:
    log_file = _audit_file(workspace_root)
    if not log_file.exists():
        return []
    text = log_file.read_text(encoding="utf-8").strip()
    if not text:
        return []
    return [json.loads(line) for line in text.split("\n")]


def test_runner_creates_audit_logger(tmp_path):
    runner = _make_runner(tmp_path)
    assert runner._audit_logger is not None
    assert runner._audit_logger.log_dir == tmp_path / ".audit"


def test_mcp_tool_blocked_writes_safety_blocked_entry(tmp_path):
    runner = _make_runner(tmp_path)
    assert runner._mcp_gateway is not None
    runner._mcp_gateway.execute = AsyncMock(return_value={"is_error": False})

    async def _run():
        return await runner.execute_mcp_tool("write_file", {"path": str(tmp_path / ".env"), "content": "x"})

    result = asyncio.run(_run())
    assert result.get("guard_blocked") is True

    entries = _read_entries(tmp_path)
    blocked = [e for e in entries if e["type"] == "safety_blocked"]
    assert len(blocked) == 1
    assert blocked[0]["agent"] == "mcp:write_file"
    assert "sha256" in blocked[0]
    assert blocked[0]["previous_hash"] == AuditLogger.GENESIS_HASH


def test_mcp_tool_allowed_writes_tool_entries(tmp_path):
    runner = _make_runner(tmp_path)
    assert runner._mcp_gateway is not None
    runner._mcp_gateway.execute = AsyncMock(return_value={"is_error": False, "written": True})

    async def _run():
        return await runner.execute_mcp_tool("write_file", {"path": "allowed.txt", "content": "ok"})

    result = asyncio.run(_run())
    assert result.get("mcp_executed") is True

    entries = _read_entries(tmp_path)
    invoked = [e for e in entries if e["type"] == "tool_invoked"]
    completed = [e for e in entries if e["type"] == "tool_completed"]
    assert len(invoked) == 1
    assert len(completed) == 1
    assert invoked[0]["agent"] == "mcp:write_file"
    assert completed[0]["agent"] == "mcp:write_file"
    assert completed[0]["previous_hash"] == invoked[0]["sha256"]
    assert "sha256" in invoked[0]
    assert "sha256" in completed[0]


def test_finalize_and_return_writes_pipeline_end(tmp_path):
    runner = _make_runner(tmp_path)
    audit_anchor = "audit-anchor-123"
    runner._current_audit_anchor = audit_anchor

    async def _run():
        metrics = SessionMetrics(session_id="session-1")
        return await runner._finalize_and_return(
            "hello", "done", TerminationStatus.SUCCESS,
            metrics, audit_anchor, [], "session-1",
        )

    result = asyncio.run(_run())
    assert result.audit_anchor == audit_anchor

    entries = _read_entries(tmp_path)
    end_entries = [e for e in entries if e["type"] == "pipeline_end"]
    assert len(end_entries) == 1
    assert end_entries[0]["audit_anchor"] == audit_anchor
    assert end_entries[0]["payload"]["status"] == "success"
    assert "sha256" in end_entries[0]


def test_audit_chain_verifies_after_finalize(tmp_path):
    runner = _make_runner(tmp_path)
    runner._current_audit_anchor = "anchor-verify"

    async def _run():
        # Simulate a blocked tool and a pipeline end to create a multi-entry chain.
        await runner.execute_mcp_tool("write_file", {"path": str(tmp_path / ".env"), "content": "x"})
        metrics = SessionMetrics(session_id="session-2")
        return await runner._finalize_and_return(
            "hello", "blocked", TerminationStatus.FAILURE,
            metrics, "anchor-verify", [], "session-2",
        )

    asyncio.run(_run())
    verification = runner._audit_logger.verify_chain()
    assert verification["valid"] is True
    assert verification["entries"] == 2
