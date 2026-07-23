"""Integration tests for expanded SAFETY_AGENTS list in PipelineRunner."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import json
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


def test_safety_agents_list_includes_all_required_agents(tmp_path):
    runner = _make_runner(tmp_path)
    expected = {
        "safety-control/input_sanitizer.md",
        "safety-control/threat_detector.md",
        "safety-control/permission_checker.md",
        "safety-control/command_guard.md",
        "safety-control/data_leak_preventer.md",
        "safety-control/output_reviewer.md",
        "safety-control/bias_detector.md",
        "safety-control/content_checker.md",
        "safety-control/safety_assessor.md",
        "control/scope_manager.md",
        "control/policy_enforcer.md",
    }
    assert set(runner.SAFETY_AGENTS) == expected


def test_safety_pre_check_invokes_all_agents_and_passes(tmp_path):
    runner = _make_runner(tmp_path)
    called_agents: list[str] = []

    async def mock_invoke(agent_path, inputs, trace, phase, metrics=None):
        called_agents.append(agent_path)
        return _mock_response({"blocked": False, "reason": "mock"})

    runner._invoke_agent = mock_invoke

    async def _run():
        return await runner._run_safety_pre_check("hello", "session-1", [], SessionMetrics(session_id="session-1"))

    result = asyncio.run(_run())
    assert result is True
    assert len(called_agents) == len(runner.SAFETY_AGENTS)
    for agent in runner.SAFETY_AGENTS:
        assert agent in called_agents


def test_safety_pre_check_blocks_on_any_agent_blocked(tmp_path):
    runner = _make_runner(tmp_path)

    async def mock_invoke(agent_path, inputs, trace, phase, metrics=None):
        if agent_path == "safety-control/command_guard.md":
            return _mock_response({"blocked": True, "reason": "prohibited command"})
        return _mock_response({"blocked": False})

    runner._invoke_agent = mock_invoke

    async def _run():
        return await runner._run_safety_pre_check("hello", "session-1", [], SessionMetrics(session_id="session-1"))

    result = asyncio.run(_run())
    assert result is False


def test_safety_chain_command_check_blocks_dangerous_tool_arguments(tmp_path):
    runner = _make_runner(tmp_path)
    blocked = runner._check_safety_for_tool("Bash", {"command": "rm -rf /tmp"})
    assert blocked is not None
    assert blocked.get("guard_blocked") is True
    assert "Safety chain blocked" in blocked.get("error", "")


def test_safety_chain_command_check_allows_safe_tool_arguments(tmp_path):
    runner = _make_runner(tmp_path)
    allowed = runner._check_safety_for_tool("Bash", {"command": "python .agent_loop/scripts/health_check.py"})
    assert allowed is None


def test_full_run_with_mock_safety_agents_terminates(tmp_path):
    runner = _make_runner(tmp_path)

    async def mock_invoke(agent_path, inputs, trace, phase, metrics=None):
        if phase == "safety_pre_check":
            return _mock_response({"blocked": False})
        if phase == "planning":
            return _mock_response({"plan": {"steps": []}})
        if phase == "execution":
            return _mock_response({"result": "done", "tool_call": None})
        if phase == "observation":
            return _mock_response({"result": "done"})
        if phase == "validation":
            return _mock_response({"decision": "terminate_success"})
        if phase == "mutual_check":
            return _mock_response({"approved": True})
        return _mock_response({})

    runner._invoke_agent = mock_invoke

    # Use green resource monitor so the run does not abort on resources.
    from runtime.observability.resource_monitor import ResourceCheckResult, ResourceLevel, ResourceMonitor, ResourceSnapshot
    monitor = ResourceMonitor(workspace_root=str(tmp_path), disable_psutil=True)

    def _green():
        return ResourceCheckResult(
            level=ResourceLevel.GREEN,
            reason="green",
            snapshot=ResourceSnapshot(cpu_percent=None, memory_percent=None, disk_percent=10.0, timestamp=0),
            thresholds=monitor.thresholds,
        )

    monitor.check = _green
    runner._resource_monitor = monitor

    async def _run():
        return await runner.run("hello", session_id="session-1", max_iterations=2)

    result = asyncio.run(_run())
    assert result.termination_status == TerminationStatus.SUCCESS
