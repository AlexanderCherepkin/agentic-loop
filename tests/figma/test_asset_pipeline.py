import importlib.util
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
ASSET_PIPELINE_PATH = ROOT / "figma-agent-core" / "asset_pipeline.py"


def _load_asset_pipeline():
    spec = importlib.util.spec_from_file_location("figma_asset_pipeline", str(ASSET_PIPELINE_PATH))
    module = importlib.util.module_from_spec(spec)
    sys.modules["figma_asset_pipeline"] = module
    spec.loader.exec_module(module)
    return module


asset_pipeline = _load_asset_pipeline()


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
    small.write_text('<svg><circle r="5"/></svg>')
    assert extractor.extract(small) == '<svg><circle r="5"/></svg>'

    bad = Path(__file__).parent / "bad.svg"
    bad.write_text('<svg><script>alert(1)</script></svg>')
    assert extractor.extract(bad) is None

    big = Path(__file__).parent / "big.svg"
    big.write_text('<svg>' + 'x' * 5000 + '</svg>')
    assert extractor.extract(big) is None

    small.unlink()
    bad.unlink()
    big.unlink()
