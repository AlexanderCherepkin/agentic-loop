from __future__ import annotations

import os
import sys
from unittest.mock import patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

import pytest

from runtime.observability.resource_monitor import ResourceLevel, ResourceMonitor


class TestResourceMonitorWithoutPsutil:
    def test_disk_only_when_psutil_missing(self, tmp_path):
        monitor = ResourceMonitor(workspace_root=str(tmp_path), disable_psutil=True)
        result = monitor.check()
        assert result.snapshot.cpu_percent is None
        assert result.snapshot.memory_percent is None
        assert result.snapshot.disk_percent is not None
        assert result.level == ResourceLevel.GREEN

    def test_disk_critical_blocks(self, tmp_path):
        monitor = ResourceMonitor(
            workspace_root=str(tmp_path),
            disable_psutil=True,
            thresholds={"disk_warning": 0.0, "disk_critical": 1.0},
        )
        result = monitor.check()
        # Disk usage is always >= 1% on any real filesystem, so should be critical
        assert result.level == ResourceLevel.CRITICAL
        assert "Disk" in result.reason

    def test_disk_warning_level(self, tmp_path):
        monitor = ResourceMonitor(
            workspace_root=str(tmp_path),
            disable_psutil=True,
            thresholds={"disk_warning": 0.0, "disk_critical": 100.0},
        )
        result = monitor.check()
        assert result.level == ResourceLevel.WARNING
        assert "Disk" in result.reason


class TestResourceMonitorWithMockPsutil:
    def test_cpu_critical(self, tmp_path):
        monitor = ResourceMonitor(workspace_root=str(tmp_path))
        fake_psutil = type("P", (), {})()
        fake_psutil.cpu_percent = lambda interval: 95.0
        fake_psutil.virtual_memory = lambda: type("M", (), {"percent": 50.0})()
        monitor._psutil = fake_psutil

        result = monitor.check()
        assert result.level == ResourceLevel.CRITICAL
        assert "CPU" in result.reason

    def test_memory_warning(self, tmp_path):
        monitor = ResourceMonitor(workspace_root=str(tmp_path))
        fake_psutil = type("P", (), {})()
        fake_psutil.cpu_percent = lambda interval: 50.0
        fake_psutil.virtual_memory = lambda: type("M", (), {"percent": 80.0})()
        monitor._psutil = fake_psutil

        result = monitor.check()
        assert result.level == ResourceLevel.WARNING
        assert "Memory" in result.reason

    def test_all_green(self, tmp_path):
        monitor = ResourceMonitor(workspace_root=str(tmp_path))
        fake_psutil = type("P", (), {})()
        fake_psutil.cpu_percent = lambda interval: 10.0
        fake_psutil.virtual_memory = lambda: type("M", (), {"percent": 20.0})()
        monitor._psutil = fake_psutil

        result = monitor.check()
        assert result.level == ResourceLevel.GREEN
        assert "within safe limits" in result.reason

    def test_psutil_exception_falls_back_to_disk(self, tmp_path):
        monitor = ResourceMonitor(workspace_root=str(tmp_path))

        class BadPsutil:
            def cpu_percent(self, interval):
                raise RuntimeError("fail")

            def virtual_memory(self):
                raise RuntimeError("fail")

        monitor._psutil = BadPsutil()
        result = monitor.check()
        assert result.snapshot.cpu_percent is None
        assert result.snapshot.memory_percent is None
        assert result.snapshot.disk_percent is not None


class TestResourceMonitorSerialization:
    def test_to_dict(self, tmp_path):
        monitor = ResourceMonitor(workspace_root=str(tmp_path), disable_psutil=True)
        data = monitor.to_dict()
        assert data["level"] in ("green", "warning", "critical")
        assert "reason" in data
        assert "snapshot" in data
        assert "thresholds" in data
