"""Tests for runtime/notifications engine and config."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from runtime.notifications import NotificationsConfig, NotificationsEngine
from runtime.notifications.engine import NotificationPayload


pytestmark = [pytest.mark.core, pytest.mark.runtime]


def test_config_from_dict():
    cfg = NotificationsConfig.from_dict(
        {"channels": ["email"], "emails": ["admin@example.com"]}
    )
    assert cfg.channels == ["email"]
    assert cfg.emails == ["admin@example.com"]


def test_dispatch_disabled_returns_empty():
    engine = NotificationsEngine(NotificationsConfig(channels=[]))
    result = asyncio.run(
        engine.dispatch(NotificationPayload(project_id="p1", status="completed"))
    )
    assert result.dispatched == 0
    assert result.failed == 0


def test_dispatch_unknown_channel_is_skipped():
    engine = NotificationsEngine(NotificationsConfig(channels=["sms"]))
    result = asyncio.run(
        engine.dispatch(NotificationPayload(project_id="p1", status="completed"))
    )
    assert result.dispatched == 0
    assert result.failed == 0


def test_message_builds_payload():
    engine = NotificationsEngine()
    payload = NotificationPayload(
        project_id="p1",
        status="failed",
        brief="Build failed",
        error="No tests",
    )
    message = engine._build_message(payload)
    assert "p1" in message.body_text
    assert "failed" in message.body_text
    assert "No tests" in message.body_text
