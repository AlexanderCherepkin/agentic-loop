"""Smoke tests for figma-agent-core/conductor.py."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "figma-agent-core"))

import conductor as conductor_module


class FakeCompletedProcess:
    def __init__(self, returncode: int = 0, stdout: str = "", stderr: str = ""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


class TestRedactCommand:
    def test_redacts_secret_flag_value(self):
        cmd = ["script.py", "--provider-api-key", "secret123", "--file", "x.json"]
        redacted = conductor_module._redact_command(cmd)
        assert "secret123" not in redacted
        assert "<REDACTED>" in redacted
        assert redacted.index("<REDACTED>") == redacted.index("--provider-api-key") + 1

    def test_no_secret_flags_unchanged(self):
        cmd = ["script.py", "--file", "x.json"]
        assert conductor_module._redact_command(cmd) == cmd


class TestRunCommand:
    def test_run_command_resolves_script_path(self, tmp_path, monkeypatch):
        script = tmp_path / "helper.py"
        script.write_text("print('ok')", encoding="utf-8")
        conductor_file = Path(conductor_module.__file__)

        # Place a script next to conductor.py so path resolution triggers.
        target = conductor_file.parent / "helper.py"
        target.write_text("print('ok')", encoding="utf-8")
        try:

            def fake_run(cmd, **kwargs):
                assert Path(cmd[1]).exists()
                return FakeCompletedProcess(0, "ok\n", "")

            monkeypatch.setattr(subprocess, "run", fake_run)
            result = conductor_module._run_command([sys.executable, "helper.py"])
            assert result.returncode == 0
        finally:
            target.unlink(missing_ok=True)

    def test_run_command_logs_failure(self, monkeypatch):
        def fake_run(cmd, **kwargs):
            return FakeCompletedProcess(1, "", "boom")

        monkeypatch.setattr(subprocess, "run", fake_run)
        result = conductor_module._run_command([sys.executable, "script.py"])
        assert result.returncode == 1

    def test_run_command_timeout_raises(self, monkeypatch):
        def fake_run(cmd, **kwargs):
            raise subprocess.TimeoutExpired(cmd, timeout=1)

        monkeypatch.setattr(subprocess, "run", fake_run)
        with pytest.raises(subprocess.TimeoutExpired):
            conductor_module._run_command([sys.executable, "script.py"])


class TestStageDryRun:
    def test_stage_bootstrap_dry_run(self, caplog):
        with caplog.at_level("INFO"):
            result = conductor_module.stage_bootstrap(dry_run=True)
        assert result is True
        assert "DRY-RUN" in caplog.text

    def test_stage_analyze_dry_run(self, caplog):
        with caplog.at_level("INFO"):
            result = conductor_module.stage_analyze(dry_run=True)
        assert result is True
        assert "DRY-RUN" in caplog.text

    def test_stage_spec_dry_run(self, caplog):
        with caplog.at_level("INFO"):
            result = conductor_module.stage_spec(dry_run=True)
        assert result is True

    def test_stage_layout_dry_run(self, caplog):
        with caplog.at_level("INFO"):
            result = conductor_module.stage_layout(dry_run=True)
        assert result is True

    def test_stage_download_reference_skips_without_node_id(self, caplog):
        result = conductor_module.stage_download_figma_reference()
        assert result is False

    def test_stage_download_reference_dry_run(self, caplog):
        result = conductor_module.stage_download_figma_reference(
            node_id="1:1", file_key="ABC", dry_run=True
        )
        assert result is True

    def test_stage_image_enrichment_falls_back_to_pollinations(self, caplog, monkeypatch):
        monkeypatch.delenv("UNSPLASH_ACCESS_KEY", raising=False)
        result = conductor_module.stage_image_enrichment(dry_run=True)
        assert result is True

    def test_stage_backend_bridge_skips_without_specs(self, caplog):
        result = conductor_module.stage_backend_bridge(dry_run=True)
        assert result is True


class TestCollectTopLevelSections:
    def test_collects_sections(self, tmp_path, monkeypatch):
        data = {
            "children": [
                {"id": "1:1", "name": "Hero"},
                {"id": "2:2", "name": "Features"},
            ]
        }
        path = tmp_path / "figma_node.json"
        path.write_text("{\"children\": [{\"id\": \"1:1\", \"name\": \"Hero\"}, {\"id\": \"2:2\", \"name\": \"Features\"}]}", encoding="utf-8")
        monkeypatch.chdir(tmp_path)

        def fake_load(file):
            return data

        def fake_list(data):
            return data["children"]

        monkeypatch.setattr(conductor_module.analyzer, "load_figma_json", fake_load)
        monkeypatch.setattr(conductor_module.analyzer, "list_top_level_nodes", fake_list)
        sections = conductor_module._collect_top_level_sections()
        assert len(sections) == 2
        assert sections[0]["name"] == "Hero"


class TestRunPipeline:
    def test_pipeline_dry_run_all_stages(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        # Stage functions are tested in dry-run mode so they always succeed.
        report = conductor_module.run_pipeline({"dry_run": True, "only": ["bootstrap", "spec", "analyze"]})
        assert report["stages"]["bootstrap"]["success"] is True
        assert report["stages"]["spec"]["success"] is True
        assert report["stages"]["analyze"]["success"] is True
        assert "duration_seconds" in report

    def test_pipeline_halts_on_bootstrap_failure(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)

        def failing_bootstrap(**kwargs):
            return False

        monkeypatch.setattr(conductor_module, "stage_bootstrap", failing_bootstrap)
        report = conductor_module.run_pipeline({"dry_run": False, "only": ["bootstrap", "analyze"]})
        assert report["stages"]["bootstrap"]["success"] is False
        assert "analyze" not in report["stages"]

    def test_pipeline_only_string(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        report = conductor_module.run_pipeline({"dry_run": True, "only": "spec"})
        assert list(report["stages"].keys()) == ["spec"]


class TestSaveReport:
    def test_save_report_writes_json(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        report = {"ok": True}
        conductor_module.save_report(report, "test_report.json")
        assert (tmp_path / "test_report.json").exists()
