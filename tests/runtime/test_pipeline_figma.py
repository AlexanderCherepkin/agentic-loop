"""Integration tests for Figma wiring inside PipelineRunner.

These tests verify that the runtime exposes Figma MCP tools only when the
figma-agent-core configuration is present, and that figma_* tools can be
executed through the pipeline runner.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

# Ensure project root is on PYTHONPATH
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import pytest

from runtime.engine.agent_loader import AgentLoader
from runtime.engine.llm_engine import LLMConfig, LLMEngine, LLMProvider
from runtime.engine.message_bus import MessageBus
from runtime.engine.pipeline_runner import PipelineRunner
from runtime.engine.state_manager import StateManager


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


def test_figma_available_when_configured() -> None:
    runner = _make_runner(Path.cwd())
    # This test assumes the local figma-agent-core/.env is configured.
    core_dir = Path(runner.workspace) / "figma-agent-core"
    assert core_dir.exists(), "figma-agent-core directory must exist for this test"
    assert runner.mcp_enabled is True
    assert runner.figma_available is True


def test_figma_category_exposed_when_available() -> None:
    runner = _make_runner(Path.cwd())
    categories = runner.get_mcp_categories()
    if runner.figma_available:
        assert "figma" in categories
    else:
        assert "figma" not in categories


def test_figma_category_hidden_when_mcp_disabled() -> None:
    runner = _make_runner(Path.cwd(), mcp_enabled=False)
    assert runner.figma_available is False
    assert runner.get_mcp_categories() == []


def test_execute_mcp_figma_tool_dry_run() -> None:
    runner = _make_runner(Path.cwd())

    async def _run():
        return await runner.execute_mcp_tool("figma_run_pipeline", {"dry_run": True})

    result = asyncio.run(_run())
    assert result.get("mcp_executed") is True
    assert result["tool"] == "figma_run_pipeline"
    inner = result.get("result", {})
    assert inner.get("is_error") is False
    assert "content" in inner
    payload = inner["content"][0]["text"]
    assert "DRY RUN" in payload or "dry" in payload.lower()
