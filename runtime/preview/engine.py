from __future__ import annotations

import importlib.util
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .config import PreviewConfig


@dataclass
class PreviewResult:
    status: str = "unknown"
    page_url: str | None = None
    screenshot_path: str | None = None
    preview_html_path: str | None = None
    feedback_file_path: str | None = None
    approved: bool | None = None
    can_refine: bool = False
    refinement_hints: list[str] = field(default_factory=list)
    report: dict[str, Any] = field(default_factory=dict)
    errors: list[dict[str, Any]] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


class PreviewEngine:
    def __init__(self, target_dir: Path | str, config: PreviewConfig | None = None):
        self.target_dir = Path(target_dir).resolve()
        self.config = config or PreviewConfig()
        self.config.target_dir = self.target_dir
        self.result = PreviewResult()

    def run(self) -> PreviewResult:
        validation_errors = self.config.validate()
        if validation_errors:
            for err in validation_errors:
                self.result.errors.append({"file": "", "reason": err})
            return self.result

        preview_module = self._load_preview_module()
        if preview_module is None:
            self.result.errors.append({"file": "figma-agent-core/preview_workflow.py", "reason": "could not load preview workflow module"})
            return self.result

        site_dir = str(self.target_dir / self.config.site_dir)
        report_output = str(self.target_dir / self.config.report_output)
        output_dir = str(self.target_dir / self.config.output_dir)
        feedback_file = None
        if self.config.feedback_file:
            feedback_file = str(self.target_dir / self.config.feedback_file)

        try:
            report = preview_module.run_preview_workflow(
                site_dir=site_dir,
                page_url=self.config.page_url,
                port=self.config.port,
                output_dir=output_dir,
                root_dir=str(self.target_dir),
                start_server=self.config.page_url is None,
                dev_command=self.config.dev_command,
                server_timeout=self.config.server_timeout,
                feedback_file=feedback_file,
                report_output=report_output,
                viewport=self.config.viewport,
                title=self.config.title or "Preview",
                allowed_domains=self.config.allowed_domains,
                auto_approve_after_timeout=self.config.auto_approve_after_timeout,
            )
            self.result.report = dict(report)
            self.result.status = report.get("status", "unknown")
            self.result.page_url = report.get("page_url")
            self.result.screenshot_path = report.get("screenshot_path")
            self.result.preview_html_path = report.get("preview_html_path")
            self.result.feedback_file_path = report.get("feedback_file_path")
            self.result.approved = report.get("approved")
            self.result.can_refine = report.get("can_refine", False)
            self.result.refinement_hints = report.get("refinement_hints", [])
        except Exception as exc:
            self.result.errors.append({"file": "", "reason": f"preview workflow failed: {exc}"})

        return self.result

    def _load_preview_module(self) -> Any:
        preview_path = self.target_dir / "figma-agent-core" / "preview_workflow.py"
        if not preview_path.exists():
            # Try repo-relative fallback.
            preview_path = Path(__file__).resolve().parent.parent.parent / "figma-agent-core" / "preview_workflow.py"
        if not preview_path.exists():
            return None
        module_name = "figma_preview_workflow_runtime"
        spec = importlib.util.spec_from_file_location(module_name, str(preview_path))
        if not spec or not spec.loader:
            return None
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)
        return module
