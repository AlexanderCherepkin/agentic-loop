"""Drift detection for model economy overrides.

Compares the current effective configuration against both the active mode
-template and the last persisted snapshot. Non-critical drift is flagged and
returned; critical drift can be escalated to a hard block by the caller.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from .mode_manager import ModeManager
from .model_economy_config import AUXILIARY_SLOT_KEYS, ModelRef


class DriftSeverity(StrEnum):
    NONE = "none"
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


@dataclass
class DriftReport:
    """Result of a drift-detection pass."""

    severity: DriftSeverity
    template_drifts: list[dict[str, Any]] = field(default_factory=list)
    snapshot_drifts: list[dict[str, Any]] = field(default_factory=list)
    critical: bool = False
    audit_event: dict[str, Any] = field(default_factory=dict)

    @property
    def has_drift(self) -> bool:
        return bool(self.template_drifts or self.snapshot_drifts)


def _model_refs_equal(a: ModelRef, b: ModelRef) -> bool:
    return a.provider.lower() == b.provider.lower() and a.model == b.model


def _format_drift(slot: str, expected: ModelRef, actual: ModelRef, kind: str) -> dict[str, Any]:
    return {
        "slot": slot,
        "kind": kind,
        "expected_provider": expected.provider,
        "expected_model": expected.model,
        "actual_provider": actual.provider,
        "actual_model": actual.model,
    }


class DriftDetector:
    """Compare effective overrides against the active mode template and snapshot."""

    def detect(
        self,
        mode_manager: ModeManager,
        critical: bool = False,
    ) -> DriftReport:
        """Return a drift report for the supplied mode manager state.

        Args:
            mode_manager: Source of active mode, overrides, and snapshot.
            critical: If ``True`` and drift is found, escalate severity to ``CRITICAL``.

        Returns:
            A ``DriftReport`` with template and snapshot deltas plus an audit event.
        """
        mode = mode_manager.active_mode
        current_refs = mode_manager.current_effective_refs()
        snapshot_refs = mode_manager.snapshot

        template_drifts: list[dict[str, Any]] = []
        slots = ["main", *AUXILIARY_SLOT_KEYS]
        for slot in slots:
            expected = mode.model_for(slot)
            actual = current_refs.get(slot, expected)
            if not _model_refs_equal(expected, actual):
                template_drifts.append(_format_drift(slot, expected, actual, "template"))

        snapshot_drifts: list[dict[str, Any]] = []
        for slot, expected in snapshot_refs.items():
            actual = current_refs.get(slot)
            if actual is None:
                continue
            if not _model_refs_equal(expected, actual):
                snapshot_drifts.append(_format_drift(slot, expected, actual, "snapshot"))

        severity = DriftSeverity.NONE
        if template_drifts:
            severity = DriftSeverity.WARNING
        elif snapshot_drifts:
            severity = DriftSeverity.INFO

        if critical and (template_drifts or snapshot_drifts):
            severity = DriftSeverity.CRITICAL

        audit_event = {
            "event_type": "model_economy_drift",
            "timestamp": datetime.now(UTC).isoformat(),
            "active_mode": mode.name,
            "severity": severity.value,
            "template_drift_count": len(template_drifts),
            "snapshot_drift_count": len(snapshot_drifts),
            "details": {"template": template_drifts, "snapshot": snapshot_drifts},
        }

        return DriftReport(
            severity=severity,
            template_drifts=template_drifts,
            snapshot_drifts=snapshot_drifts,
            critical=critical and bool(template_drifts or snapshot_drifts),
            audit_event=audit_event,
        )
