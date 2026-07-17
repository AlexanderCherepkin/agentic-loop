"""TUI Dashboard renderer for the Agentic Loop pipeline.

Pure rendering module: no side effects, no terminal mutations. Emits either a
rich ANSI/Unicode dashboard or a compact plain-text summary depending on TTY
availability and terminal dimensions.
"""

from __future__ import annotations

import shutil
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class DashboardStatus(str, Enum):
    RUNNING = "running"
    COMPLETED = "completed"
    PARTIAL = "partial"
    FAILURE = "failure"
    ESCALATED_HUMAN = "escalated_human"


@dataclass
class AgentActivity:
    name: str
    category: str = ""
    duration_ms: int = 0
    outcome: str = "running"  # pass, fail, degraded, running


@dataclass
class ResourceState:
    cpu_level: str = "normal"  # low, normal, elevated, critical
    memory_level: str = "normal"
    cpu_percent: float = 0.0
    memory_percent: float = 0.0


@dataclass
class SafetyState:
    verdicts: list[dict[str, Any]] = field(default_factory=list)
    check_count: int = 0
    active_blocks: int = 0
    human_escalations: int = 0


@dataclass
class PipelineState:
    phase: str = "user"
    iteration: int = 0
    status: str = "running"
    agents: list[AgentActivity] = field(default_factory=list)


@dataclass
class DashboardInput:
    session_id: str
    pipeline_state: PipelineState
    resource_state: ResourceState
    safety_state: SafetyState
    max_lines: int = 24
    start_time: float = 0.0


@dataclass
class DashboardResult:
    dashboard_text: str
    summary: dict[str, Any]


class TuiDashboardRenderer:
    """Render a live TUI dashboard from pipeline state."""

    PHASES = ["user", "planning", "execution", "observability", "self_correction", "result"]

    STATUS_COLORS: dict[str, str] = {
        DashboardStatus.RUNNING: "\033[33m",       # yellow
        DashboardStatus.COMPLETED: "\033[32m",     # green
        DashboardStatus.PARTIAL: "\033[35m",       # magenta
        DashboardStatus.FAILURE: "\033[31m",       # red
        DashboardStatus.ESCALATED_HUMAN: "\033[35m",  # magenta
    }
    RESET = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"

    OUTCOME_ICONS: dict[str, str] = {
        "pass": "✓",
        "fail": "✗",
        "degraded": "⚠",
        "running": "⧖",
    }

    VERDICT_COLORS: dict[str, str] = {
        "pass": "\033[32m",
        "warn": "\033[33m",
        "block": "\033[31m",
        "escalate": "\033[35m",
    }

    def __init__(self, use_ansi: bool | None = None, use_unicode: bool = True):
        if use_ansi is None:
            use_ansi = True
        self.use_ansi = use_ansi
        self.use_unicode = use_unicode
        self.term_size = shutil.get_terminal_size((80, 24))

    def render(self, input_state: DashboardInput) -> DashboardResult:
        width = self.term_size.columns
        height = self.term_size.lines

        if height < 8 or input_state.max_lines < 8:
            text = self._render_single_line(input_state, width)
        elif width < 40:
            text = self._render_stacked(input_state, min(input_state.max_lines, height))
        else:
            text = self._render_full(input_state, min(input_state.max_lines, height), width)

        summary = {
            "lines": len(text.splitlines()),
            "width": width,
            "phase": input_state.pipeline_state.phase,
            "status": input_state.pipeline_state.status,
        }
        return DashboardResult(dashboard_text=text, summary=summary)

    def _color(self, name: str) -> str:
        if not self.use_ansi:
            return ""
        return name

    def _reset(self) -> str:
        return self.RESET if self.use_ansi else ""

    def _bar(self, percent: float, width: int = 20) -> str:
        filled = int(max(0.0, min(100.0, percent)) / 100.0 * width)
        empty = width - filled
        bar = "|" * filled + "." * empty
        if not self.use_unicode:
            return f"[{bar}]"
        return f"[{bar}]"

    def _status_badge(self, status: str) -> str:
        color = self.STATUS_COLORS.get(status, "")
        return f"{color}{status.upper()}{self._reset()}"

    def _phase_index(self, phase: str) -> int:
        try:
            return self.PHASES.index(phase)
        except ValueError:
            return -1

    def _phase_strip(self, current_phase: str, loop_detected: bool = False) -> str:
        current_index = self._phase_index(current_phase)
        if current_index < 0:
            # Unknown phase: show raw with marker.
            strip = f"{current_phase} ?"
            if loop_detected:
                strip += f" {self._color(self.STATUS_COLORS[DashboardStatus.FAILURE])}↻ loop{self._reset()}"
            return strip

        parts: list[str] = []
        for phase in self.PHASES:
            phase_index = self._phase_index(phase)
            if phase == current_phase:
                icon = "▶" if self.use_unicode else ">"
                parts.append(f"{self._color(self.BOLD)}{icon} {phase}{self._reset()}")
            elif phase_index < current_index:
                icon = "✓" if self.use_unicode else "v"
                parts.append(f"{self._color(self.VERDICT_COLORS['pass'])}{icon} {phase}{self._reset()}")
            else:
                icon = "○" if self.use_unicode else "o"
                parts.append(f"{self._color(self.DIM)}{icon} {phase}{self._reset()}")
        strip = " → ".join(parts)
        if loop_detected:
            strip += f" {self._color(self.STATUS_COLORS[DashboardStatus.FAILURE])}↻ loop{self._reset()}"
        return strip

    def _header(self, input_state: DashboardInput) -> str:
        session = input_state.session_id[:8]
        status = self._status_badge(input_state.pipeline_state.status)
        phase = input_state.pipeline_state.phase
        iteration = input_state.pipeline_state.iteration
        return f"Session {session} | Phase {phase} | Iter {iteration} | {status}"

    def _uptime(self, start_time: float) -> str:
        if start_time <= 0:
            return "--:--"
        elapsed = time.time() - start_time
        minutes = int(elapsed // 60)
        seconds = int(elapsed % 60)
        return f"{minutes:02d}:{seconds:02d}"

    def _render_single_line(self, input_state: DashboardInput, width: int) -> str:
        phase = input_state.pipeline_state.phase
        iteration = input_state.pipeline_state.iteration
        status = input_state.pipeline_state.status
        agent_count = len(input_state.pipeline_state.agents)
        text = f"Session {input_state.session_id[:8]} | phase {phase} | iter {iteration} | status {status} | agents {agent_count}"
        return text[:width]

    def _render_stacked(self, input_state: DashboardInput, max_lines: int) -> str:
        lines: list[str] = []
        lines.append(self._header(input_state))
        lines.append(self._phase_strip(input_state.pipeline_state.phase))

        # Resource panel
        rs = input_state.resource_state
        lines.append(f"CPU {self._bar(rs.cpu_percent)} {rs.cpu_level}")
        lines.append(f"MEM {self._bar(rs.memory_percent)} {rs.memory_level}")

        # Agents
        lines.append("Agents:")
        for agent in input_state.pipeline_state.agents[-5:]:
            icon = self.OUTCOME_ICONS.get(agent.outcome, "?")
            lines.append(f"  {icon} {agent.name} ({agent.category}) {agent.duration_ms}ms")

        # Safety
        ss = input_state.safety_state
        lines.append(f"Safety: {ss.check_count} checks, {ss.active_blocks} blocks, {ss.human_escalations} escalations")

        # Footer
        lines.append(f"Uptime {self._uptime(input_state.start_time)} | Ctrl-C = human escalation")

        return "\n".join(lines[:max_lines])

    def _render_full(self, input_state: DashboardInput, max_lines: int, width: int) -> str:
        lines: list[str] = []
        lines.append(self._header(input_state))
        lines.append(self._phase_strip(input_state.pipeline_state.phase))
        lines.append("")

        # Left/right panels
        left_width = max(28, width // 2 - 2)
        right_width = width - left_width - 3

        # Agents panel
        agents_title = "Agent Activity"
        agents_lines = [agents_title, "-" * min(len(agents_title), left_width)]
        for agent in input_state.pipeline_state.agents[-5:]:
            icon = self.OUTCOME_ICONS.get(agent.outcome, "?")
            name = agent.name[:left_width - 10]
            line = f"{icon} {name} {agent.duration_ms}ms"
            agents_lines.append(line[:left_width])
        while len(agents_lines) < 8:
            agents_lines.append("")

        # Resource + safety panel
        rs = input_state.resource_state
        ss = input_state.safety_state
        info_title = "Resources / Safety"
        info_lines = [info_title, "-" * min(len(info_title), right_width)]
        info_lines.append(f"CPU {self._bar(rs.cpu_percent, width=right_width - 10)} {rs.cpu_level}")
        info_lines.append(f"MEM {self._bar(rs.memory_percent, width=right_width - 10)} {rs.memory_level}")
        info_lines.append("")
        info_lines.append(f"Safety checks: {ss.check_count}")
        info_lines.append(f"Blocks: {ss.active_blocks}")
        info_lines.append(f"Escalations: {ss.human_escalations}")
        for verdict in ss.verdicts[-3:]:
            color = self.VERDICT_COLORS.get(verdict.get("verdict", ""), "")
            text = f"  {verdict.get('verdict', '-')} {verdict.get('rule', '')}"[:right_width]
            info_lines.append(f"{color}{text}{self._reset()}")
        while len(info_lines) < 8:
            info_lines.append("")

        # Merge panels side-by-side
        for a, b in zip(agents_lines[:8], info_lines[:8]):
            lines.append(f"{a:<{left_width}} | {b:<{right_width}}")

        lines.append("")
        lines.append(f"Uptime {self._uptime(input_state.start_time)} | Ctrl-C = human escalation")

        return "\n".join(lines[:max_lines])


def render_dashboard(
    session_id: str,
    pipeline_state: dict[str, Any],
    resource_state: dict[str, Any] | None = None,
    safety_state: dict[str, Any] | None = None,
    max_lines: int = 24,
    start_time: float = 0.0,
    use_ansi: bool | None = None,
) -> DashboardResult:
    """Convenience entry point that accepts plain dicts."""
    ps = PipelineState(
        phase=pipeline_state.get("phase", "user"),
        iteration=pipeline_state.get("iteration", 0),
        status=pipeline_state.get("status", "running"),
        agents=[
            AgentActivity(
                name=a.get("name", "unknown"),
                category=a.get("category", ""),
                duration_ms=a.get("duration_ms", 0),
                outcome=a.get("outcome", "running"),
            )
            for a in pipeline_state.get("agents", [])
        ],
    )
    rs = ResourceState(**(resource_state or {}))
    ss = SafetyState(**(safety_state or {}))
    renderer = TuiDashboardRenderer(use_ansi=use_ansi)
    return renderer.render(
        DashboardInput(
            session_id=session_id,
            pipeline_state=ps,
            resource_state=rs,
            safety_state=ss,
            max_lines=max_lines,
            start_time=start_time,
        )
    )
