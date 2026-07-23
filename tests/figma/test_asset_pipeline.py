import importlib.util
import json
import shutil
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent
ASSET_PIPELINE_PATH = ROOT / "figma-agent-core" / "asset_pipeline.py"
ASSET_DOWNLOADER_PATH = ROOT / "figma-agent-core" / "asset_downloader.py"


def _load_asset_pipeline():
    spec = importlib.util.spec_from_file_location("figma_asset_pipeline", str(ASSET_PIPELINE_PATH))
    module = importlib.util.module_from_spec(spec)
    sys.modules["figma_asset_pipeline"] = module
    spec.loader.exec_module(module)
    return module


def _load_asset_downloader():
    spec = importlib.util.spec_from_file_location("figma_asset_downloader", str(ASSET_DOWNLOADER_PATH))
    module = importlib.util.module_from_spec(spec)
    sys.modules["figma_asset_downloader"] = module
    spec.loader.exec_module(module)
    return module


asset_pipeline = _load_asset_pipeline()
asset_downloader = _load_asset_downloader()


FIXTURES = Path(__file__).parent / "fixtures"


def _load_fixture(name: str):
    with open(FIXTURES / name, "r", encoding="utf-8") as f:
        return json.load(f)


def test_asset_extractor_finds_all_assets():
    data = _load_fixture("assets_simple.json")
    extractor = asset_pipeline.AssetExtractor()
    assets = extractor.extract(data)
    ids = {a["id"] for a in assets}
    assert "2:1" in ids  # IMAGE
    assert "2:2" in ids  # VECTOR -> svg
    assert "2:3" in ids  # RECTANGLE with IMAGE fill


def test_asset_extractor_formats():
    data = _load_fixture("assets_simple.json")
    assets = asset_pipeline.AssetExtractor().extract(data)
    by_id = {a["id"]: a for a in assets}
    assert by_id["2:1"]["format"] == "png"
    assert by_id["2:2"]["format"] == "svg"
    assert by_id["2:3"]["format"] == "png"
    assert by_id["2:1"]["width"] == 752


def test_asset_extractor_deduplicates_by_image_ref():
    """IMAGE fills sharing the same imageRef must yield a single asset entry."""
    data = {
        "name": "Root",
        "type": "FRAME",
        "visible": True,
        "children": [
            {
                "id": "10:1",
                "name": "A",
                "type": "RECTANGLE",
                "visible": True,
                "fills": [{"type": "IMAGE", "imageRef": "abc123"}],
            },
            {
                "id": "10:2",
                "name": "B",
                "type": "RECTANGLE",
                "visible": True,
                "fills": [{"type": "IMAGE", "imageRef": "abc123"}],
            },
            {
                "id": "10:3",
                "name": "C",
                "type": "RECTANGLE",
                "visible": True,
                "fills": [{"type": "IMAGE", "imageRef": "def456"}],
            },
        ],
    }
    assets = asset_pipeline.AssetExtractor().extract(data)
    refs = {a["ref"] for a in assets}
    assert "abc123" in refs
    assert "def456" in refs
    assert len([a for a in assets if a["ref"] == "abc123"]) == 1


def test_font_collector_maps_inter():
    data = _load_fixture("assets_simple.json")
    fonts = asset_pipeline.FontCollector().collect(data)
    assert "Inter" in fonts
    assert fonts["Inter"]["strategy"] == "next/font/google"
    assert fonts["Inter"]["importName"] == "Inter"


def test_pipeline_skip_download_builds_registry(tmp_path):
    data = _load_fixture("assets_simple.json")
    pipeline = asset_pipeline.AssetPipeline(
        public_dir=str(tmp_path / "public"),
        skip_download=True,
    )
    registry = pipeline.run(data)

    assert registry["stats"]["discovered"] == 3
    assert registry["stats"]["skipped"] == 3
    assert "Inter" in registry["fonts"]
    refs = {a["ref"] for a in asset_pipeline.AssetExtractor().extract(data)}
    for ref in refs:
        assert ref in registry["assets"]
        assert registry["assets"][ref]["publicPath"].startswith("/assets/figma/")
        assert "strategy" in registry["assets"][ref]


def test_pipeline_skips_existing_assets(tmp_path):
    """Если файл уже существует, не перезаписываем и не ломаем реестр."""
    data = _load_fixture("assets_simple.json")
    public_dir = tmp_path / "public"
    assets_dir = public_dir / "assets" / "figma"
    assets_dir.mkdir(parents=True, exist_ok=True)
    # Подготовим существующий SVG-файл для VECTOR-ноды 2:2.
    existing = assets_dir / "Logo_Icon_2_2.svg"
    existing.write_text('<svg xmlns="http://www.w3.org/2000/svg"><rect width="10" height="10"/></svg>', encoding="utf-8")

    pipeline = asset_pipeline.AssetPipeline(
        public_dir=str(public_dir),
        skip_download=False,
        downloader=asset_pipeline.AssetDownloader(skip_existing=True),
    )
    registry = pipeline.run(data)

    assert "2:2" in registry["assets"]
    assert registry["assets"]["2:2"]["publicPath"] == "/assets/figma/Logo_Icon_2_2.svg"
    assert registry["assets"]["2:2"]["skipped"] is False
    assert existing.read_text(encoding="utf-8") == '<svg xmlns="http://www.w3.org/2000/svg"><rect width="10" height="10"/></svg>'
    # API-запрос не прошел, но уже существующий asset не пострадал.


def test_downloader_batches_requests(monkeypatch):
    """AssetDownloader.get_image_urls должен разбивать node_ids на chunks."""
    calls = []

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        def get(self, url, **kwargs):
            calls.append(url)
            class Resp:
                status_code = 200
                text = '{"images": {}}'
                headers = {}
                def json(self):
                    return {"images": {}}
            return Resp()

    monkeypatch.setattr(asset_pipeline, "FigmaHTTPClient", FakeClient)
    downloader = asset_pipeline.AssetDownloader(
        token="token",
        url="https://www.figma.com/file/abc123",
        batch_size=3,
    )
    ids = [f"1:{i}" for i in range(10)]
    downloader.get_image_urls(ids, fmt="png")
    assert len(calls) == 4  # 10 / 3 -> 4 chunks


def test_downloader_cache_probe_for_existing_files(tmp_path):
    """Для уже существующих файлов is_cached возвращает путь, а API не вызывается."""
    assets_dir = tmp_path / "assets"
    assets_dir.mkdir(parents=True, exist_ok=True)
    existing = assets_dir / "img_1_1.png"
    existing.write_bytes(b"png")

    # Без client файл считается закэшированным.
    downloader = asset_pipeline.AssetDownloader(skip_existing=True)
    cached = downloader.is_cached("1:1", fmt="png", scale=1.0, assets_dir=assets_dir)
    assert cached is not None
    assert cached.exists()
    urls = downloader.get_image_urls(
        ["1:1"],
        fmt="png",
        assets_dir=assets_dir,
    )
    # file:// URLs are no longer emitted; local reuse happens inside AssetPipeline.
    assert "1:1" not in urls


def test_optimizer_graceful_fallback_when_tools_missing(tmp_path):
    svg = tmp_path / "test.svg"
    svg.write_text('<svg xmlns="http://www.w3.org/2000/svg"><rect width="10" height="10"/></svg>')
    optimizer = asset_pipeline.AssetOptimizer(enabled=True)
    result = optimizer.optimize(svg, "svg")
    # Если svgo не установлен — graceful fallback, результат False; если установлен — True.
    assert isinstance(result, bool)


def test_inline_svg_extractor_rejects_large_or_script():
    extractor = asset_pipeline.InlineSvgExtractor()
    small = Path(__file__).parent / "small.svg"
    small.write_text('<svg viewBox="0 0 24 24"><circle r="5"/></svg>')
    assert extractor.extract(small) == '<svg viewBox="0 0 24 24"><circle r="5"/></svg>'

    bad = Path(__file__).parent / "bad.svg"
    bad.write_text('<svg><script>alert(1)</script></svg>')
    assert extractor.extract(bad) is None

    use = Path(__file__).parent / "use.svg"
    use.write_text('<svg><use href="#x"/></svg>')
    assert extractor.extract(use) is None

    big = Path(__file__).parent / "big.svg"
    big.write_text('<svg>' + 'x' * 5000 + '</svg>')
    assert extractor.extract(big) is None

    small.unlink()
    bad.unlink()
    use.unlink()
    big.unlink()


def test_svg_classifier_icon_by_name():
    classifier = asset_pipeline.SvgClassifier()
    node = {"name": "Close Icon", "width": 24, "height": 24}
    svg = '<svg viewBox="0 0 24 24"><path d="M6 6l12 12"/></svg>'
    assert classifier.classify(node, svg, byte_size=len(svg)) == "icon"


def test_svg_classifier_simple_svg_inline():
    classifier = asset_pipeline.SvgClassifier()
    node = {"name": "Logo mark", "width": 120, "height": 40}
    svg = '<svg viewBox="0 0 120 40"><rect width="120" height="40"/></svg>'
    assert classifier.classify(node, svg, byte_size=len(svg)) == "inline"


def test_svg_classifier_complex_svg_to_image():
    classifier = asset_pipeline.SvgClassifier()
    node = {"name": "Big illustration", "width": 800, "height": 600}
    big_svg = '<svg viewBox="0 0 800 600" xmlns="http://www.w3.org/2000/svg">' + "x" * 2000 + '</svg>'
    assert classifier.classify(node, big_svg, byte_size=len(big_svg.encode("utf-8"))) == "image"


def test_svg_classifier_none_to_img():
    classifier = asset_pipeline.SvgClassifier()
    assert classifier.classify({"name": "Missing"}, None, byte_size=0) == "img"


def test_icon_component_written(tmp_path):
    svg_content = '<svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg"><circle r="10"/></svg>'
    pipeline = asset_pipeline.AssetPipeline(
        public_dir=str(tmp_path / "public"),
        components_dir=str(tmp_path / "src" / "components" / "icons"),
        skip_download=True,
    )
    dest = tmp_path / "public" / "assets" / "figma" / "close_icon_2_2.svg"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(svg_content, encoding="utf-8")

    icon_file = pipeline._write_icon_component("Close Icon", svg_content)
    assert icon_file.exists()
    assert "CloseIcon" in icon_file.read_text(encoding="utf-8")
    assert icon_file.name == "CloseIcon.tsx"


def test_malicious_icon_downgraded_to_image(tmp_path):
    """If SVG looks like an icon but fails security sanitization, it cannot become a component."""
    bad_svg = '<svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">\n<script\n>alert(1)</script\n>\n</svg>'
    pipeline = asset_pipeline.AssetPipeline(
        public_dir=str(tmp_path / "public"),
        components_dir=str(tmp_path / "src" / "components" / "icons"),
        skip_download=True,
    )
    dest = tmp_path / "public" / "assets" / "figma" / "close_icon_2_2.svg"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(bad_svg, encoding="utf-8")

    entry = pipeline._build_registry_entry(
        {"name": "Close Icon", "format": "svg", "type": "svg", "width": 24, "height": 24},
        "/assets/figma/close_icon_2_2.svg",
        optimized=False,
        skipped=False,
    )
    # Sanitization rejects the SVG, so it cannot become an inline/icon component.
    assert entry["strategy"] != "icon"
    assert "componentPath" not in entry
    # No malicious TSX file should have been written.
    assert not list((tmp_path / "src" / "components" / "icons").glob("*.tsx"))


def test_inline_svg_extractor_rejects_script_with_whitespace():
    """Spaces/newlines between '<' and tag name must not bypass the block."""
    extractor = asset_pipeline.InlineSvgExtractor()
    bad = Path(__file__).parent / "bad_whitespace.svg"
    bad.write_text('<svg><\nscript\n>alert(1)</\nscript\n></svg>')
    assert extractor.extract(bad) is None
    bad.unlink()


def test_inline_svg_extractor_rejects_foreign_object():
    extractor = asset_pipeline.InlineSvgExtractor()
    bad = Path(__file__).parent / "bad_foreign.svg"
    bad.write_text('<svg>\n< foreignObject >\n<iframe src="x"/>\n</ foreignObject >\n</svg>')
    assert extractor.extract(bad) is None
    bad.unlink()


def test_inline_svg_extractor_rejects_event_handlers_and_js_urls():
    extractor = asset_pipeline.InlineSvgExtractor()
    onload = Path(__file__).parent / "bad_onload.svg"
    onload.write_text('<svg onload="alert(1)"></svg>')
    assert extractor.extract(onload) is None

    href = Path(__file__).parent / "bad_href.svg"
    href.write_text('<svg><a xlink:href="javascript:alert(1)"><circle r="1"/></a></svg>')
    assert extractor.extract(href) is None

    onload.unlink()
    href.unlink()


def test_svg_classifier_rejects_script_with_whitespace():
    classifier = asset_pipeline.SvgClassifier()
    svg = '<svg><\nscript\n>alert(1)</\nscript\n></svg>'
    # Provide dimensions so the SVG is not treated as a tiny icon by default.
    assert classifier.classify({"name": "Bad", "width": 800, "height": 600}, svg, byte_size=len(svg)) == "image"


def test_asset_pipeline_rejects_public_dir_traversal(tmp_path):
    with pytest.raises(ValueError, match="escapes workspace"):
        asset_pipeline.AssetPipeline(public_dir="../escaped_public")


def test_asset_pipeline_rejects_components_dir_traversal(tmp_path):
    with pytest.raises(ValueError, match="escapes workspace"):
        asset_pipeline.AssetPipeline(
            public_dir=str(tmp_path / "public"),
            components_dir="../escaped_icons",
        )


def test_asset_pipeline_rejects_assets_dir_traversal(tmp_path):
    with pytest.raises(ValueError, match="outside public_dir"):
        asset_pipeline.AssetPipeline(
            public_dir=str(tmp_path / "public"),
            assets_dir="../escaped_assets",
        )


def test_downloader_rejects_file_scheme():
    downloader = asset_pipeline.AssetDownloader()
    dest = Path("/tmp/should_not_be_written")
    assert downloader.download("file:///etc/passwd", dest) is False


def test_downloader_rejects_non_http_scheme():
    downloader = asset_pipeline.AssetDownloader()
    dest = Path("/tmp/should_not_be_written")
    assert downloader.download("ftp://example.com/x.png", dest) is False


def test_main_rejects_file_path_traversal(tmp_path, monkeypatch):
    """CLI --file with traversal must exit before touching the filesystem."""
    fake_json = tmp_path / "figma_node.json"
    fake_json.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(
        sys, "argv",
        [
            "asset_pipeline.py",
            "--file", str(fake_json),
            "--registry", "../escaped_registry.json",
        ],
    )
    with pytest.raises(SystemExit) as exc_info:
        asset_pipeline.main()
    assert exc_info.value.code != 0


def test_main_rejects_public_dir_traversal(monkeypatch):
    """CLI --public-dir with traversal must exit before creating directories."""
    monkeypatch.setattr(
        sys, "argv",
        [
            "asset_pipeline.py",
            "--file", "figma_node.json",
            "--public-dir", "../escaped_public",
        ],
    )
    with pytest.raises(SystemExit) as exc_info:
        asset_pipeline.main()
    assert exc_info.value.code != 0


def test_safe_asset_url_allows_public_https() -> None:
    assert asset_downloader._is_safe_asset_url("https://example.com/image.png") is True


def test_safe_asset_url_blocks_private_ips() -> None:
    assert asset_downloader._is_safe_asset_url("http://127.0.0.1:8080/image.png") is False
    assert asset_downloader._is_safe_asset_url("http://10.0.0.1/image.png") is False
    assert asset_downloader._is_safe_asset_url("http://192.168.1.1/image.png") is False
    assert asset_downloader._is_safe_asset_url("http://169.254.169.254/metadata") is False


def test_safe_asset_url_blocks_non_http_schemes() -> None:
    assert asset_downloader._is_safe_asset_url("file:///etc/passwd") is False
    assert asset_downloader._is_safe_asset_url("ftp://example.com/image.png") is False


def test_download_asset_fails_closed_on_unsafe_url(tmp_path: Path) -> None:
    """SSRF attempts must fail without hitting the network."""
    dest = tmp_path / "stolen.txt"
    assert asset_downloader.download_asset("http://127.0.0.1:8080/admin", dest) is False
    assert not dest.exists()


def test_download_asset_fails_closed_when_downloader_raises(tmp_path: Path, monkeypatch) -> None:
    """If AssetDownloader fails, there must be no raw requests.get fallback."""

    def _boom(*args, **kwargs):
        raise RuntimeError("downloader unavailable")

    monkeypatch.setattr(asset_downloader, "_load_asset_pipeline", _boom)
    dest = tmp_path / "image.png"
    assert asset_downloader.download_asset("https://example.com/image.png", dest) is False
    assert not dest.exists()


def test_download_asset_passes_through_downloader(tmp_path: Path, monkeypatch) -> None:
    """Happy path delegates to AssetDownloader and writes the file."""
    dest = tmp_path / "image.png"

    class FakeDownloader:
        def download(self, url, path):
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"fake image")
            return True

    fake_module = type(sys)("fake_module")
    fake_module.AssetDownloader = FakeDownloader

    monkeypatch.setattr(asset_downloader, "_load_asset_pipeline", lambda: fake_module)
    assert asset_downloader.download_asset("https://example.com/image.png", dest) is True
    assert dest.read_bytes() == b"fake image"
