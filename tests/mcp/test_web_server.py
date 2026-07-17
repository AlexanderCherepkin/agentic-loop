"""pytest tests for the Web MCP server.

These tests verify tool registration, request building, auth, rate limiting,
response parsing/extraction, retry strategy, and error analysis without making
real network calls unless necessary.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import sys
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

# Ensure project root is on PYTHONPATH
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import pytest

from mcp_servers.web_server import WebMCPServer


@pytest.fixture
def web_server() -> WebMCPServer:
    return WebMCPServer(".")


def test_web_server_initializes(web_server: WebMCPServer) -> None:
    assert web_server.name == "tools_web"
    tools = web_server.get_tools_list()
    assert len(tools) == 10
    names = {t["name"] for t in tools}
    expected = {
        "build_request", "add_auth", "check_network", "check_rate_limit",
        "send_request", "parse_response", "web_extract_content", "cache_response",
        "handle_retry", "web_analyze_error",
    }
    assert names == expected


def test_web_server_ping(web_server: WebMCPServer) -> None:
    assert asyncio.run(web_server.ping()) is True


def test_web_tool_schemas(web_server: WebMCPServer) -> None:
    for tool in web_server.get_tools_list():
        assert "name" in tool
        assert "description" in tool
        assert "inputSchema" in tool
        schema = tool["inputSchema"]
        assert schema.get("type") == "object"
        assert "properties" in schema


def test_build_request(web_server: WebMCPServer) -> None:
    result = asyncio.run(web_server.build_request(method="GET", url="https://example.com/api"))
    assert result["method"] == "GET"
    assert result["url"] == "https://example.com/api"


def test_add_auth_bearer(web_server: WebMCPServer) -> None:
    result = asyncio.run(web_server.add_auth(headers={}, auth_type="bearer", credentials="token"))
    assert result["headers"]["Authorization"] == "Bearer token"


def test_add_auth_basic(web_server: WebMCPServer) -> None:
    result = asyncio.run(web_server.add_auth(headers={}, auth_type="basic", credentials="user:pass"))
    assert "Basic" in result["headers"]["Authorization"]


def test_check_rate_limit(web_server: WebMCPServer) -> None:
    result = asyncio.run(web_server.check_rate_limit(domain="example.com", max_requests_per_minute=2))
    assert result["allowed"] is True
    result2 = asyncio.run(web_server.check_rate_limit(domain="example.com", max_requests_per_minute=2))
    assert result2["allowed"] is True
    result3 = asyncio.run(web_server.check_rate_limit(domain="example.com", max_requests_per_minute=2))
    assert result3["allowed"] is False


def test_send_request_uses_cache(web_server: WebMCPServer) -> None:
    body = '{"ok": true}'
    cached_payload = json.dumps({"body": body, "status_code": 200})
    # Prime the same internal cache key send_request uses: md5(method:url:body)
    cache_key = hashlib.md5(f"GET:https://example.com/cached:".encode()).hexdigest()
    web_server._cache[cache_key] = (time.time(), cached_payload)
    with patch("mcp_servers.web_server.urllib.request.urlopen") as mock_urlopen:
        mock_urlopen.side_effect = Exception("should not be called when cached")
        result = asyncio.run(web_server.send_request(method="GET", url="https://example.com/cached"))
    assert result.get("body") == body
    assert result.get("status_code") == 200
    assert mock_urlopen.called is False


def test_parse_response_json(web_server: WebMCPServer) -> None:
    result = asyncio.run(web_server.parse_response(response_body='{"x":1}', content_type="application/json"))
    assert result["parsed"] is True
    assert result["parsed_type"] == "dict"


def test_extract_content_json(web_server: WebMCPServer) -> None:
    result = asyncio.run(web_server.extract_content(body='{"a":1,"b":2}', content_type="application/json"))
    assert set(result["keys"]) == {"a", "b"}


def test_extract_content_html(web_server: WebMCPServer) -> None:
    result = asyncio.run(web_server.extract_content(body="<p>hello</p><a href='/x'>link</a>", content_type="text/html"))
    assert result["text"] == "hello link"
    assert "/x" in result["links"]


def test_handle_retry_429(web_server: WebMCPServer) -> None:
    result = asyncio.run(web_server.handle_retry(url="https://example.com", status_code=429, attempt=1))
    assert result["should_retry"] is True
    assert result["wait_ms"] == 2000


def test_analyze_error(web_server: WebMCPServer) -> None:
    result = asyncio.run(web_server.analyze_error(status_code=404))
    assert result["type"] == "not_found"
