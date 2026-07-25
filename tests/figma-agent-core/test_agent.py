"""Smoke tests for figma-agent-core/agent.py."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "figma-agent-core"))

import agent as agent_module


@pytest.fixture
def sample_context(tmp_path):
    path = tmp_path / "figma_node.json"
    path.write_text(
        json.dumps(
            {
                "id": "1:1",
                "name": "Hero Section",
                "type": "FRAME",
                "children": [],
            }
        ),
        encoding="utf-8",
    )
    return str(path)


class TestToPascalCase:
    def test_simple_name(self):
        assert agent_module._to_pascal_case("hero section") == "HeroSection"

    def test_special_chars(self):
        assert agent_module._to_pascal_case("hero-section (v2)") == "HeroSectionV2"

    def test_starts_with_digit(self):
        assert agent_module._to_pascal_case("123 section") == "Figma123Section"


class TestExtractAnnotationText:
    def test_joins_labels_and_descriptions(self):
        annotations = [
            {"label": "Primary", "description": "Main CTA"},
            {"label": "Secondary"},
        ]
        assert agent_module._extract_annotation_text(annotations) == "Primary Main CTA Secondary"

    def test_empty_annotations(self):
        assert agent_module._extract_annotation_text([]) == ""


class TestBuildSemanticSummary:
    def test_builds_summary(self, monkeypatch):
        monkeypatch.setattr(agent_module.analyzer, "infer_semantic_name", lambda n: "HeroSection")
        summary = agent_module._build_semantic_summary({"name": "Hero", "description": "Top block"})
        assert "Semantic component name: HeroSection" in summary
        assert "Description: Top block" in summary


class TestMaybeBootstrap:
    def test_returns_true_when_file_exists(self, tmp_path):
        path = tmp_path / "ctx.json"
        path.write_text("{}", encoding="utf-8")
        assert agent_module._maybe_bootstrap(str(path)) is True

    def test_returns_false_without_env(self, tmp_path, monkeypatch):
        monkeypatch.delenv("FIGMA_TOKEN", raising=False)
        monkeypatch.delenv("FIGMA_URL", raising=False)
        assert agent_module._maybe_bootstrap(str(tmp_path / "missing.json")) is False


class TestInjectAssetPaths:
    def test_injects_public_path(self):
        data = {"id": "a", "isAsset": True, "children": [{"id": "b", "isAsset": True}]}
        paths = {"a": "/images/a.png", "b": "/images/b.png"}
        result = agent_module._inject_asset_paths(data, paths)
        assert result["publicPath"] == "/images/a.png"
        assert result["children"][0]["publicPath"] == "/images/b.png"


class TestParseToolCall:
    def test_parses_simple_call(self):
        response = "ACTION: WRITE_FILE(component_name='Hero', code='''export default function Hero() {}''')"
        args = agent_module.FigmaAgent.parse_tool_call(response, "WRITE_FILE")
        assert args == {"component_name": "Hero", "code": "export default function Hero() {}"}

    def test_returns_none_when_marker_missing(self):
        assert agent_module.FigmaAgent.parse_tool_call("no action", "WRITE_FILE") is None


class TestExtractCode:
    def test_extracts_tsx_block(self):
        response = "```tsx\nexport default function Hero() {}\n```"
        assert agent_module.FigmaAgent.extract_code(response) == "export default function Hero() {}"

    def test_extracts_plain_block(self):
        response = "```\nconst x = 1\n```"
        assert agent_module.FigmaAgent.extract_code(response) == "const x = 1"

    def test_returns_none_when_no_block(self):
        assert agent_module.FigmaAgent.extract_code("plain text") is None


class TestFigmaAgentLoadContext:
    def test_loads_context_file(self, sample_context):
        figma_agent = agent_module.FigmaAgent()
        context, selected = figma_agent.load_context(sample_context, download_assets=False)
        assert isinstance(context, str)
        assert selected["name"] == "Hero Section"

    def test_loads_specific_node(self, tmp_path):
        child = {"id": "2:2", "name": "Child", "type": "TEXT", "visible": True, "characters": "x"}
        root = {"id": "1:1", "name": "Root", "type": "FRAME", "children": [child]}
        path = tmp_path / "figma_node.json"
        path.write_text(json.dumps(root), encoding="utf-8")

        figma_agent = agent_module.FigmaAgent()
        _context, selected = figma_agent.load_context(str(path), node_id="2:2", download_assets=False)
        assert selected["name"] == "Child"


class TestFigmaAgentCallLLM:
    def test_calls_local_ollama(self, monkeypatch):
        class FakeResponse:
            status_code = 200
            text = "{}"

            def json(self):
                return {"choices": [{"message": {"content": "LLM reply"}}]}

        captured = {}

        def fake_post(url, data, headers, timeout):
            captured["url"] = url
            captured["headers"] = headers
            return FakeResponse()

        monkeypatch.setattr(agent_module.requests, "post", fake_post)
        monkeypatch.setenv("LLM_API_URL", "http://localhost:11434/v1/chat/completions")

        figma_agent = agent_module.FigmaAgent()
        figma_agent.api_key = "ollama-dummy-key"
        result = figma_agent.call_llm("task", "{}")
        assert result == "LLM reply"
        assert captured["url"] == "http://localhost:11434/v1/chat/completions"

    def test_handles_non_200_status(self, monkeypatch):
        class FakeResponse:
            status_code = 500
            text = "Server error"

            def json(self):
                return {"error": "Server error"}

        monkeypatch.setattr(agent_module.requests, "post", lambda *args, **kwargs: FakeResponse())

        figma_agent = agent_module.FigmaAgent()
        with pytest.raises(SystemExit):
            figma_agent.call_llm("task", "{}")


class TestFigmaAgentExecute:
    def test_execute_writes_file_via_tool_call(self, sample_context, monkeypatch):
        figma_agent = agent_module.FigmaAgent()

        def fake_call_llm(task, context_data, semantic_summary=""):
            return "ACTION: WRITE_FILE(component_name='HeroSection', code='''export default function HeroSection() { return <div>Hero</div>; }''')"

        monkeypatch.setattr(figma_agent, "call_llm", fake_call_llm)
        monkeypatch.setattr(agent_module.file_writer, "write_component", lambda name, code: f"SUCCESS: {name}")

        figma_agent.execute("task", "{}", selected_node={"name": "Hero Section"})
        # Should not raise and should call write_component via handle_tool_calls.

    def test_execute_falls_back_to_markdown_block(self, sample_context, monkeypatch):
        figma_agent = agent_module.FigmaAgent()

        def fake_call_llm(task, context_data, semantic_summary=""):
            return "```tsx\nexport default function Fallback() {}\n```"

        monkeypatch.setattr(figma_agent, "call_llm", fake_call_llm)
        written = {}
        monkeypatch.setattr(agent_module.file_writer, "write_component", lambda name, code: written.update({name: code}))

        figma_agent.execute("task", "{}", output_name="Fallback", selected_node={"name": "Hero Section"})
        assert "Fallback" in written

    def test_execute_warns_when_no_code_and_no_name(self, sample_context, monkeypatch):
        figma_agent = agent_module.FigmaAgent()

        def fake_call_llm(task, context_data, semantic_summary=""):
            return "plain text without code"

        monkeypatch.setattr(figma_agent, "call_llm", fake_call_llm)
        figma_agent.execute("task", "{}")  # No output_name, no selected_node
