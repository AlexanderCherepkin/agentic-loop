"""Integration tests for expanded MUTUAL_CHECK_AGENTS list in PipelineRunner."""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import pytest

from runtime.engine.agent_loader import AgentLoader
from runtime.engine.llm_engine import LLMConfig, LLMEngine, LLMProvider, LLMResponse
from runtime.engine.message_bus import MessageBus
from runtime.engine.pipeline_runner import PipelineRunner, SessionMetrics, TerminationStatus
from runtime.engine.state_manager import StateManager


def _mock_response(data: dict) -> LLMResponse:
    content = json.dumps(data, ensure_ascii=False)
    return LLMResponse(
        content=content,
        parsed=data,
        model="mock-engine",
        tokens_used=len(content) // 4,
        latency_ms=15.0,
        finish_reason="stop",
    )


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


def test_mutual_check_agents_list_includes_all_required_agents(tmp_path):
    runner = _make_runner(tmp_path)
    expected = {
        "safety-control/mutual_check/consistency_checker.md",
        "safety-control/mutual_check/result_validator.md",
        "safety-control/mutual_check/quality_assessor.md",
        "safety-control/mutual_check/action_verifier.md",
        "safety-control/mutual_check/performance_monitor.md",
        "safety-control/mutual_check/quota_manager.md",
        "safety-control/mutual_check/anomaly_detector.md",
        "safety-control/mutual_check/feedback_aggregator.md",
        "safety-control/mutual_check/compliance_checker.md",
        "safety-control/mutual_check/audit_logger.md",
    }
    assert set(runner.MUTUAL_CHECK_AGENTS) == expected


def test_run_mutual_check_invokes_all_agents(tmp_path):
    runner = _make_runner(tmp_path)
    called_agents: list[str] = []

    async def mock_invoke(agent_path, inputs, trace, phase, metrics=None):
        called_agents.append(agent_path)
        return _mock_response({"approved": True})

    runner._invoke_agent = mock_invoke

    async def _run():
        metrics = SessionMetrics(session_id="session-1")
        await runner._run_mutual_check("mock result", "session-1", [], metrics)

    asyncio.run(_run())
    assert len(called_agents) == len(runner.MUTUAL_CHECK_AGENTS)
    for agent in runner.MUTUAL_CHECK_AGENTS:
        assert agent in called_agents


def test_run_mutual_check_passes_metrics_context(tmp_path):
    runner = _make_runner(tmp_path)
    captured_inputs: dict[str, dict] = {}

    async def mock_invoke(agent_path, inputs, trace, phase, metrics=None):
        captured_inputs[agent_path] = inputs
        return _mock_response({"approved": True})

    runner._invoke_agent = mock_invoke

    async def _run():
        metrics = SessionMetrics(session_id="session-1")
        metrics.iterations = 3
        metrics.tools_used = ["tool_a", "tool_b"]
        metrics.tokens_consumed = 150
        metrics.time_elapsed_ms = 1200.5
        await runner._run_mutual_check("result text", "session-1", [], metrics)

    asyncio.run(_run())
    sample_inputs = next(iter(captured_inputs.values()))
    assert sample_inputs["result"] == "result text"
    assert sample_inputs["session_id"] == "session-1"
    assert sample_inputs["iteration"] == 3
    assert sample_inputs["tools_used"] == ["tool_a", "tool_b"]
    assert sample_inputs["tokens_consumed"] == 150
    assert sample_inputs["time_elapsed_ms"] == 1200.5


def test_mock_engine_returns_responses_for_all_mutual_check_agents(tmp_path):
    """Ensure the mock LLM engine has deterministic responses for every MUTUAL_CHECK agent."""
    runner = _make_runner(tmp_path)
    for agent_path in runner.MUTUAL_CHECK_AGENTS:
        spec = runner._get_agent(agent_path)
        response = asyncio.run(runner.llm.execute(spec, {"result": "x", "session_id": "s-1"}))
        assert response is not None
        assert response.parsed is not None
        assert response.parsed.get("mock") is None, f"Missing mock response for {agent_path}"
