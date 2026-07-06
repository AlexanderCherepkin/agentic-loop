from __future__ import annotations

import shutil
import time
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any


class ResourceLevel(str, Enum):
    GREEN = "green"
    WARNING = "warning"
    CRITICAL = "critical"


@dataclass
class ResourceSnapshot:
    cpu_percent: float | None
    memory_percent: float | None
    disk_percent: float | None
    timestamp: float


@dataclass
class ResourceCheckResult:
    level: ResourceLevel
    reason: str
    snapshot: ResourceSnapshot
    thresholds: dict[str, Any]


class ResourceMonitor:
    """Runtime watchdog for CPU, memory, and workspace disk usage.

    The monitor is deterministic and intentionally cheap: it samples system
    metrics at checkpoint boundaries (pipeline start and each ReAct iteration)
    and returns a verdict. CRITICAL results abort execution to prevent the
    autonomous bot from exhausting the host.

    `psutil` is optional. Without it, only disk usage is available (via shutil),
    and CPU/RAM checks always return GREEN unless explicitly disabled.
    """

    DEFAULT_THRESHOLDS = {
        "cpu_warning": 70.0,
        "cpu_critical": 90.0,
        "memory_warning": 75.0,
        "memory_critical": 90.0,
        "disk_warning": 80.0,
        "disk_critical": 95.0,
    }

    def __init__(
        self,
        workspace_root: str | Path = ".",
        thresholds: dict[str, float] | None = None,
        disable_psutil: bool = False,
    ):
        self.workspace = Path(workspace_root).resolve()
        self.thresholds = {**self.DEFAULT_THRESHOLDS, **(thresholds or {})}
        self._disable_psutil = disable_psutil
        self._psutil = self._load_psutil()

    def _load_psutil(self) -> Any:
        if self._disable_psutil:
            return None
        try:
            import psutil
            return psutil
        except Exception:
            return None

    def check(self) -> ResourceCheckResult:
        """Sample current resource usage and return a verdict."""
        snapshot = self._sample()
        level = ResourceLevel.GREEN
        reasons: list[str] = []

        if snapshot.cpu_percent is not None:
            if snapshot.cpu_percent >= self.thresholds["cpu_critical"]:
                level = ResourceLevel.CRITICAL
                reasons.append(f"CPU {snapshot.cpu_percent:.1f}% >= critical {self.thresholds['cpu_critical']:.1f}%")
            elif snapshot.cpu_percent >= self.thresholds["cpu_warning"] and level != ResourceLevel.CRITICAL:
                level = ResourceLevel.WARNING
                reasons.append(f"CPU {snapshot.cpu_percent:.1f}% >= warning {self.thresholds['cpu_warning']:.1f}%")

        if snapshot.memory_percent is not None:
            if snapshot.memory_percent >= self.thresholds["memory_critical"]:
                level = ResourceLevel.CRITICAL
                reasons.append(f"Memory {snapshot.memory_percent:.1f}% >= critical {self.thresholds['memory_critical']:.1f}%")
            elif snapshot.memory_percent >= self.thresholds["memory_warning"] and level != ResourceLevel.CRITICAL:
                level = ResourceLevel.WARNING
                reasons.append(f"Memory {snapshot.memory_percent:.1f}% >= warning {self.thresholds['memory_warning']:.1f}%")

        disk_level = self._classify_disk(snapshot.disk_percent)
        if disk_level == ResourceLevel.CRITICAL:
            level = ResourceLevel.CRITICAL
            reasons.append(f"Disk {snapshot.disk_percent:.1f}% >= critical {self.thresholds['disk_critical']:.1f}%")
        elif disk_level == ResourceLevel.WARNING and level != ResourceLevel.CRITICAL:
            level = ResourceLevel.WARNING
            reasons.append(f"Disk {snapshot.disk_percent:.1f}% >= warning {self.thresholds['disk_warning']:.1f}%")

        return ResourceCheckResult(
            level=level,
            reason="; ".join(reasons) if reasons else "Resources within safe limits",
            snapshot=snapshot,
            thresholds=self.thresholds,
        )

    def _sample(self) -> ResourceSnapshot:
        cpu: float | None = None
        memory: float | None = None
        disk: float | None = None

        if self._psutil:
            try:
                cpu = self._psutil.cpu_percent(interval=0.1)
                memory = self._psutil.virtual_memory().percent
            except Exception:
                pass

        try:
            usage = shutil.disk_usage(str(self.workspace))
            if usage.total > 0:
                disk = (usage.used / usage.total) * 100.0
        except Exception:
            pass

        return ResourceSnapshot(
            cpu_percent=cpu,
            memory_percent=memory,
            disk_percent=disk,
            timestamp=time.time(),
        )

    def _classify_disk(self, disk_percent: float | None) -> ResourceLevel:
        if disk_percent is None:
            return ResourceLevel.GREEN
        if disk_percent >= self.thresholds["disk_critical"]:
            return ResourceLevel.CRITICAL
        if disk_percent >= self.thresholds["disk_warning"]:
            return ResourceLevel.WARNING
        return ResourceLevel.GREEN

    def is_critical(self) -> bool:
        return self.check().level == ResourceLevel.CRITICAL

    def to_dict(self) -> dict[str, Any]:
        result = self.check()
        return {
            "level": result.level.value,
            "reason": result.reason,
            "snapshot": {
                "cpu_percent": result.snapshot.cpu_percent,
                "memory_percent": result.snapshot.memory_percent,
                "disk_percent": result.snapshot.disk_percent,
                "timestamp": result.snapshot.timestamp,
            },
            "thresholds": result.thresholds,
        }
