"""pytest tests for the Open Design bridge.

Uses monkeypatch on urllib.request to avoid needing a real Open Design Desktop
instance running on localhost.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import pytest

from runtime.premium_design.open_design_bridge import OpenDesignBridge, OpenDesignBridgeResult


@pytest.fixture
def bridge(tmp_path: Path) -> OpenDesignBridge:
    return OpenDesignBridge(workspace_root=tmp_path, port=8123)


def test_sync_skill_missing_file(bridge: OpenDesignBridge) -> None:
    result = bridge.sync_skill()
    assert result.ok is False
    assert result.errors
    assert "Skill file not found" in result.errors[0]


class _FakeResponse:
    """Minimal context-manager response stand-in for urllib.request.urlopen."""

    def __init__(self, status: int, body: bytes):
        self.status = status
        self._body = body

    def __enter__(self) -> "_FakeResponse":
        return self

    def __exit__(self, *exc: Any) -> None:
        return None

    def read(self) -> bytes:
        return self._body


def test_sync_skill_success(bridge: OpenDesignBridge, tmp_path: Path, monkeypatch: Any) -> None:
    skill = tmp_path / ".claude" / "skills"
    skill.mkdir(parents=True)
    skill_file = skill / "premium-design.skill.md"
    skill_file.write_text("## 02. 44 anti-slop rules\nno slop\n## 03.\n")

    calls = []

    def fake_urlopen(req, **kwargs: Any) -> _FakeResponse:
        calls.append(req)
        return _FakeResponse(201, b'{"id": "skill-123"}')

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)

    result = bridge.sync_skill()
    assert result.ok is True
    assert result.skill_id == "skill-123"
    assert result.policy_synced is True
    assert calls


def test_sync_tokens_missing(bridge: OpenDesignBridge) -> None:
    result = bridge.sync_tokens()
    assert result.ok is False
    assert "Tokens not found" in result.errors[0]


def test_sync_tokens_success(bridge: OpenDesignBridge, tmp_path: Path, monkeypatch: Any) -> None:
    tokens = tmp_path / "design_tokens.json"
    tokens.write_text('{"color": {"surface": {"$value": "#0a0a0a"}}}')

    monkeypatch.setattr(
        "urllib.request.urlopen",
        lambda req, **kwargs: _FakeResponse(200, b'{}'),
    )

    result = bridge.sync_tokens()
    assert result.ok is True
    assert result.tokens_synced is True


def test_pull_policy(bridge: OpenDesignBridge, monkeypatch: Any) -> None:
    monkeypatch.setattr(
        "urllib.request.urlopen",
        lambda url, **kwargs: _FakeResponse(200, b'{"variance": 0.5}'),
    )
    policy = bridge.pull_policy()
    assert policy.get("variance") == 0.5


def test_full_sync_short_circuits_on_skill_failure(bridge: OpenDesignBridge) -> None:
    result = bridge.full_sync()
    assert result.ok is False
    assert not result.tokens_synced
