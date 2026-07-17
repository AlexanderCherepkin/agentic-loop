"""pytest tests for the TUI dashboard renderer."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from tools_terminal.tui_dashboard import (
    AgentActivity,
    DashboardInput,
    DashboardStatus,
    PipelineState,
    ResourceState,
    SafetyState,
    TuiDashboardRenderer,
    render_dashboard,
)


def test_render_full_dashboard() -> None:
    renderer = TuiDashboardRenderer(use_ansi=False)
    pipeline = PipelineState(
        phase="execution",
        iteration=2,
        status="running",
        agents=[
            AgentActivity(name="tool_plan_selection", category="planning", duration_ms=120, outcome="pass"),
            AgentActivity(name="tool_invocation", category="execution", duration_ms=340, outcome="running"),
        ],
    )
    resources = ResourceState(cpu_level="normal", memory_level="warning", cpu_percent=45.0, memory_percent=78.0)
    safety = SafetyState(verdicts=[{"verdict": "pass", "rule": "no_secrets"}], check_count=1, active_blocks=0)
    result = renderer.render(
        DashboardInput(
            session_id="abc123",
            pipeline_state=pipeline,
            resource_state=resources,
            safety_state=safety,
            max_lines=24,
        )
    )
    assert result.dashboard_text
    assert "execution" in result.dashboard_text
    assert result.summary["phase"] == "execution"


def render_single_line_when_short() -> None:
    renderer = TuiDashboardRenderer(use_ansi=False)
    pipeline = PipelineState(phase="result", iteration=5, status="completed")
    result = renderer.render(
        DashboardInput(
            session_id="abc123",
            pipeline_state=pipeline,
            resource_state=ResourceState(),
            safety_state=SafetyState(),
            max_lines=4,
        )
    )
    assert "\n" not in result.dashboard_text
    assert "phase result" in result.dashboard_text


def test_stacked_layout_when_narrow() -> None:
    renderer = TuiDashboardRenderer(use_ansi=False)
    # Force narrow terminal by patching term_size
    renderer.term_size = type("TS", (), {"columns": 30, "lines": 24})()
    pipeline = PipelineState(phase="observability", iteration=1, status="running")
    result = renderer.render(
        DashboardInput(
            session_id="abc123",
            pipeline_state=pipeline,
            resource_state=ResourceState(cpu_percent=30.0),
            safety_state=SafetyState(),
        )
    )
    assert "Agents:" in result.dashboard_text


def test_phase_strip_includes_loop_marker() -> None:
    renderer = TuiDashboardRenderer(use_ansi=False)
    strip = renderer._phase_strip("execution", loop_detected=True)
    assert "execution" in strip
    assert "loop" in strip


def test_convenience_render_dashboard() -> None:
    result = render_dashboard(
        session_id="abc123",
        pipeline_state={"phase": "planning", "iteration": 1, "status": "running", "agents": []},
        resource_state={"cpu_percent": 12.0, "memory_percent": 34.0},
        safety_state={"verdicts": [], "check_count": 0, "active_blocks": 0},
    )
    assert "planning" in result.dashboard_text
    assert result.summary["status"] == "running"
