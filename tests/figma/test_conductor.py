"""Tests for conductor helper functions and dry-run pipeline orchestration."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "figma-agent-core"))

from conductor import (
    _redact_command,
    _to_pascal_case,
    run_pipeline,
)


pytestmark = [pytest.mark.core, pytest.mark.figma]


def test_redact_command_replaces_secret_values():
    command = [
        "python",
        "script.py",
        "--provider-api-key",
        "super-secret",
        "--image-provider-api-key",
        "other-secret",
    ]
    redacted = _redact_command(command)
    assert "super-secret" not in redacted
    assert "other-secret" not in redacted
    assert redacted[redacted.index("--provider-api-key") + 1] == "<REDACTED>"
    assert redacted[redacted.index("--image-provider-api-key") + 1] == "<REDACTED>"


def test_redact_command_leaves_regular_arguments():
    command = ["python", "script.py", "--file", "main.py"]
    assert _redact_command(command) == command


def test_redact_command_custom_secret_flags():
    command = ["python", "script.py", "--token", "abc123"]
    redacted = _redact_command(command, secret_flags={"--token"})
    assert redacted[redacted.index("--token") + 1] == "<REDACTED>"


@pytest.mark.parametrize(
    "name, expected",
    [
        ("Hero Section", "HeroSection"),
        ("cta button", "CtaButton"),
        ("Pricing-Table!", "PricingTable"),
        ("123 start", "Figma123Start"),
        ("", "Figma"),
    ],
)
def test_to_pascal_case(name, expected):
    assert _to_pascal_case(name) == expected


@patch("conductor.analyzer.load_figma_json")
@patch("conductor.analyzer.list_top_level_nodes")
def test_collect_top_level_sections_returns_ids_and_names(mock_list, mock_load):
    mock_load.return_value = {"name": "Page", "children": []}
    mock_list.return_value = [
        {"id": "1:2", "name": "Hero"},
        {"id": "3:4", "name": "Features"},
    ]
    # list_top_level_nodes is imported by name inside _collect_top_level_sections.
    import conductor

    sections = conductor._collect_top_level_sections("figma_node.json")
    assert len(sections) == 2
    assert sections[0]["id"] == "1:2"
    assert sections[1]["name"] == "Features"


def test_run_pipeline_dry_run_records_stages():
    config = {"dry_run": True, "only": "analyze"}
    report = run_pipeline(config)
    assert report["stages"]["analyze"]["success"] is True
    assert "duration_seconds" in report


def test_run_pipeline_unknown_stage_skipped():
    config = {"dry_run": True, "only": "not_a_stage"}
    report = run_pipeline(config)
    assert report["stages"] == {}
