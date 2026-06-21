import json
import re
import time
import argparse
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


try:
    from playwright.sync_api import sync_playwright

    PLAYWRIGHT_AVAILABLE = True
except Exception:
    sync_playwright = None  # type: ignore
    PLAYWRIGHT_AVAILABLE = False


try:
    from PIL import Image

    PIL_AVAILABLE = True
except Exception:
    Image = None  # type: ignore
    PIL_AVAILABLE = False


DEFAULT_VIEWPORT = {"width": 1280, "height": 720}
DEFAULT_OUTPUT_DIR = ".tmp/browser/visual_qa"


def _sanitize_output_dir(output_dir: str, root_dir: Optional[str] = None) -> Path:
    target = Path(output_dir).resolve()
    root = Path(root_dir).resolve() if root_dir else Path.cwd().resolve()
    if not str(target).startswith(str(root)):
        raise ValueError(f"Output directory outside workspace: {output_dir}")
    target.mkdir(parents=True, exist_ok=True)
    return target


def _is_allowed_url(url: str, allowed_domains: Optional[List[str]] = None) -> bool:
    if url.startswith("http://localhost:") or url.startswith("http://127.0.0.1:"):
        return True
    if url.startswith("file://"):
        path = Path(url.replace("file://", "").replace("/", "\\") if "win" in __import__("sys").platform else url.replace("file://", ""))
        return str(path.resolve()).startswith(str(Path.cwd().resolve()))
    if allowed_domains:
        for domain in allowed_domains:
            host = __import__("urllib.parse").urlparse(url).hostname or ""
            if domain == host or domain in url:
                return True
    return False


@dataclass
class DomAssertion:
    selector: str
    expected_count: Optional[int] = None
    expected_text: Optional[str] = None
    exact_text: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "selector": self.selector,
            "expected_count": self.expected_count,
            "expected_text": self.expected_text,
            "exact_text": self.exact_text,
        }


@dataclass
class VisualQaReport:
    status: str
    screenshot_path: Optional[str] = None
    reference_screenshot_path: Optional[str] = None
    diff_score: Optional[float] = None
    dom_assertions: List[Dict[str, Any]] = field(default_factory=list)
    discrepancies: List[str] = field(default_factory=list)
    metrics: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status,
            "screenshot_path": self.screenshot_path,
            "reference_screenshot_path": self.reference_screenshot_path,
            "diff_score": self.diff_score,
            "dom_assertions": self.dom_assertions,
            "discrepancies": self.discrepancies,
            "metrics": self.metrics,
        }


class VisualQAEngine:
    def __init__(
        self,
        viewport: Optional[Dict[str, int]] = None,
        allowed_domains: Optional[List[str]] = None,
        output_dir: str = DEFAULT_OUTPUT_DIR,
        root_dir: Optional[str] = None,
    ):
        self.viewport = viewport or DEFAULT_VIEWPORT.copy()
        self.allowed_domains = allowed_domains or []
        self.output_dir = _sanitize_output_dir(output_dir, root_dir=root_dir)
        self.report = VisualQaReport(status="blocked")

    def run(
        self,
        page_url: str,
        reference_path: Optional[str] = None,
        expected_nodes: Optional[List[Dict[str, Any]]] = None,
    ) -> VisualQaReport:
        if not PLAYWRIGHT_AVAILABLE:
            return self._blocked("Playwright is not installed. Install with: pip install playwright && playwright install")

        if not _is_allowed_url(page_url, self.allowed_domains):
            return self._blocked(f"URL not allowed by network guard: {page_url}")

        screenshot_path = self.output_dir / f"page_{int(time.time())}.png"
        reference_screenshot_path = None
        if reference_path:
            reference_screenshot_path = str(Path(reference_path).resolve())

        start_time = time.time()
        metrics: Dict[str, Any] = {
            "viewport_width": self.viewport["width"],
            "viewport_height": self.viewport["height"],
        }

        discrepancies: List[str] = []
        dom_assertions: List[Dict[str, Any]] = []
        diff_score: Optional[float] = None

        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-dev-shm-usage"])
                context = browser.new_context(viewport=self.viewport)
                page = context.new_page()

                try:
                    page.goto(page_url, wait_until="networkidle", timeout=30000)
                except Exception as e:
                    discrepancies.append(f"Navigation warning: {e}")

                page.screenshot(path=str(screenshot_path), full_page=True)

                screenshot_size = Image.open(screenshot_path).size if PIL_AVAILABLE else (0, 0)
                metrics["screenshot_width"] = screenshot_size[0]
                metrics["screenshot_height"] = screenshot_size[1]
                metrics["load_time_ms"] = int(round((time.time() - start_time) * 1000))

                dom_assertions = self._run_dom_assertions(page, expected_nodes or [])

                if reference_screenshot_path and Path(reference_screenshot_path).exists():
                    diff_score = self._compute_diff(str(screenshot_path), reference_screenshot_path, discrepancies)

                browser.close()
        except Exception as e:
            return self._blocked(f"Browser session failed: {e}")

        failed_assertions = [a for a in dom_assertions if not a.get("passed", False)]
        status = "passed"
        if failed_assertions or discrepancies:
            status = "failed"

        self.report = VisualQaReport(
            status=status,
            screenshot_path=str(screenshot_path.resolve()),
            reference_screenshot_path=reference_screenshot_path,
            diff_score=diff_score,
            dom_assertions=dom_assertions,
            discrepancies=discrepancies,
            metrics=metrics,
        )
        self._write_report()
        return self.report

    def _blocked(self, reason: str) -> VisualQaReport:
        self.report = VisualQaReport(status="blocked", discrepancies=[reason])
        self._write_report()
        return self.report

    def _run_dom_assertions(self, page: Any, expected_nodes: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        results: List[Dict[str, Any]] = []
        for entry in expected_nodes:
            selector = entry.get("selector", "")
            if not selector:
                continue

            expected_count = entry.get("expected_count")
            expected_text = entry.get("expected_text")
            exact_text = entry.get("exact_text")

            passed = True
            actual: Dict[str, Any] = {}
            discrepancies: List[str] = []

            try:
                elements = page.query_selector_all(selector)
                actual["count"] = len(elements)

                if expected_count is not None and len(elements) != expected_count:
                    passed = False
                    discrepancies.append(f"expected {expected_count} elements, found {len(elements)}")

                if expected_text or exact_text:
                    texts = [el.inner_text().strip() for el in elements if el.inner_text()]
                    actual["texts"] = texts
                    target = exact_text or expected_text
                    if target and target not in texts:
                        passed = False
                        if exact_text:
                            discrepancies.append(f"no element has exact text '{exact_text}'")
                        else:
                            discrepancies.append(f"no element contains text '{expected_text}'")
            except Exception as e:
                passed = False
                actual["error"] = str(e)
                discrepancies.append(f"selector query failed: {e}")

            results.append({
                "selector": selector,
                "expected": entry,
                "actual": actual,
                "passed": passed,
                "discrepancies": discrepancies,
            })
        return results

    def _compute_diff(
        self,
        screenshot_path: str,
        reference_path: str,
        discrepancies: List[str],
    ) -> Optional[float]:
        if not PIL_AVAILABLE:
            discrepancies.append("PIL not installed; skipping image diff.")
            return None

        try:
            img = Image.open(screenshot_path).convert("RGB")
            ref = Image.open(reference_path).convert("RGB")

            if img.size != ref.size:
                discrepancies.append(
                    f"Screenshot size {img.size} differs from reference {ref.size}; normalizing before diff."
                )
                ref = ref.resize(img.size, Image.Resampling.LANCZOS)

            diff = 0.0
            pixels = img.size[0] * img.size[1]
            if pixels == 0:
                return 0.0

            img_data = list(img.getdata())
            ref_data = list(ref.getdata())
            for (r1, g1, b1), (r2, g2, b2) in zip(img_data, ref_data):
                diff += abs(r1 - r2) + abs(g1 - g2) + abs(b1 - b2)

            max_diff = pixels * 3 * 255
            return round(diff / max_diff, 4)
        except Exception as e:
            discrepancies.append(f"Image diff failed: {e}")
            return None

    def _write_report(self) -> None:
        report_path = self.output_dir / "report.json"
        with open(report_path, "w", encoding="utf-8") as f:
            json.dump(self.report.to_dict(), f, ensure_ascii=False, indent=2)


def _expected_nodes_from_ast(ast: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Извлекает минимальные DOM-assertions из Tailwind AST."""
    nodes: List[Dict[str, Any]] = []

    def walk(node: Dict[str, Any]) -> None:
        tag = node.get("tag")
        text = node.get("text")
        if tag == "img" and node.get("src"):
            nodes.append({"selector": f'img[src="{node["src"]}"]', "expected_count": 1})
        if text and tag in ("h1", "h2", "h3"):
            nodes.append({"selector": tag, "expected_text": text})
        for child in node.get("children", []):
            walk(child)

    root = ast.get("root", ast)
    walk(root)
    return nodes


def run_visual_qa(
    page_url: str,
    ast_path: Optional[str] = None,
    reference_path: Optional[str] = None,
    expected_nodes: Optional[List[Dict[str, Any]]] = None,
    viewport: Optional[Dict[str, int]] = None,
    output_dir: str = DEFAULT_OUTPUT_DIR,
    allowed_domains: Optional[List[str]] = None,
    root_dir: Optional[str] = None,
) -> Dict[str, Any]:
    merged_expected = list(expected_nodes or [])
    if ast_path:
        path = Path(ast_path)
        if path.exists():
            with open(path, "r", encoding="utf-8") as f:
                ast = json.load(f)
            merged_expected.extend(_expected_nodes_from_ast(ast))

    engine = VisualQAEngine(
        viewport=viewport,
        allowed_domains=allowed_domains,
        output_dir=output_dir,
        root_dir=root_dir,
    )
    report = engine.run(page_url, reference_path=reference_path, expected_nodes=merged_expected)
    return report.to_dict()


def main():
    parser = argparse.ArgumentParser(description="Visual QA: screenshot + DOM assertions for generated landing page")
    parser.add_argument("--url", required=True, help="URL of the generated landing page")
    parser.add_argument("--ast", default=None, help="Path to Tailwind AST (layout_ast.json) for auto assertions")
    parser.add_argument("--reference", default=None, help="Path to Figma reference screenshot")
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR, help="Directory for screenshots and report")
    parser.add_argument(
        "--viewport",
        default=None,
        help="Viewport as WIDTHxHEIGHT, e.g. 1280x720",
    )
    parser.add_argument(
        "--expected",
        default=None,
        help='JSON string with DOM assertions, e.g. [{"selector":"h1","expected_text":"Hero"}]',
    )
    parser.add_argument(
        "--allowed-domains",
        default=None,
        help="Comma-separated list of allowed external domains for URL guard.",
    )
    args = parser.parse_args()

    viewport = None
    if args.viewport:
        match = re.match(r"(\d+)x(\d+)", args.viewport)
        if match:
            viewport = {"width": int(match.group(1)), "height": int(match.group(2))}

    expected_nodes = None
    if args.expected:
        expected_nodes = json.loads(args.expected)

    allowed_domains = None
    if args.allowed_domains:
        allowed_domains = [d.strip() for d in args.allowed_domains.split(",") if d.strip()]

    result = run_visual_qa(
        page_url=args.url,
        ast_path=args.ast,
        reference_path=args.reference,
        expected_nodes=expected_nodes,
        viewport=viewport,
        output_dir=args.output_dir,
        allowed_domains=allowed_domains,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
