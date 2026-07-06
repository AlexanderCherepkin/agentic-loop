"""Client preview & approval workflow for Figma-generated Next.js sites.

Starts a local dev server (or uses an existing URL), captures a screenshot,
builds a preview report with QR code and optional preview link, collects
client feedback, and feeds the feedback into the refinement loop.
"""

import argparse
import json
import os
import re
import subprocess
import sys
import time
import urllib.parse
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional


DEFAULT_PORT = 3000
DEFAULT_OUTPUT_DIR = ".tmp/browser/preview"
DEFAULT_FEEDBACK_TIMEOUT = 86400  # 24 hours in seconds


def _sanitize_output_dir(output_dir: str, root_dir: Optional[str] = None) -> Path:
    target = Path(output_dir).resolve()
    root = Path(root_dir).resolve() if root_dir else Path.cwd().resolve()
    if not str(target).startswith(str(root)):
        raise ValueError(f"Output directory outside workspace: {output_dir}")
    target.mkdir(parents=True, exist_ok=True)
    return target


def _is_available(url: str, timeout: float = 5.0) -> bool:
    try:
        import urllib.request

        req = urllib.request.Request(
            url,
            method="HEAD",
            headers={"User-Agent": "AgenticLoop-Preview/1.0"},
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status < 500
    except Exception:
        return False


def _find_next_free_port(start: int = 3000, end: int = 3100) -> int:
    import socket

    for port in range(start, end):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(("127.0.0.1", port))
                return port
            except OSError:
                continue
    return start


def _build_qr_svg(url: str, size: int = 256) -> str:
    """Build a simple SVG QR placeholder containing the URL as text.

    Real QR generation can be swapped in via qrcode library; this avoids
    adding a hard dependency.
    """
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{size}" height="{size}" viewBox="0 0 {size} {size}">
  <rect width="100%" height="100%" fill="white"/>
  <text x="50%" y="50%" dominant-baseline="middle" text-anchor="middle" font-size="12" fill="black">{url}</text>
</svg>"""


@dataclass
class PreviewReport:
    status: str
    page_url: Optional[str] = None
    screenshot_path: Optional[str] = None
    qr_path: Optional[str] = None
    preview_html_path: Optional[str] = None
    feedback_file_path: Optional[str] = None
    client_notes: List[str] = field(default_factory=list)
    approved: Optional[bool] = None
    rejection_reason: Optional[str] = None
    can_refine: bool = False
    refinement_hints: List[str] = field(default_factory=list)
    server_pid: Optional[int] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status,
            "page_url": self.page_url,
            "screenshot_path": self.screenshot_path,
            "qr_path": self.qr_path,
            "preview_html_path": self.preview_html_path,
            "feedback_file_path": self.feedback_file_path,
            "client_notes": self.client_notes,
            "approved": self.approved,
            "rejection_reason": self.rejection_reason,
            "can_refine": self.can_refine,
            "refinement_hints": self.refinement_hints,
            "server_pid": self.server_pid,
        }


def _save_json(path: Path, data: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _build_preview_html(report: PreviewReport, title: str = "Preview") -> str:
    screenshot = report.screenshot_path or ""
    qr = report.qr_path or ""
    url = report.page_url or ""
    feedback = report.feedback_file_path or ""
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{title} — Preview</title>
  <style>
    body {{ font-family: system-ui, -apple-system, sans-serif; margin: 0; padding: 2rem; background: #f6f6f6; }}
    .container {{ max-width: 960px; margin: 0 auto; background: #fff; padding: 2rem; border-radius: 12px; box-shadow: 0 2px 8px rgba(0,0,0,0.06); }}
    h1 {{ margin-top: 0; }}
    .meta {{ color: #666; margin-bottom: 1rem; }}
    img {{ max-width: 100%; border: 1px solid #ddd; border-radius: 6px; }}
    .qr {{ width: 256px; height: 256px; margin: 1rem 0; }}
    .feedback {{ margin-top: 1.5rem; padding: 1rem; background: #fafafa; border-radius: 6px; }}
    code {{ background: #eee; padding: 0.15rem 0.3rem; border-radius: 4px; }}
  </style>
</head>
<body>
  <div class="container">
    <h1>{title}</h1>
    <p class="meta">Live URL: <a href="{url}">{url}</a></p>
    {f'<img class="qr" src="{qr}" alt="QR code"/>' if qr else ""}
    {f'<img src="{screenshot}" alt="Preview screenshot"/>' if screenshot else ""}
    <div class="feedback">
      <h2>Client feedback</h2>
      <p>Write your notes to <code>{feedback}</code> and set <code>approved</code> to true/false.</p>
      <pre id="template">{{
  "approved": false,
  "notes": ["Fix heading size", "Move CTA up"],
  "reject_reason": ""
}}</pre>
    </div>
  </div>
</body>
</html>"""


def _extract_refinement_hints(feedback: Dict[str, Any]) -> List[str]:
    hints: List[str] = []
    notes = feedback.get("notes") or []
    if isinstance(notes, str):
        notes = [notes]
    for note in notes:
        text = str(note).lower()
        if any(word in text for word in ("size", "padding", "spacing", "margin", "gap", "alignment", "position")):
            hints.append(f"layout: {note}")
        if any(word in text for word in ("color", "font", "text", "typography", "bold", "italic")):
            hints.append(f"typography: {note}")
        if any(word in text for word in ("image", "photo", "picture", "logo", "icon")):
            hints.append(f"asset: {note}")
        if any(word in text for word in ("button", "link", "hover", "click", "form", "input")):
            hints.append(f"interactive: {note}")
        if any(word in text for word in ("mobile", "phone", "responsive", "breakpoint", "tablet")):
            hints.append(f"responsive: {note}")
        if not hints or note not in [h.split(": ", 1)[1] for h in hints if ": " in h]:
            hints.append(f"general: {note}")
    return hints


def _read_feedback(feedback_file: Path) -> Dict[str, Any]:
    if not feedback_file.exists():
        return {}
    try:
        with open(feedback_file, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def start_dev_server(
    site_dir: str,
    port: int = DEFAULT_PORT,
    command: str = "pnpm dev",
    timeout: float = 60.0,
) -> subprocess.Popen:
    """Start the Next.js dev server and wait until it responds."""
    cwd = Path(site_dir).resolve()
    if not cwd.exists():
        raise ValueError(f"Site directory does not exist: {site_dir}")
    env = os.environ.copy()
    env["PORT"] = str(port)
    shell = sys.platform == "win32"
    process = subprocess.Popen(
        command,
        cwd=str(cwd),
        env=env,
        shell=shell,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    url = f"http://127.0.0.1:{port}"
    deadline = time.time() + timeout
    while time.time() < deadline:
        if process.poll() is not None:
            stdout, stderr = process.communicate()
            raise RuntimeError(
                f"Dev server exited early (code {process.returncode}).\nSTDOUT:\n{stdout}\nSTDERR:\n{stderr}"
            )
        if _is_available(url, timeout=1.0):
            return process
        time.sleep(0.5)
    process.terminate()
    try:
        process.wait(timeout=5)
    except Exception:
        process.kill()
    raise RuntimeError(f"Dev server did not become ready within {timeout}s")


def run_preview_workflow(
    site_dir: str,
    page_url: Optional[str] = None,
    port: int = DEFAULT_PORT,
    output_dir: str = DEFAULT_OUTPUT_DIR,
    root_dir: Optional[str] = None,
    start_server: bool = True,
    dev_command: str = "pnpm dev",
    server_timeout: float = 60.0,
    feedback_timeout: float = DEFAULT_FEEDBACK_TIMEOUT,
    title: str = "Preview",
    viewport: str = "1280x720",
    expected_nodes: Optional[List[Dict[str, Any]]] = None,
    allowed_domains: Optional[List[str]] = None,
    report_output: str = "preview_report.json",
    feedback_file: Optional[str] = None,
    auto_approve_after_timeout: bool = False,
) -> Dict[str, Any]:
    """Run the full preview workflow and return a report.

    In automated/CI mode, reads existing feedback_file. In interactive mode,
    writes the file and waits until approved/rejected or timeout.
    """
    out_dir = _sanitize_output_dir(output_dir, root_dir=root_dir)
    server_process: Optional[subprocess.Popen] = None
    server_pid: Optional[int] = None

    try:
        if page_url:
            target_url = page_url
            if not start_server and not _is_available(target_url, timeout=5.0):
                return PreviewReport(
                    status="blocked",
                    page_url=target_url,
                    can_refine=False,
                ).to_dict()
        else:
            if start_server:
                free_port = _find_next_free_port(port, port + 100)
                server_process = start_dev_server(
                    site_dir=site_dir,
                    port=free_port,
                    command=dev_command,
                    timeout=server_timeout,
                )
                server_pid = server_process.pid
                target_url = f"http://127.0.0.1:{free_port}"
            else:
                return PreviewReport(
                    status="blocked",
                    can_refine=False,
                ).to_dict()

        # Run Visual QA against the live page to capture screenshot + metrics.
        parsed_viewport = None
        if isinstance(viewport, str):
            match = re.match(r"(\d+)x(\d+)", viewport)
            if match:
                parsed_viewport = {"width": int(match.group(1)), "height": int(match.group(2))}
        elif isinstance(viewport, dict):
            parsed_viewport = viewport
        visual_qa_module = _load_module("visual_qa.py", "figma_visual_qa")
        qa_report = visual_qa_module.run_visual_qa(
            page_url=target_url,
            ast_path="layout_ast.json",
            reference_path=None,
            output_dir=str(out_dir / "visual_qa"),
            viewport=parsed_viewport,
            allowed_domains=allowed_domains,
            root_dir=root_dir or str(Path.cwd()),
        )
        screenshot_path = qa_report.get("screenshot_path")

        # Build QR code placeholder and preview HTML.
        qr_path = str(out_dir / "preview_qr.svg")
        Path(qr_path).write_text(_build_qr_svg(target_url), encoding="utf-8")

        fb_path = Path(feedback_file) if feedback_file else out_dir / "client_feedback.json"
        feedback: Dict[str, Any] = _read_feedback(fb_path)

        html_path = str(out_dir / "preview.html")
        report_obj = PreviewReport(
            status="awaiting_feedback",
            page_url=target_url,
            screenshot_path=screenshot_path,
            qr_path=qr_path,
            preview_html_path=html_path,
            feedback_file_path=str(fb_path),
            server_pid=server_pid,
        )
        Path(html_path).write_text(_build_preview_html(report_obj, title=title), encoding="utf-8")

        if not feedback:
            _save_json(
                fb_path,
                {
                    "approved": None,
                    "notes": [],
                    "reject_reason": "",
                    "url": target_url,
                    "expires_at": time.time() + feedback_timeout,
                },
            )

        if feedback.get("approved") is True:
            report_obj.status = "approved"
            report_obj.approved = True
        elif feedback.get("approved") is False:
            report_obj.status = "rejected"
            report_obj.approved = False
            report_obj.rejection_reason = feedback.get("reject_reason") or "Client rejected preview"
            report_obj.refinement_hints = _extract_refinement_hints(feedback)
            report_obj.can_refine = bool(report_obj.refinement_hints)
        elif feedback.get("approved") is None and not auto_approve_after_timeout:
            report_obj.status = "awaiting_feedback"
        elif auto_approve_after_timeout:
            report_obj.status = "approved"
            report_obj.approved = True

        report_obj.client_notes = feedback.get("notes") or []
        report_dict = report_obj.to_dict()
        report_dict["visual_qa"] = qa_report
        _save_json(Path(report_output), report_dict)
        return report_dict

    finally:
        # Keep server alive in interactive mode so client can review live page.
        pass


def _load_module(file_name: str, module_name: str) -> Any:
    from importlib import util as importlib_util

    module_dir = Path(__file__).resolve().parent
    file_path = module_dir / file_name
    spec = importlib_util.spec_from_file_location(module_name, str(file_path))
    if not spec or not spec.loader:
        raise ImportError(f"Cannot load module {file_name}")
    if module_name in sys.modules:
        existing = sys.modules[module_name]
        spec.loader.exec_module(existing)
        return existing
    module = importlib_util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Client preview & approval workflow for generated Next.js sites."
    )
    parser.add_argument("--site-dir", default="generated-site", help="Directory with the generated Next.js site.")
    parser.add_argument("--page-url", default=None, help="Use existing URL instead of starting dev server.")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help="Port for dev server.")
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR, help="Output directory for preview artifacts.")
    parser.add_argument("--dev-command", default="pnpm dev", help="Command to start the dev server.")
    parser.add_argument("--server-timeout", type=float, default=60.0, help="Seconds to wait for dev server readiness.")
    parser.add_argument("--no-start-server", action="store_true", help="Do not start a dev server; require --page-url.")
    parser.add_argument("--feedback-file", default=None, help="Path to client feedback JSON.")
    parser.add_argument("--report-output", default="preview_report.json", help="Path to preview report JSON.")
    parser.add_argument("--viewport", default="1280x720", help="Viewport for screenshot, e.g. 1280x720.")
    parser.add_argument("--allowed-domains", default=None, help="Comma-separated allowed external domains.")
    parser.add_argument("--title", default="Preview", help="Preview page title.")
    args = parser.parse_args()

    allowed_domains = None
    if args.allowed_domains:
        allowed_domains = [d.strip() for d in args.allowed_domains.split(",") if d.strip()]

    result = run_preview_workflow(
        site_dir=args.site_dir,
        page_url=args.page_url,
        port=args.port,
        output_dir=args.output_dir,
        start_server=not args.no_start_server,
        dev_command=args.dev_command,
        server_timeout=args.server_timeout,
        feedback_file=args.feedback_file,
        report_output=args.report_output,
        viewport=args.viewport,
        allowed_domains=allowed_domains,
        title=args.title,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
