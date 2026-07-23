"""Tests for CodeReviewer helpers and prompt building without live LLM calls."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from runtime.code_review import CodeReviewConfig, CodeReviewer
from runtime.code_review.engine import _extract_json


pytestmark = [pytest.mark.core, pytest.mark.runtime]


def test_extract_json_from_code_block():
    text = 'Some words\n```json\n{"overall_score": 8, "summary": "ok"}\n```\nMore words'
    data = _extract_json(text)
    assert data == {"overall_score": 8, "summary": "ok"}


def test_extract_json_without_fence():
    text = 'prefix {"overall_score": 7, "summary": "ok"} suffix'
    data = _extract_json(text)
    assert data == {"overall_score": 7, "summary": "ok"}


def test_extract_json_invalid_returns_raw():
    text = "not json at all"
    data = _extract_json(text)
    assert data == {"raw_output": text}


def test_extract_json_malformed_object_returns_raw():
    text = "{this is not valid json}"
    data = _extract_json(text)
    assert "raw_output" in data


def test_build_prompt_includes_brief_manifest_and_codebase():
    class DummyLLM:
        pass

    reviewer = CodeReviewer(llm=DummyLLM())  # type: ignore[arg-type]
    brief = "Build a landing page"
    manifest = "Use Next.js"
    codebase = {"page.tsx": "export default function Page() {}"}
    prompt = reviewer._build_prompt(brief, manifest, codebase)
    assert "Build a landing page" in prompt
    assert "Use Next.js" in prompt
    assert "page.tsx" in prompt
    dumped = json.dumps(codebase, ensure_ascii=False, indent=2)
    assert dumped in prompt


def test_code_review_config_to_dict():
    cfg = CodeReviewConfig(diff_mode=True, severity_threshold="critical")
    data = cfg.to_dict()
    assert data["diff_mode"] is True
    assert data["severity_threshold"] == "critical"
    assert data["mode"] == "review"
    assert ".py" in data["allowed_extensions"]
