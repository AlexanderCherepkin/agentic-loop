"""Unit tests for figma-agent-core/preview_workflow.py.

Avoids real dev-server startup by mocking subprocess and visual_qa.
"""

from __future__ import annotations

import html
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent
PREVIEW_PATH = ROOT / "figma-agent-core" / "preview_workflow.py"


def _load_preview() -> Any:
    spec = importlib.util.spec_from_file_location("figma_preview_workflow", str(PREVIEW_PATH))
    module = importlib.util.module_from_spec(spec)
    sys.modules["figma_preview_workflow"] = module
    spec.loader.exec_module(module)
    return module


preview = _load_preview()


def test_build_qr_svg_contains_url() -> None:
    svg = preview._build_qr_svg("https://example.com")
    assert "https://example.com" in svg
    assert svg.startswith("<svg")


def test_find_next_free_port_returns_int() -> None:
    port = preview._find_next_free_port(start=45000, end=45010)
    assert isinstance(port, int)
    assert 45000 <= port < 45010


def test_extract_refinement_hints_categorizes_notes() -> None:
    hints = preview._extract_refinement_hints({"notes": ["Fix heading size", "Button color is wrong"]})
    assert any(h.startswith("layout:") for h in hints)
    assert any("color" in h for h in hints)


def test_extract_refinement_hints_string_note() -> None:
    hints = preview._extract_refinement_hints({"notes": "Make font bigger"})
    assert any("typography" in h for h in hints)


def test_read_feedback_missing_returns_empty() -> None:
    assert preview._read_feedback(Path("/nonexistent/feedback.json")) == {}


def test_build_preview_html_includes_url_and_paths() -> None:
    report = preview.PreviewReport(
        status="awaiting_feedback",
        page_url="http://127.0.0.1:3000",
        screenshot_path="shot.png",
        qr_path="qr.svg",
        feedback_file_path="feedback.json",
    )
    html = preview._build_preview_html(report, title="My Preview")
    assert "My Preview" in html
    assert "http://127.0.0.1:3000" in html
    assert "shot.png" in html
    assert "qr.svg" in html
    assert "feedback.json" in html


def test_build_preview_html_escapes_xss_payloads() -> None:
    xss_title = "<script>alert('title')</script>"
    xss_url = "http://127.0.0.1:3000/?q=\">onclick=alert('url')"
    xss_path = "img\"><script>alert('path')</script>"
    report = preview.PreviewReport(
        status="awaiting_feedback",
        page_url=xss_url,
        screenshot_path=xss_path,
        qr_path=xss_path,
        feedback_file_path=xss_path,
    )
    preview_html = preview._build_preview_html(report, title=xss_title)
    assert "<script>" not in preview_html
    assert html.escape(xss_title) in preview_html
    # The URL is escaped in both href and link text; raw JS handlers must not appear.
    assert '"onclick=' not in preview_html
    assert "'onclick=" not in preview_html
    assert html.escape(xss_url) in preview_html
    assert html.escape(xss_path) in preview_html


def test_validate_dev_command_rejects_shell_metacharacters() -> None:
    for bad in ["pnpm dev && rm -rf /", "npm; whoami", "npx `cat /etc/passwd`", 'node -e "process.exit(1)"']:
        with pytest.raises(ValueError, match="forbidden shell metacharacter"):
            preview._validate_dev_command(bad)


def test_validate_dev_command_returns_argv_for_safe_command() -> None:
    assert preview._validate_dev_command("pnpm dev") == ["pnpm", "dev"]
    assert preview._validate_dev_command("npm run dev --port 3000") == ["npm", "run", "dev", "--port", "3000"]


def test_validate_dev_command_rejects_executable_path() -> None:
    with pytest.raises(ValueError, match="must be a bare name"):
        preview._validate_dev_command("/usr/bin/pnpm dev")


def test_sanitize_output_dir_blocks_traversal(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="outside workspace"):
        preview._sanitize_output_dir("../outside", root_dir=str(tmp_path))
    with pytest.raises(ValueError, match="outside workspace"):
        preview._sanitize_output_dir("inside/../../outside", root_dir=str(tmp_path))


def test_sanitize_output_dir_resolves_absolute_inside_root(tmp_path: Path) -> None:
    out_dir = tmp_path / "preview"
    result = preview._sanitize_output_dir(str(out_dir), root_dir=str(tmp_path))
    assert result == out_dir


def test_preview_report_to_dict_serializable() -> None:
    report = preview.PreviewReport(status="approved", approved=True)
    data = report.to_dict()
    assert data["status"] == "approved"
    assert data["approved"] is True


def test_run_preview_workflow_uses_existing_url(tmp_path: Path) -> None:
    out_dir = tmp_path / "preview"
    fb_file = tmp_path / "feedback.json"
    fb_file.write_text(json.dumps({"approved": True, "notes": ["Looks good"]}), encoding="utf-8")

    fake_qa = {"status": "passed", "screenshot_path": str(out_dir / "shot.png")}
    with patch.object(preview, "_is_available", return_value=True):
        with patch.object(preview, "_load_module") as mock_load:
            mock_visual_qa = MagicMock()
            mock_visual_qa.run_visual_qa.return_value = fake_qa
            mock_load.return_value = mock_visual_qa
            result = preview.run_preview_workflow(
                site_dir=str(tmp_path / "site"),
                page_url="http://127.0.0.1:3000",
                output_dir=str(out_dir),
                root_dir=str(tmp_path),
                start_server=False,
                feedback_file=str(fb_file),
                report_output=str(out_dir / "preview_report.json"),
            )
    assert result["status"] == "approved"
    assert result["page_url"] == "http://127.0.0.1:3000"
    assert Path(result["preview_html_path"]).exists()


def test_run_preview_workflow_rejected_yields_refinement_hints(tmp_path: Path) -> None:
    out_dir = tmp_path / "preview"
    fb_file = tmp_path / "feedback.json"
    fb_file.write_text(
        json.dumps({"approved": False, "notes": ["Padding is too big"], "reject_reason": "Spacing"}),
        encoding="utf-8",
    )

    fake_qa = {"status": "passed", "screenshot_path": str(out_dir / "shot.png")}
    with patch.object(preview, "_is_available", return_value=True):
        with patch.object(preview, "_load_module") as mock_load:
            mock_visual_qa = MagicMock()
            mock_visual_qa.run_visual_qa.return_value = fake_qa
            mock_load.return_value = mock_visual_qa
            result = preview.run_preview_workflow(
                site_dir=str(tmp_path / "site"),
                page_url="http://127.0.0.1:3000",
                output_dir=str(out_dir),
                root_dir=str(tmp_path),
                start_server=False,
                feedback_file=str(fb_file),
                report_output=str(out_dir / "preview_report.json"),
            )
    assert result["status"] == "rejected"
    assert result["can_refine"] is True
    assert any("layout:" in h for h in result["refinement_hints"])


def test_run_preview_workflow_missing_url_blocked() -> None:
    with patch.object(preview, "_is_available", return_value=False):
        result = preview.run_preview_workflow(
            site_dir="/nonexistent",
            page_url="http://127.0.0.1:3000",
            start_server=False,
        )
    assert result["status"] == "blocked"


def test_run_preview_workflow_creates_feedback_template(tmp_path: Path) -> None:
    out_dir = tmp_path / "preview"
    fb_file = tmp_path / "feedback.json"

    fake_qa = {"status": "passed", "screenshot_path": str(out_dir / "shot.png")}
    with patch.object(preview, "_is_available", return_value=True):
        with patch.object(preview, "_load_module") as mock_load:
            mock_visual_qa = MagicMock()
            mock_visual_qa.run_visual_qa.return_value = fake_qa
            mock_load.return_value = mock_visual_qa
            result = preview.run_preview_workflow(
                site_dir=str(tmp_path / "site"),
                page_url="http://127.0.0.1:3000",
                output_dir=str(out_dir),
                root_dir=str(tmp_path),
                start_server=False,
                feedback_file=str(fb_file),
                report_output=str(out_dir / "preview_report.json"),
            )
    assert result["status"] == "awaiting_feedback"
    assert fb_file.exists()
    data = json.loads(fb_file.read_text(encoding="utf-8"))
    assert data["approved"] is None
    assert "expires_at" in data


def test_run_preview_workflow_auto_approve_after_timeout(tmp_path: Path) -> None:
    out_dir = tmp_path / "preview"
    fb_file = tmp_path / "feedback.json"
    fb_file.write_text(json.dumps({"approved": None, "notes": []}), encoding="utf-8")

    fake_qa = {"status": "passed", "screenshot_path": str(out_dir / "shot.png")}
    with patch.object(preview, "_is_available", return_value=True):
        with patch.object(preview, "_load_module") as mock_load:
            mock_visual_qa = MagicMock()
            mock_visual_qa.run_visual_qa.return_value = fake_qa
            mock_load.return_value = mock_visual_qa
            result = preview.run_preview_workflow(
                site_dir=str(tmp_path / "site"),
                page_url="http://127.0.0.1:3000",
                output_dir=str(out_dir),
                root_dir=str(tmp_path),
                start_server=False,
                feedback_file=str(fb_file),
                report_output=str(out_dir / "preview_report.json"),
                auto_approve_after_timeout=True,
            )
    assert result["status"] == "approved"
    assert result["approved"] is True
