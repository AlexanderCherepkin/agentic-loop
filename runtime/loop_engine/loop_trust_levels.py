"""Runtime trust-level policy for loop operations."""

from __future__ import annotations

# Operations that are safe to run autonomously only at report-only L1.
READ_ONLY_OPERATIONS: frozenset[str] = frozenset(
    {
        "audit",
        "report",
        "read",
        "scan",
        "inspect",
        "summarize",
        "check",
        "list",
    }
)

# Operations that must remain under human approval (L2 or higher; never L3 autonomous).
NEVER_AUTONOMOUS_OPERATIONS: frozenset[str] = frozenset(
    {
        "git push",
        "deploy",
        "rm -rf",
        "database migration",
        "db migration",
        "migration",
        "production secret",
        "payment",
        "bulk email",
    }
)


def classify_operation(operation: str) -> str:
    """Return the maximum trust level allowed for an operation.

    - L1: read-only / report-only operations.
    - L2: supervised; never autonomous. Used for all mutating operations and
          dangerous operations explicitly listed as human zones.
    - L3 is never returned by this function; autonomous mode is decided by
      the loop runtime after L2 stability metrics and human approval.
    """
    op = operation.strip().lower()
    if op in NEVER_AUTONOMOUS_OPERATIONS:
        return "L2"
    if op in READ_ONLY_OPERATIONS:
        return "L1"
    return "L2"


def can_run_autonomous(level: str, operation: str) -> bool:
    """Return True only if the operation is allowed at L3 (autonomous).

    Only read-only L1 operations may run without approval at L3. All mutating
    or dangerous operations stay supervised (L2) even under L3 loop autonomy.
    """
    if level != "L3":
        return False
    return classify_operation(operation) == "L1"


def validate_level_transition(current: str, proposed: str, days_stable: int, rejection_rate: float) -> dict[str, Any]:
    """Validate a trust-level promotion request."""
    from typing import Any

    rules: dict[tuple[str, str], tuple[int, float]] = {
        ("L1", "L2"): (7, 1.0),
        ("L2", "L3"): (30, 0.05),
    }
    required_days, max_rejection = rules.get((current, proposed), (0, 0.0))
    allowed = days_stable >= required_days and rejection_rate <= max_rejection
    return {
        "allowed": allowed,
        "current": current,
        "proposed": proposed,
        "required_days": required_days,
        "actual_days": days_stable,
        "max_rejection_rate": max_rejection,
        "actual_rejection_rate": rejection_rate,
        "reason": "ok" if allowed else "insufficient stability or too many rejections",
    }
