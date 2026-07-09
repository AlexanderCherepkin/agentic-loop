from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class PreviewConfig:
    target_dir: Path | str = "."
    site_dir: str = "."
    page_url: str | None = None
    port: int = 3000
    output_dir: str = ".tmp/browser/preview"
    dev_command: str = "pnpm dev"
    server_timeout: float = 60.0
    feedback_file: str | None = None
    report_output: str = "preview_report.json"
    viewport: str = "1280x720"
    title: str | None = None
    allowed_domains: list[str] | None = None
    auto_approve_after_timeout: bool = False

    def __post_init__(self) -> None:
        self.target_dir = Path(self.target_dir)

    def validate(self) -> list[str]:
        errors: list[str] = []
        if not self.target_dir.exists():
            errors.append(f"target_dir does not exist: {self.target_dir}")
        if not self.site_dir:
            errors.append("site_dir is required")
        if not self.dev_command:
            errors.append("dev_command is required")
        return errors

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "PreviewConfig":
        return cls(
            target_dir=data.get("target_dir", "."),
            site_dir=data.get("site_dir", "."),
            page_url=data.get("page_url"),
            port=int(data.get("port", 3000)),
            output_dir=data.get("output_dir", ".tmp/browser/preview"),
            dev_command=data.get("dev_command", "pnpm dev"),
            server_timeout=float(data.get("server_timeout", 60.0)),
            feedback_file=data.get("feedback_file"),
            report_output=data.get("report_output", "preview_report.json"),
            viewport=data.get("viewport", "1280x720"),
            title=data.get("title"),
            allowed_domains=list(data.get("allowed_domains") or []),
            auto_approve_after_timeout=bool(data.get("auto_approve_after_timeout", False)),
        )
