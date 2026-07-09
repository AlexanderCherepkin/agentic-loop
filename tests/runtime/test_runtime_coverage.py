"""Tests ensuring every loaded agent spec has a runtime invocation path."""

from __future__ import annotations

import asyncio
import json
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from runtime.engine.agent_invocation_map import (
    PHASE_AGENTS,
    PLANNING_FLAG_GROUPS,
    all_referenced_paths,
    conditional_groups_for_flags,
    phase_dispatch,
)
from runtime.engine.agent_loader import AgentLoader
from runtime.engine.llm_engine import LLMConfig, LLMEngine, LLMProvider
from runtime.engine.message_bus import MessageBus
from runtime.engine.pipeline_runner import PipelineRunner, SessionMetrics
from runtime.engine.state_manager import StateManager


@pytest.mark.core
@pytest.mark.runtime
def test_validate_runtime_coverage_script():
    """The standalone validator must report 100% coverage."""
    script = Path(__file__).resolve().parent.parent.parent / ".agent_loop" / "scripts" / "validate_runtime_coverage.py"
    result = subprocess.run(
        [sys.executable, str(script)],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "[OK]" in result.stdout or '"coverage_ok": true' in result.stdout


@pytest.mark.core
@pytest.mark.runtime
def test_agent_loader_count_matches_map():
    """Every agent loaded by AgentLoader is referenced in the invocation map."""
    root = Path(__file__).resolve().parent.parent.parent / ".agent_loop"
    loader = AgentLoader(str(root))
    loaded = set(loader.load_all_agents().keys())
    referenced = all_referenced_paths()
    referenced.add("main_loop.md")
    assert loaded == referenced, f"Unreachable agents: {sorted(loaded - referenced)}"


@pytest.mark.core
@pytest.mark.runtime
def test_planning_coverage_mode_dispatches_all_groups(tmp_path):
    """In coverage mode the planner must invoke every planning context."""
    config = LLMConfig(provider=LLMProvider.MOCK, mcp_enabled=False)
    llm = LLMEngine(config=config)
    runner = PipelineRunner(
        loader=AgentLoader(".agent_loop"),
        llm=llm,
        bus=MessageBus(),
        state=StateManager(),
        workspace_root=str(tmp_path),
        coverage_mode=True,
    )

    called: set[str] = set()

    async def mock_invoke(agent_path, inputs, trace, phase, metrics=None):
        called.add(agent_path)
        return type("R", (), {"parsed": {"mock": True}})()

    runner._invoke_agent = mock_invoke

    async def _run():
        return await runner._run_planning("hello", "session-1", [], SessionMetrics(session_id="session-1"))

    plan = asyncio.run(_run())

    expected = set(runner.FLOW_SEQUENCE)
    expected.update(phase_dispatch("planning_general"))
    for flag in PLANNING_FLAG_GROUPS:
        expected.update(conditional_groups_for_flags({flag: True}))
    # Flatten groups to agent paths.
    expected_agents: set[str] = set()
    for item in expected:
        if item.endswith(".md"):
            expected_agents.add(item)
        else:
            expected_agents.update(phase_dispatch(item))

    missing = expected_agents - called
    assert not missing, f"Planning coverage missing: {sorted(missing)}"


@pytest.mark.core
@pytest.mark.runtime
def test_all_phase_contexts_are_reachable():
    """Every context in PHASE_AGENTS must contain at least one agent."""
    for phase, agents in PHASE_AGENTS.items():
        assert agents, f"Phase {phase} has no agents"
