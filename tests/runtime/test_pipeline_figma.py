"""Integration tests for Figma wiring inside PipelineRunner.

These tests verify that the runtime exposes Figma MCP tools only when the
figma-agent-core configuration is present, and that figma_* tools can be
executed through the pipeline runner.
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, patch

# Ensure project root is on PYTHONPATH
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import pytest

from runtime.engine.agent_loader import AgentLoader
from runtime.engine.llm_engine import LLMConfig, LLMEngine, LLMProvider
from runtime.engine.message_bus import MessageBus
from runtime.engine.pipeline_runner import IterationTrace, PipelineResult, PipelineRunner, SessionMetrics
from runtime.engine.state_manager import StateManager
from runtime.observability.resource_monitor import ResourceMonitor


def _make_runner(workspace_root: Path, mcp_enabled: bool = True) -> PipelineRunner:
    config = LLMConfig(provider=LLMProvider.MOCK, mcp_enabled=mcp_enabled)
    llm = LLMEngine(config=config)
    runner = PipelineRunner(
        loader=AgentLoader(".agent_loop"),
        llm=llm,
        bus=MessageBus(),
        state=StateManager(),
        workspace_root=str(workspace_root),
    )
    # Deterministic resource monitoring: disable psutil so CPU/RAM checks are
    # skipped and only disk usage (which is stable in temp dirs) is evaluated.
    runner._resource_monitor = ResourceMonitor(workspace_root=str(workspace_root), disable_psutil=True)
    return runner


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


def test_design_intake_short_circuits_for_full_code() -> None:
    runner = _make_runner(Path.cwd())

    async def _run():
        with patch.object(runner, "execute_mcp_tool", new=AsyncMock(return_value={
            "tool": "figma_run_pipeline",
            "result": {"status": "success", "returncode": 0, "stdout": "generated", "stderr": ""},
            "mcp_executed": True,
        })) as mock_mcp:
            result = await runner.run("сверстай макет Figma https://www.figma.com/design/abc123/Sample")
            mock_mcp.assert_awaited_once()
            args = mock_mcp.await_args[0]
            assert args[0] == "figma_run_pipeline"
            assert args[1].get("figma_url") == "https://www.figma.com/design/abc123/Sample"
            assert args[1].get("file_key") == "abc123"
            assert args[1].get("dry_run") is False
        return result

    result = asyncio.run(_run())
    assert result.termination_status.value == "success"
    assert "Design pipeline triggered" in result.final_response


def test_design_intake_honors_dry_run_flag() -> None:
    runner = _make_runner(Path.cwd())

    async def _run():
        with patch.object(runner, "execute_mcp_tool", new=AsyncMock(return_value={
            "tool": "figma_run_pipeline",
            "result": {"status": "success", "returncode": 0, "stdout": "generated", "stderr": ""},
            "mcp_executed": True,
        })) as mock_mcp:
            result = await runner.run(
                "сделай dry-run по макету Figma https://www.figma.com/design/abc123/Sample"
            )
            args = mock_mcp.await_args[0]
            assert args[0] == "figma_run_pipeline"
            assert args[1].get("dry_run") is True
        return result

    result = asyncio.run(_run())
    assert result.termination_status.value in ("success", "partial")


def test_design_intake_continues_planning_for_spec() -> None:
    runner = _make_runner(Path.cwd())

    async def _run():
        original_execute = runner.llm.execute

        async def _mock_execute(spec, inputs, extra_context=None):
            response = await original_execute(spec, inputs, extra_context=extra_context)
            agent_path = getattr(spec, "source_path", "")
            if agent_path.endswith("user/design_intake.md"):
                response.parsed["design_descriptor"]["output_mode"] = "technical_assignment"
            return response

        with patch.object(runner.llm, "execute", new=_mock_execute):
            with patch.object(runner, "execute_mcp_tool", new=AsyncMock(return_value={})) as mock_mcp:
                result = await runner.run("напиши ТЗ по макету Figma https://www.figma.com/design/abc123/Sample")
                mock_mcp.assert_not_awaited()
        return result

    result = asyncio.run(_run())
    assert result.termination_status.value in ("success", "partial")


def test_extract_figma_file_key_and_node_id() -> None:
    runner = _make_runner(Path.cwd())
    assert runner._extract_figma_file_key("https://www.figma.com/design/abc123/Sample?node-id=1-2") == "abc123"
    assert runner._extract_figma_node_id("https://www.figma.com/design/abc123/Sample?node-id=1-2") == "1:2"
    assert runner._extract_figma_file_key("not a url") == ""
    assert runner._extract_figma_node_id("no node") == ""


def test_client_brief_interview_short_circuits() -> None:
    runner = _make_runner(Path.cwd(), mcp_enabled=False)

    async def _run():
        result = await runner.run("заказать лендинг для SaaS продукта")
        return result

    result = asyncio.run(_run())
    assert result.termination_status.value == "success"
    assert "business goal" in result.final_response.lower() or "target audience" in result.final_response.lower()


def test_client_brief_proceeds_when_complete() -> None:
    runner = _make_runner(Path.cwd(), mcp_enabled=False)

    async def _run():
        original_execute = runner.llm.execute

        async def _mock_execute(spec, inputs, extra_context=None):
            response = await original_execute(spec, inputs, extra_context=extra_context)
            agent_path = str(getattr(spec, "source_path", "")).replace("\\", "/")
            if agent_path.endswith("user/client_brief_agent.md"):
                response.parsed["client_brief"]["next_action"] = "proceed"
                response.parsed["client_brief"]["missing_fields"] = []
                response.parsed["client_brief"]["questions"] = []
                response.parsed["client_brief"]["brief_confidence"] = 0.9
            return response

        with patch.object(runner.llm, "execute", new=_mock_execute):
            result = await runner.run("сделай лендинг с целью продажи подписок, аудитория — малый бизнес, CTA — 'Оформить подписку'")
        return result

    result = asyncio.run(_run())
    assert result.termination_status.value in ("success", "partial")


def test_copywriting_agent_runs_when_client_brief_present() -> None:
    runner = _make_runner(Path.cwd(), mcp_enabled=False)

    design_descriptor = {
        "design_source": "design_brief",
        "source_value": "mock brief",
        "output_mode": "both",
        "target_stack": "react_next_tailwind",
        "target_scope": "whole_page",
        "backend_spec": None,
        "metadata": {
            "title": "Client Brief",
            "detected_language": "ru",
            "client_brief": {
                "business_goal": "продажа подписок",
                "target_audience": {"personas": ["малый бизнес"]},
                "ctas": [{"label": "Оформить подписку", "priority": "primary"}],
                "output_mode": "both",
                "next_action": "proceed",
                "missing_fields": [],
                "questions": [],
                "brief_confidence": 0.9,
            },
        },
    }

    async def _run():
        original_execute = runner.llm.execute

        async def _mock_execute(spec, inputs, extra_context=None):
            response = await original_execute(spec, inputs, extra_context=extra_context)
            agent_path = str(getattr(spec, "source_path", "")).replace("\\", "/")
            if agent_path.endswith("planning/tool_plan_selection.md"):
                response.parsed["needs_copywriting"] = True
            return response

        with patch.object(runner.llm, "execute", new=_mock_execute):
            return await runner._run_planning(
                "сделай лендинг",
                "test-session",
                [],
                SessionMetrics(session_id="test-session"),
                design_descriptor=design_descriptor,
            )

    plan = asyncio.run(_run())
    assert plan.get("needs_copywriting") is True
    copy_package = plan.get("copy_package")
    assert copy_package is not None, "copy_package missing from plan"
    assert copy_package.get("headline") == "Mock Headline"
    assert copy_package.get("cta_primary", {}).get("label") == "Get Started"
    assert copy_package.get("confidence", 0) >= 0.5


def test_estimation_agent_runs_when_client_brief_has_limits() -> None:
    runner = _make_runner(Path.cwd(), mcp_enabled=False)

    design_descriptor = {
        "design_source": "design_brief",
        "source_value": "mock brief",
        "output_mode": "both",
        "target_stack": "react_next_tailwind",
        "target_scope": "whole_page",
        "backend_spec": None,
        "metadata": {
            "title": "Client Brief",
            "detected_language": "ru",
            "client_brief": {
                "business_goal": "продажа подписок",
                "target_audience": {"personas": ["малый бизнес"]},
                "ctas": [{"label": "Оформить подписку", "priority": "primary"}],
                "limits": {"budget": "$5000", "deadline": "2 недели"},
                "output_mode": "both",
                "next_action": "proceed",
                "missing_fields": [],
                "questions": [],
                "brief_confidence": 0.9,
            },
        },
    }

    async def _run():
        original_execute = runner.llm.execute

        async def _mock_execute(spec, inputs, extra_context=None):
            response = await original_execute(spec, inputs, extra_context=extra_context)
            agent_path = str(getattr(spec, "source_path", "")).replace("\\", "/")
            if agent_path.endswith("planning/tool_plan_selection.md"):
                response.parsed["needs_copywriting"] = True
                response.parsed["needs_estimation"] = True
            return response

        with patch.object(runner.llm, "execute", new=_mock_execute):
            return await runner._run_planning(
                "сделай лендинг",
                "test-session",
                [],
                SessionMetrics(session_id="test-session"),
                design_descriptor=design_descriptor,
            )

    plan = asyncio.run(_run())
    assert plan.get("needs_estimation") is True
    proposal_package = plan.get("proposal_package")
    assert proposal_package is not None, "proposal_package missing from plan"
    assert proposal_package.get("estimate", {}).get("hourly_rate") == 80
    assert proposal_package.get("proposal_markdown", "")
    assert proposal_package.get("confidence", 0) >= 0.5


def test_starter_agent_runs_when_client_order_present() -> None:
    runner = _make_runner(Path.cwd(), mcp_enabled=False)

    design_descriptor = {
        "design_source": "design_brief",
        "source_value": "mock brief",
        "output_mode": "both",
        "target_stack": "react_next_tailwind",
        "target_scope": "whole_page",
        "backend_spec": None,
        "metadata": {
            "title": "Client Brief",
            "detected_language": "ru",
            "client_brief": {
                "business_goal": "продажа подписок",
                "target_audience": {"personas": ["малый бизнес"]},
                "ctas": [{"label": "Оформить подписку", "priority": "primary"}],
                "output_mode": "both",
                "next_action": "proceed",
                "missing_fields": [],
                "questions": [],
                "brief_confidence": 0.9,
            },
        },
    }

    async def _run():
        original_execute = runner.llm.execute

        async def _mock_execute(spec, inputs, extra_context=None):
            response = await original_execute(spec, inputs, extra_context=extra_context)
            agent_path = str(getattr(spec, "source_path", "")).replace("\\", "/")
            if agent_path.endswith("planning/tool_plan_selection.md"):
                response.parsed["needs_copywriting"] = True
                response.parsed["needs_estimation"] = True
                response.parsed["needs_starter"] = True
            return response

        with patch.object(runner.llm, "execute", new=_mock_execute):
            return await runner._run_planning(
                "сделай лендинг",
                "test-session",
                [],
                SessionMetrics(session_id="test-session"),
                design_descriptor=design_descriptor,
            )

    plan = asyncio.run(_run())
    assert plan.get("needs_starter") is True
    starter_package = plan.get("starter_package")
    assert starter_package is not None, "starter_package missing from plan"
    assert starter_package.get("template_id") in ("landing", "saas", "portfolio", "ecommerce")
    assert len(starter_package.get("files", [])) > 0
    assert starter_package.get("readme", "")
    assert starter_package.get("confidence", 0) >= 0.5


def test_regression_guard_agent_in_validation_core() -> None:
    runner = _make_runner(Path.cwd(), mcp_enabled=False)
    assert "tooll_subagents/self_correction/regression_guard.md" in runner.VALIDATION_CORE


def test_regression_guard_passes_previous_validation_to_review() -> None:
    runner = _make_runner(Path.cwd(), mcp_enabled=False)

    async def _run():
        state = {
            "observation": {
                "visual_qa_report": {
                    "status": "passed",
                    "screenshot_path": "/tmp/current.png",
                    "diff_score": 0.02,
                    "layout_checks": [],
                    "bbox_comparison": {"failed": 0},
                },
                "lighthouse_audit_report": {
                    "passed": True,
                    "category_scores": {"performance": 1.0, "accessibility": 1.0, "best_practices": 1.0, "seo": 1.0},
                },
                "file_context": {"file_changes": [{"path": "app/page.tsx", "change_type": "modified"}], "integrity_check": "passed"},
            },
            "validation": {
                "visual_qa_report": {
                    "status": "passed",
                    "screenshot_path": "/tmp/baseline.png",
                    "diff_score": 0.01,
                    "layout_checks": [],
                    "bbox_comparison": {"failed": 0},
                },
                "lighthouse_audit_report": {
                    "passed": True,
                    "category_scores": {"performance": 1.0, "accessibility": 1.0, "best_practices": 1.0, "seo": 1.0},
                },
                "file_context": {"file_changes": [], "integrity_check": "passed"},
            },
            "iteration": 2,
        }
        trace: list[IterationTrace] = []
        return await runner._run_self_correction_review(state, trace, SessionMetrics(session_id="test-regression"))

    review = asyncio.run(_run())
    assert "previous_validation" in review
    assert review["iteration_count"] == 2
    assert review["regression_report"] is not None
    assert review["regression_report"]["verdict"] == "pass"


def test_regression_guard_reports_regression_on_diff_jump() -> None:
    runner = _make_runner(Path.cwd(), mcp_enabled=False)

    async def _run():
        original_execute = runner.llm.execute

        async def _mock_execute(spec, inputs, extra_context=None):
            response = await original_execute(spec, inputs, extra_context=extra_context)
            agent_path = str(getattr(spec, "source_path", "")).replace("\\", "/")
            if agent_path.endswith("self_correction/regression_guard.md"):
                response.parsed = {
                    "regression_report": {
                        "status": "regressed",
                        "screenshot_delta": {"diff_score_delta": 0.12, "baseline_path": "/tmp/baseline.png", "current_path": "/tmp/current.png", "threshold": 0.05},
                        "layout_delta": {"new_overflows": 1, "new_overlaps": 0, "new_clipped_text": 0, "bbox_regressions": 0},
                        "console_delta": {"new_errors": 0, "new_warnings": 0},
                        "lighthouse_delta": {"score_changes": {}},
                        "file_delta": {"files_added": 0, "files_removed": 0, "files_modified": 1},
                        "regressions": [{"severity": "high", "message": "Screenshot diff jumped above threshold", "evidence": "diff_score_delta=0.12"}],
                        "verdict": "fail",
                        "refinement_actions": [{"target": "visual_qa_agent", "action": "re-run layout checks and reduce diff"}],
                    }
                }
                response.content = json.dumps(response.parsed, ensure_ascii=False)
            return response

        state = {
            "observation": {
                "visual_qa_report": {
                    "status": "failed",
                    "screenshot_path": "/tmp/current.png",
                    "diff_score": 0.15,
                    "layout_checks": [{"type": "overflow", "passed": False}],
                    "bbox_comparison": {"failed": 1},
                },
            },
            "validation": {
                "visual_qa_report": {
                    "status": "passed",
                    "screenshot_path": "/tmp/baseline.png",
                    "diff_score": 0.03,
                    "layout_checks": [],
                    "bbox_comparison": {"failed": 0},
                },
            },
            "iteration": 2,
        }
        with patch.object(runner.llm, "execute", new=_mock_execute):
            trace: list[IterationTrace] = []
            review = await runner._run_self_correction_review(state, trace, SessionMetrics(session_id="test-regression"))
        return review

    review = asyncio.run(_run())
    report = review["regression_report"]
    assert report["status"] == "regressed"
    assert report["verdict"] == "fail"
    assert any(r["severity"] == "high" for r in report["regressions"])
    assert len(report["refinement_actions"]) > 0
