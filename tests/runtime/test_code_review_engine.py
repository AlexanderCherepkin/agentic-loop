"""Unit tests for the CodeReviewer engine."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from runtime.code_review.config import CodeReviewConfig
from runtime.code_review.engine import CodeIssue, CodeReviewer, ReviewResult, _extract_json


class FakeLLMEngine:
    """Deterministic LLM engine double for code review tests."""

    def __init__(self, responses: list[str] | None = None):
        self.responses = responses or []
        self.calls: list[tuple[str, str, dict]] = []

    async def raw_chat_completion(
        self,
        system: str,
        user: str,
        temperature: float = 0.0,
    ) -> str:
        self.calls.append((system, user, {"temperature": temperature}))
        if self.responses:
            return self.responses.pop(0)
        return json.dumps(
            {
                "overall_score": 7.5,
                "summary": "Review summary",
                "issues": [],
                "suggestions": [],
            },
            ensure_ascii=False,
        )


@pytest.fixture
def review_llm():
    return FakeLLMEngine()


class TestExtractJson:
    def test_extracts_from_code_block(self):
        text = "```json\n{\"a\": 1}\n```"
        assert _extract_json(text) == {"a": 1}

    def test_extracts_first_braced_object(self):
        text = "Some text {\"a\": 1} trailing"
        assert _extract_json(text) == {"a": 1}

    def test_returns_raw_when_no_json(self):
        text = "no json here"
        assert _extract_json(text) == {"raw_output": text}

    def test_returns_raw_on_invalid_json(self):
        text = "{not valid json}"
        assert _extract_json(text) == {"raw_output": text}


@pytest.mark.asyncio
class TestCodeReviewerReview:
    async def test_review_returns_structured_result(self, review_llm):
        reviewer = CodeReviewer(llm=review_llm)
        result = await reviewer.review(
            brief="Build a landing page.",
            manifest="Use Next.js.",
            codebase={"page.tsx": "export default function Page() {}"},
        )
        assert isinstance(result, ReviewResult)
        assert result.overall_score == 7.5
        assert result.summary == "Review summary"

    async def test_review_parses_issues(self, review_llm):
        review_llm.responses.append(
            json.dumps(
                {
                    "overall_score": 6.0,
                    "summary": "Found issues.",
                    "issues": [
                        {
                            "file": "page.tsx",
                            "severity": "major",
                            "line": 10,
                            "title": "Missing key",
                            "description": "Array items need keys.",
                            "suggestion": "Add a key prop.",
                        }
                    ],
                    "suggestions": ["Use semantic HTML."],
                },
                ensure_ascii=False,
            )
        )
        reviewer = CodeReviewer(llm=review_llm)
        result = await reviewer.review("brief", "manifest", {"page.tsx": "code"})
        assert len(result.issues) == 1
        issue = result.issues[0]
        assert isinstance(issue, CodeIssue)
        assert issue.file == "page.tsx"
        assert issue.severity == "major"
        assert issue.line == 10
        assert result.suggestions == ["Use semantic HTML."]

    async def test_review_skips_malformed_issues(self, review_llm):
        review_llm.responses.append(
            json.dumps(
                {
                    "overall_score": 5.0,
                    "summary": "Mixed.",
                    "issues": [
                        {"file": "ok.tsx", "severity": "minor", "title": "OK", "description": "d", "suggestion": "s"},
                        {"file": "bad.tsx"},  # missing required fields
                    ],
                    "suggestions": [],
                },
                ensure_ascii=False,
            )
        )
        reviewer = CodeReviewer(llm=review_llm)
        result = await reviewer.review("brief", "manifest", {"ok.tsx": "code"})
        assert len(result.issues) == 1
        assert result.issues[0].file == "ok.tsx"

    async def test_review_includes_codebase_in_prompt(self, review_llm):
        reviewer = CodeReviewer(llm=review_llm)
        await reviewer.review(
            brief="Brief text",
            manifest="Manifest text",
            codebase={"a.tsx": "const A = 1"},
        )
        assert review_llm.calls
        _system, user, _kwargs = review_llm.calls[0]
        assert "Brief text" in user
        assert "Manifest text" in user
        assert "a.tsx" in user
        assert "const A = 1" in user


@pytest.mark.asyncio
class TestCodeReviewerReviewAndFix:
    async def test_review_and_fix_full_file_mode(self, review_llm):
        review_llm.responses = [
            json.dumps(
                {
                    "overall_score": 6.0,
                    "summary": "Need fix.",
                    "issues": [],
                    "suggestions": [],
                },
                ensure_ascii=False,
            ),
            json.dumps({"page.tsx": "export default function Fixed() {}"}, ensure_ascii=False),
        ]
        config = CodeReviewConfig(diff_mode=False)
        reviewer = CodeReviewer(llm=review_llm, config=config)
        result = await reviewer.review_and_fix("brief", "manifest", {"page.tsx": "broken"})

        assert result.corrected_codebase is not None
        assert result.corrected_codebase["page.tsx"] == "export default function Fixed() {}"
        assert result.diff_mode is False

    async def test_review_and_fix_diff_mode(self, review_llm):
        review_llm.responses = [
            json.dumps(
                {
                    "overall_score": 6.0,
                    "summary": "Need fix.",
                    "issues": [],
                    "suggestions": [],
                },
                ensure_ascii=False,
            ),
            json.dumps(
                [{"file": "page.tsx", "old": "broken", "new": "fixed"}],
                ensure_ascii=False,
            ),
        ]
        config = CodeReviewConfig(diff_mode=True)
        reviewer = CodeReviewer(llm=review_llm, config=config)
        result = await reviewer.review_and_fix("brief", "manifest", {"page.tsx": "broken"})

        assert result.diff_mode is True
        assert result.applied == 1
        assert result.failed == 0
        assert result.corrected_codebase is not None
        assert result.corrected_codebase["page.tsx"] == "fixed"

    async def test_review_and_fix_diff_mode_partial_failure(self, review_llm):
        review_llm.responses = [
            json.dumps(
                {
                    "overall_score": 6.0,
                    "summary": "Need fix.",
                    "issues": [],
                    "suggestions": [],
                },
                ensure_ascii=False,
            ),
            json.dumps(
                [
                    {"file": "page.tsx", "old": "broken", "new": "fixed"},
                    {"file": "page.tsx", "old": "missing", "new": "nope"},
                ],
                ensure_ascii=False,
            ),
        ]
        config = CodeReviewConfig(diff_mode=True)
        reviewer = CodeReviewer(llm=review_llm, config=config)
        result = await reviewer.review_and_fix("brief", "manifest", {"page.tsx": "broken"})

        assert result.applied == 1
        assert result.failed == 1
        assert result.corrected_codebase is not None

    async def test_review_and_fix_full_file_invalid_json(self, review_llm):
        review_llm.responses = [
            json.dumps(
                {
                    "overall_score": 6.0,
                    "summary": "Need fix.",
                    "issues": [],
                    "suggestions": [],
                },
                ensure_ascii=False,
            ),
            "not valid json",
        ]
        config = CodeReviewConfig(diff_mode=False)
        reviewer = CodeReviewer(llm=review_llm, config=config)
        result = await reviewer.review_and_fix("brief", "manifest", {"page.tsx": "broken"})

        assert result.corrected_codebase is None


class TestCodeReviewerConfig:
    def test_default_config(self):
        config = CodeReviewConfig()
        assert config.mode == "review"
        assert config.diff_mode is False
        assert config.severity_threshold == "major"
        assert ".py" in config.allowed_extensions

    def test_to_dict_roundtrips(self):
        config = CodeReviewConfig()
        data = config.to_dict()
        assert data["mode"] == "review"
        assert data["diff_mode"] is False
