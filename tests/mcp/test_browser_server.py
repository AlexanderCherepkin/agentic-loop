"""pytest tests for the Browser MCP server.

These tests verify tool registration, degraded mode when Playwright is missing,
URL parsing, error sanitization, PII redaction, and approval gating for
interactive actions.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

# Ensure project root is on PYTHONPATH
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import pytest

from mcp_servers.browser_server import BrowserMCPServer


@pytest.fixture
def browser_server(tmp_path: Path) -> BrowserMCPServer:
    return BrowserMCPServer(str(tmp_path))


def test_browser_server_initializes(browser_server: BrowserMCPServer) -> None:
    assert browser_server.name == "tools_browser"
    tools = browser_server.get_tools_list()
    assert len(tools) == 10
    names = {t["name"] for t in tools}
    expected = {
        "browser_open", "browser_navigate", "browser_screenshot",
        "browser_extract", "browser_click", "browser_type", "browser_scroll",
        "browser_evaluate", "browser_cookies", "browser_close",
    }
    assert names == expected


def test_browser_server_ping(browser_server: BrowserMCPServer) -> None:
    assert asyncio.run(browser_server.ping()) is True


def test_browser_tool_schemas(browser_server: BrowserMCPServer) -> None:
    for tool in browser_server.get_tools_list():
        assert "name" in tool
        assert "description" in tool
        assert "inputSchema" in tool
        schema = tool["inputSchema"]
        assert schema.get("type") == "object"
        assert "properties" in schema


def test_browser_open_degraded_without_playwright(browser_server: BrowserMCPServer) -> None:
    browser_server._degraded_reason = "Playwright not installed"
    result = asyncio.run(browser_server.browser_open(session_id="s1"))
    assert result["status"] == "degraded"
    assert "Playwright" in result["error"]


def test_browser_click_blocked_without_approval(browser_server: BrowserMCPServer) -> None:
    browser_server._pages["s1"] = MagicMock()
    result = asyncio.run(browser_server.browser_click(session_id="s1", selector="button"))
    assert result["interaction_status"] == "blocked"


def test_browser_type_blocked_without_approval(browser_server: BrowserMCPServer) -> None:
    browser_server._pages["s1"] = MagicMock()
    result = asyncio.run(browser_server.browser_type(session_id="s1", selector="input", value="x"))
    assert result["interaction_status"] == "blocked"


def test_browser_evaluate_blocks_read_only_false(browser_server: BrowserMCPServer) -> None:
    browser_server._pages["s1"] = MagicMock()
    result = asyncio.run(browser_server.browser_evaluate(session_id="s1", expression="1+1", read_only=False))
    assert result["status"] == "blocked"


def test_browser_close_unknown_session(browser_server: BrowserMCPServer) -> None:
    result = asyncio.run(browser_server.browser_close(session_id="missing"))
    assert result["status"] == "closed"


def test_parse_url(browser_server: BrowserMCPServer) -> None:
    result = BrowserMCPServer._parse_url("https://example.com/path?x=1")
    assert result["scheme"] == "https"
    assert result["host"] == "example.com"
    assert result["path"] == "/path"


def test_sanitize_redacts_tokens(browser_server: BrowserMCPServer) -> None:
    text = "token abcdef0123456789abcdef0123456789abcdef01"
    sanitized = BrowserMCPServer._sanitize(text)
    assert "[REDACTED]" in sanitized


def test_redact_text_email(browser_server: BrowserMCPServer) -> None:
    result = BrowserMCPServer._redact_text("contact user@example.com please")
    assert "[REDACTED:email]" in result


def test_redact_cookies(browser_server: BrowserMCPServer) -> None:
    cookies = [{"name": "session", "value": "secret", "domain": "example.com"}]
    result = BrowserMCPServer._redact_cookies(cookies)
    assert result[0]["value"] == "[REDACTED]"
    assert result[0]["domain"] == "example.com"


def test_browser_navigate_blocks_non_http(browser_server: BrowserMCPServer) -> None:
    browser_server._pages["s1"] = MagicMock()
    result = asyncio.run(browser_server.browser_navigate(session_id="s1", url="file:///etc/passwd"))
    assert result["navigation_status"] == "blocked"


def test_browser_navigate_blocks_unallowed_domain(browser_server: BrowserMCPServer) -> None:
    browser_server._pages["s1"] = MagicMock()
    result = asyncio.run(browser_server.browser_navigate(
        session_id="s1", url="https://evil.com", allowed_domains=["example.com"]
    ))
    assert result["navigation_status"] == "blocked"
