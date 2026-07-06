"""Integration tests for ResourceMonitor wired into PipelineRunner."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import pytest

from runtime.engine.agent_loader import AgentLoader
from runtime.engine.llm_engine import LLMConfig, LLMEngine, LLMProvider
from runtime.engine.message_bus import MessageBus
from runtime.engine.pipeline_runner import PipelineRunner, TerminationStatus
from runtime.engine.state_manager import StateManager
from runtime.observability.resource_monitor import ResourceLevel, ResourceMonitor, ResourceSnapshot


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


def test_pipeline_aborts_when_resources_critical_before_react(tmp_path):
    runner = _make_runner(tmp_path)

    # Inject a monitor that always reports critical disk usage
    monitor = ResourceMonitor(workspace_root=str(tmp_path), disable_psutil=True)

    def _critical_check():
        from runtime.observability.resource_monitor import ResourceCheckResult
        return ResourceCheckResult(
            level=ResourceLevel.CRITICAL,
            reason="Disk 99.0% >= critical 95.0%",
            snapshot=ResourceSnapshot(cpu_percent=None, memory_percent=None, disk_percent=99.0, timestamp=0),
            thresholds=monitor.thresholds,
        )

    monitor.check = _critical_check  # type: ignore[method-assign]
    runner._resource_monitor = monitor

    async def _run():
        return await runner.run("test task", max_iterations=1)

    result = asyncio.run(_run())
    assert result.termination_status == TerminationStatus.FAILURE
    assert "resource critical" in result.final_response.lower()
    assert result.session_metrics.iterations == 0


def test_pipeline_aborts_at_iteration_when_resources_critical(tmp_path):
    runner = _make_runner(tmp_path)
    monitor = ResourceMonitor(workspace_root=str(tmp_path), disable_psutil=True)

    call_count = 0

    def _critical_on_second_check():
        nonlocal call_count
        call_count += 1
        from runtime.observability.resource_monitor import ResourceCheckResult
        if call_count <= 1:
            return ResourceCheckResult(
                level=ResourceLevel.GREEN,
                reason="Resources within safe limits",
                snapshot=ResourceSnapshot(cpu_percent=None, memory_percent=None, disk_percent=10.0, timestamp=0),
                thresholds=monitor.thresholds,
            )
        return ResourceCheckResult(
            level=ResourceLevel.CRITICAL,
            reason="Memory 95.0% >= critical 90.0%",
            snapshot=ResourceSnapshot(cpu_percent=None, memory_percent=95.0, disk_percent=10.0, timestamp=0),
            thresholds=monitor.thresholds,
        )

    monitor.check = _critical_on_second_check  # type: ignore[method-assign]
    runner._resource_monitor = monitor

    async def _run():
        return await runner.run("test task", max_iterations=3)

    result = asyncio.run(_run())
    assert result.termination_status == TerminationStatus.FAILURE
    assert "resource critical" in result.final_response.lower()
    assert "iteration" in result.final_response.lower()


def test_pipeline_succeeds_when_resources_green(tmp_path):
    runner = _make_runner(tmp_path)
    monitor = ResourceMonitor(workspace_root=str(tmp_path), disable_psutil=True)

    def _green_check():
        from runtime.observability.resource_monitor import ResourceCheckResult
        return ResourceCheckResult(
            level=ResourceLevel.GREEN,
            reason="Resources within safe limits",
            snapshot=ResourceSnapshot(cpu_percent=None, memory_percent=None, disk_percent=10.0, timestamp=0),
            thresholds=monitor.thresholds,
        )

    monitor.check = _green_check  # type: ignore[method-assign]
    runner._resource_monitor = monitor

    async def _run():
        return await runner.run("test task", max_iterations=2)

    result = asyncio.run(_run())
    assert result.termination_status == TerminationStatus.SUCCESS
