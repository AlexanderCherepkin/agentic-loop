"""Tests for Web Project Agents deterministic helpers and config."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from runtime.web_project_agents import (
    ProjectArchitect,
    ProjectClassifier,
    ProjectDeveloper,
    WebProjectAgentsConfig,
)
from runtime.web_project_agents.classifier import ClassificationCache, _extract_json
from runtime.web_project_agents.config import (
    ProjectArchitectConfig,
    ProjectClassifierConfig,
    ProjectDeveloperConfig,
)
from runtime.web_project_agents.prompts import PromptManifest


pytestmark = [pytest.mark.core, pytest.mark.runtime]


def test_config_to_dict():
    cfg = WebProjectAgentsConfig(
        classifier=ProjectClassifierConfig(use_cache=False),
        architect=ProjectArchitectConfig(include_adr=True),
        developer=ProjectDeveloperConfig(default_language="typescript"),
    )
    data = cfg.to_dict()
    assert data["classifier"]["use_cache"] is False
    assert data["architect"]["include_adr"] is True
    assert data["developer"]["default_language"] == "typescript"
    assert "prompt_manifest_path" in data


def test_extract_json_from_fence():
    text = '```json\n{"project_type": {"base_category": "SaaS"}}\n```'
    data = _extract_json(text)
    assert data["project_type"]["base_category"] == "SaaS"


def test_extract_json_without_fence():
    text = 'prefix {"project_type": {"base_category": "Blog"}} suffix'
    data = _extract_json(text)
    assert data["project_type"]["base_category"] == "Blog"


def test_extract_json_invalid_returns_raw():
    assert _extract_json("not json") == {"raw_output": "not json"}


def test_classification_cache_key_normalizes_text(tmp_path):
    db = tmp_path / "cache.db"
    cache = ClassificationCache(str(db), ttl_seconds=60)
    key1 = cache._key("  Hello   World  ", "python")
    key2 = cache._key("hello world", "python")
    assert key1 == key2
    assert key1 == "python:hello world"


def test_classification_cache_round_trip(tmp_path):
    db = tmp_path / "cache.db"
    cache = ClassificationCache(str(db), ttl_seconds=60)
    result = {"project_type": {"base_category": "E-commerce"}}
    cache.set("brief", result, language="python")
    assert cache.get("brief", language="python") == result


def test_classification_cache_expires(tmp_path):
    db = tmp_path / "cache.db"
    cache = ClassificationCache(str(db), ttl_seconds=0)
    cache.set("brief", {"x": 1})
    assert cache.get("brief") is None


def test_classification_cache_corrupt_json_returns_none(tmp_path):
    db = tmp_path / "cache.db"
    cache = ClassificationCache(str(db), ttl_seconds=60)
    cache._ensure_table()
    import sqlite3

    with sqlite3.connect(str(db)) as conn:
        conn.execute(
            "INSERT OR REPLACE INTO classifications (key, result, created_at) VALUES (?, ?, ?)",
            ("auto:bad", "not json", 0.0),
        )
    assert cache.get("bad") is None


@pytest.mark.asyncio
async def test_classifier_returns_cached_result(tmp_path):
    class DummyLLM:
        pass

    cfg = ProjectClassifierConfig(use_cache=True, cache_db_path=str(tmp_path / "cache.db"))
    classifier = ProjectClassifier(llm=DummyLLM(), config=cfg)  # type: ignore[arg-type]
    expected = {"project_type": {"base_category": "SaaS"}}
    classifier._cache.set("blog with payments", expected)
    result = await classifier.classify("blog with payments")
    assert result == expected


@pytest.mark.asyncio
async def test_classifier_empty_brief_raises():
    classifier = ProjectClassifier(llm=object())  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="empty"):
        await classifier.classify("   ")


@pytest.mark.asyncio
async def test_classifier_parses_llm_json(tmp_path):
    class DummyLLM:
        async def raw_chat_completion(self, *, system: str, user: str, temperature: float):
            return '{"project_type": {"base_category": "LMS", "modules": ["courses"]}}'

    cfg = ProjectClassifierConfig(use_cache=False, cache_db_path=str(tmp_path / "cache.db"))
    classifier = ProjectClassifier(llm=DummyLLM(), config=cfg)  # type: ignore[arg-type]
    result = await classifier.classify("online courses", language="python")
    assert result["project_type"]["base_category"] == "LMS"


@pytest.mark.asyncio
async def test_architect_returns_manifest():
    class DummyLLM:
        async def raw_chat_completion(self, *, system: str, user: str, temperature: float):
            return "# Architecture\nUse FastAPI."

    architect = ProjectArchitect(llm=DummyLLM())  # type: ignore[arg-type]
    result = await architect.design({"project_type": {"base_category": "SaaS"}})
    assert result == "# Architecture\nUse FastAPI."


@pytest.mark.asyncio
async def test_architect_with_adr_returns_tuple():
    class DummyLLM:
        async def raw_chat_completion(self, *, system: str, user: str, temperature: float):
            if "ADR" in system:
                return "## Decision\nUse FastAPI."
            return "# Architecture\nUse FastAPI."

    architect = ProjectArchitect(
        llm=DummyLLM(),  # type: ignore[arg-type]
        config=ProjectArchitectConfig(include_adr=True),
    )
    manifest, adr = await architect.design({"project_type": {"base_category": "SaaS"}})
    assert "Architecture" in manifest
    assert "Decision" in adr


@pytest.mark.asyncio
async def test_developer_parses_codebase():
    class DummyLLM:
        async def raw_chat_completion(self, *, system: str, user: str, temperature: float):
            return '{"README.md": "# X", "main.py": "print(1)"}'

    developer = ProjectDeveloper(llm=DummyLLM())  # type: ignore[arg-type]
    result = await developer.develop("manifest", language="python")
    assert result["README.md"] == "# X"
    assert result["main.py"] == "print(1)"


@pytest.mark.asyncio
async def test_developer_returns_raw_dict_on_non_dict():
    class DummyLLM:
        async def raw_chat_completion(self, *, system: str, user: str, temperature: float):
            return "not a dict"

    developer = ProjectDeveloper(llm=DummyLLM())  # type: ignore[arg-type]
    result = await developer.develop("manifest")
    # _extract_json wraps non-JSON in {"raw_output": text}, which is a dict,
    # so the developer returns it without raising.
    assert result == {"raw_output": "not a dict"}


def test_prompt_manifest_missing_file_returns_none(tmp_path):
    manifest = PromptManifest(path=tmp_path / "missing.yaml")
    assert manifest.get_system_prompt("classifier") is None
