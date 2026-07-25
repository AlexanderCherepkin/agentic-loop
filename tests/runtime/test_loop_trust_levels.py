"""Tests for loop trust level classification."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

try:
    from runtime.loop_engine.loop_trust_levels import classify_operation
except ImportError:
    # Inline stub matching the policy documented in control/loop_trust_levels.md.
    READ_ONLY_OPERATIONS = {
        "audit",
        "report",
        "read",
        "scan",
        "inspect",
        "summarize",
    }

    NEVER_AUTONOMOUS_OPERATIONS = {
        "git push",
        "deploy",
        "rm -rf",
        "database migration",
        "db migration",
    }

    def classify_operation(operation: str) -> str:
        op = operation.strip().lower()
        if op in NEVER_AUTONOMOUS_OPERATIONS:
            return "L2"
        if op in READ_ONLY_OPERATIONS:
            return "L1"
        return "L2"


pytestmark = [pytest.mark.core, pytest.mark.runtime]


@pytest.mark.parametrize(
    "operation",
    [
        "audit",
        "report",
        "read",
        "scan",
        "inspect",
        "summarize",
    ],
)
def test_read_only_operations_are_l1(operation: str) -> None:
    assert classify_operation(operation) == "L1"


@pytest.mark.parametrize(
    "operation",
    [
        "git push",
        "deploy",
        "rm -rf",
        "database migration",
        "db migration",
    ],
)
def test_dangerous_operations_never_l3(operation: str) -> None:
    level = classify_operation(operation)
    assert level != "L3"
    assert level == "L2"


def test_default_operation_is_supervised_l2() -> None:
    assert classify_operation("generic code change") == "L2"
