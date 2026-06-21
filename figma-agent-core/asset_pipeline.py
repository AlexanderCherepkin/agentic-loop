import os
import re
import sys
import json
import shutil
import argparse
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

import requests
from dotenv import load_dotenv


load_dotenv()


DEFAULT_PUBLIC_DIR = "public"
DEFAULT_ASSETS_DIR = "assets/figma"
DEFAULT_REGISTRY_FILE = "asset_registry.json"
DEFAULT_IMAGES_FORMAT = "png"


# Популярные Google Fonts, которые next/font/google умеет импортировать.
GOOGLE_FONT_FAMILIES = {
    "Inter": "Inter",
    "Roboto": "Roboto",
    "Poppins": "Poppins",
    "Manrope": "Manrope",
    "Open Sans": "Open_Sans",
    "Lato": "Lato",
    "Montserrat": "Montserrat",
    "Raleway": "Raleway",
    "Nunito": "Nunito",
    "Playfair Display": "Playfair_Display",
    "Merriweather": "Merriweather",
    "Space Grotesk": "Space_Grotesk",
    "DM Sans": "DM_Sans",
    "Outfit": "Outfit",
    "Work Sans": "Work_Sans",
    "Fira Sans": "Fira_Sans",
    "Source Sans 3": "Source_Sans_3",
    "IBM Plex Sans": "IBM_Plex_Sans",
    "PT Sans": "PT_Sans",
}


def _safe_filename(name: str) -> str:
    base = name.replace(".", "_").replace(" ", "_")
    base = re.sub(r"[^A-Za-z0_9_\-]", "", base)
    if not base:
        base = "asset"
    return base


def _to_camel_case(snake: str) -> str:
    parts = re.split(r"[^A-Za-z0-9]+", snake)
    return parts[0].lower() + "".join(p.capitalize() for p in parts[1:] if p)


def _asset_dest_path(node_id: str, name: str, extension: str, assets_dir: Path) -> Path:
    stem = _safe_filename(name)
    unique = f"{stem}_{node_id.replace(':', '_').replace('-', '_')}"
    return assets_dir / f"{unique}.{extension}"


def _public_path(dest: Path, public_dir: Path) -> str:
    try:
        rel_path = dest.relative_to(public_dir).as_posix()
    except ValueError:
        rel_path = str(dest)
    if not rel_path.startswith("/"):
        rel_path = "/" + rel_path
    return rel_path


def _extract_box_size(node: Dict[str, Any]) -> Tuple[Optional[int], Optional[int]]:
    box = node.get("box") or node.get("absoluteBoundingBox") or {}
    width = box.get("width")
    height = box.get("height")
    if width is not None and height is not None:
        return int(round(width)), int(round(height))
    return None, None


class AssetExtractor:
    """Рекурсивно находит ассеты в сжатом дереве Figma."""

    def __init__(self) -> None:
        self.assets: List[Dict[str, Any]] = []
        self._seen: Set[str] = set()

    def extract(self, node: Dict[str, Any]) -> List[Dict[str, Any]]:
        self.assets = []
        self._seen = set()
        self._walk(node)
        return self.assets

    def _add_asset(
        self,
        node: Dict[str, Any],
        ref: str,
        fmt: str,
        asset_type: str,
    ) -> None:
        if ref in self._seen:
            return
        self._seen.add(ref)
        width, height = _extract_box_size(node)
        self.assets.append({
            "id": node.get("id", ""),
            "name": node.get("name", "asset"),
            "ref": ref,
            "format": fmt,
            "type": asset_type,
            "width": width,
            "height": height,
        })

    def _walk(self, node: Dict[str, Any]) -> None:
        if not isinstance(node, dict) or not node.get("visible", True):
            return

        node_type = node.get("type", "")
        node_id = node.get("id", "")

        if node_type == "IMAGE":
            self._add_asset(node, node_id, "png", "raster")

        elif node_type == "VECTOR":
            self._add_asset(node, node_id, "svg", "svg")

        elif node.get("isAsset"):
            fmt = node.get("assetFormat", "png")
            self._add_asset(node, node_id, fmt, "svg" if fmt == "svg" else "raster")

        # IMAGE fill внутри RECTANGLE/ELLIPSE/VECTOR.
        for fill in node.get("fills", []) or []:
            if fill.get("type") == "IMAGE":
                ref = fill.get("imageRef", "") or node_id
                if ref and ref not in self._seen:
                    self._add_asset(node, ref, "png", "raster")

        for child in node.get("children", []):
            self._walk(child)


class FontCollector:
    """Собирает шрифты из текстовых нод и мапит их на next/font/google."""

    def collect(self, node: Dict[str, Any]) -> Dict[str, Dict[str, str]]:
        families: Set[str] = set()
        self._collect_families(node, families)
        return self._build_fonts(families)

    def _collect_families(self, node: Dict[str, Any], families: Set[str]) -> None:
        if not isinstance(node, dict) or not node.get("visible", True):
            return
        style = node.get("style", {})
        if style:
            family = style.get("fontFamily")
            if family:
                families.add(family)
        for child in node.get("children", []):
            self._collect_families(child, families)

    def _build_fonts(self, families: Set[str]) -> Dict[str, Dict[str, str]]:
        result: Dict[str, Dict[str, str]] = {}
        for family in sorted(families):
            google_id = GOOGLE_FONT_FAMILIES.get(family)
            if not google_id:
                continue
            variable = _to_camel_case(google_id.replace("_", " ").lower())
            result[family] = {
                "strategy": "next/font/google",
                "package": f"next/font/google",
                "importName": google_id,
                "variableName": variable,
                "cssVar": f"--font-{variable}",
            }
        return result


class AssetDownloader:
    """Скачивание ассетов через Figma Images API."""

    def __init__(self, token: Optional[str] = None, url: Optional[str] = None) -> None:
        self.token = token or os.environ.get("FIGMA_TOKEN")
        self.url = url or os.environ.get("FIGMA_URL")
        self.file_key = self._parse_file_key(self.url) if self.url else None

    @staticmethod
    def _parse_file_key(url: str) -> Optional[str]:
        match = re.search(r"/file/([^/?#]+)", url) or re.search(r"/design/([^/?#]+)", url)
        return match.group(1) if match else None

    def get_image_urls(self, node_ids: List[str], fmt: str = "png", scale: float = 1.0) -> Dict[str, str]:
        if not self.file_key or not self.token or not node_ids:
            return {}
        ids_param = ",".join(node_ids)
        endpoint = f"https://api.figma.com/v1/images/{self.file_key}?ids={ids_param}&format={fmt}&scale={scale}"
        try:
            response = requests.get(endpoint, headers={"X-Figma-Token": self.token}, timeout=60)
            if response.status_code != 200:
                print(f"[WARNING] Figma images API returned {response.status_code}: {response.text}")
                return {}
            return response.json().get("images", {})
        except Exception as e:
            print(f"[ERROR] Failed to fetch image URLs: {e}")
            return {}

    def download(self, url: str, dest: Path) -> bool:
        try:
            response = requests.get(url, timeout=60)
            if response.status_code != 200:
                return False
            dest.parent.mkdir(parents=True, exist_ok=True)
            with open(dest, "wb") as f:
                f.write(response.content)
            return True
        except Exception:
            return False


class AssetOptimizer:
    """Оптимизация SVG (svgo) и PNG (sharp) с graceful fallback."""

    def __init__(self, enabled: bool = True) -> None:
        self.enabled = enabled

    def optimize(self, path: Path, fmt: str) -> bool:
        if not self.enabled:
            return False
        if fmt == "svg":
            return self._run_svgo(path)
        if fmt in ("png", "jpg", "jpeg"):
            return self._run_sharp(path)
        return False


class InlineSvgExtractor:
    """Пытается безопасно инлайнить простой SVG для page_composer."""

    MAX_SIZE_BYTES = 2048
    FORBIDDEN_TAGS = {"script", "foreignObject", "iframe", "object", "embed"}

    def extract(self, path: Path) -> Optional[str]:
        try:
            content = path.read_text(encoding="utf-8")
        except Exception:
            return None
        if len(content.encode("utf-8")) > self.MAX_SIZE_BYTES:
            return None
        lowered = content.lower()
        if any(f"<{tag}" in lowered for tag in self.FORBIDDEN_TAGS):
            return None
        # Убираем XML declaration и DOCTYPE.
        content = re.sub(r"<\?xml[^?]*\?>\s*", "", content)
        content = re.sub(r"<!DOCTYPE[^>]*>\s*", "", content, flags=re.IGNORECASE)
        return content.strip()


class AssetOptimizer:
    """Оптимизация SVG (svgo) и PNG (sharp) с graceful fallback."""

    def __init__(self, enabled: bool = True) -> None:
        self.enabled = enabled

    def optimize(self, path: Path, fmt: str) -> bool:
        if not self.enabled:
            return False
        if fmt == "svg":
            return self._run_svgo(path)
        if fmt in ("png", "jpg", "jpeg"):
            return self._run_sharp(path)
        return False

    def _run_svgo(self, path: Path) -> bool:
        if shutil.which("svgo") is None:
            print(f"[INFO] svgo not installed; skipping SVG optimization for {path}")
            return False
        try:
            result = subprocess.run(
                ["svgo", str(path), "-o", str(path)],
                capture_output=True,
                text=True,
                timeout=60,
            )
            return result.returncode == 0
        except Exception as e:
            print(f"[WARNING] svgo failed for {path}: {e}")
            return False

    def _run_sharp(self, path: Path) -> bool:
        if shutil.which("sharp") is None and shutil.which("npx") is None:
            print(f"[INFO] sharp not installed; skipping PNG optimization for {path}")
            return False
        try:
            cmd: List[str]
            if shutil.which("sharp"):
                cmd = ["sharp", str(path), "--optimize"]
            else:
                cmd = ["npx", "sharp", str(path), "--optimize"]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
            return result.returncode == 0
        except Exception as e:
            print(f"[WARNING] sharp failed for {path}: {e}")
            return False


class AssetPipeline:
    """Полный пайплайн: discovery → download → optimize → registry."""

    def __init__(
        self,
        public_dir: str = DEFAULT_PUBLIC_DIR,
        assets_dir: str = DEFAULT_ASSETS_DIR,
        downloader: Optional[AssetDownloader] = None,
        optimizer: Optional[AssetOptimizer] = None,
        skip_download: bool = False,
    ) -> None:
        self.public_dir = Path(public_dir)
        self.assets_dir = self.public_dir / assets_dir
        self.downloader = downloader or AssetDownloader()
        self.optimizer = optimizer or AssetOptimizer(enabled=True)
        self.skip_download = skip_download
        self._inline_extractor = InlineSvgExtractor()

    def run(
        self,
        figma_data: Dict[str, Any],
    ) -> Dict[str, Any]:
        extractor = AssetExtractor()
        assets = extractor.extract(figma_data)

        collector = FontCollector()
        fonts = collector.collect(figma_data)

        registry: Dict[str, Any] = {
            "assets": {},
            "fonts": fonts,
            "stats": {
                "discovered": len(assets),
                "downloaded": 0,
                "optimized": 0,
                "skipped": 0,
            },
        }

        if not assets:
            return registry

        if self.skip_download:
            for asset in assets:
                dest = _asset_dest_path(asset["id"], asset["name"], asset["format"], self.assets_dir)
                public_path = _public_path(dest, self.public_dir)
                registry["assets"][asset["ref"]] = {
                    "publicPath": public_path,
                    "type": asset["type"],
                    "format": asset["format"],
                    "width": asset["width"],
                    "height": asset["height"],
                    "originalName": asset["name"],
                    "optimized": False,
                    "skipped": True,
                }
                registry["stats"]["skipped"] += 1
            return registry

        # Группировка по формату для batch-запроса URL.
        svg_assets = [a for a in assets if a["format"] == "svg"]
        raster_assets = [a for a in assets if a["format"] != "svg"]

        urls: Dict[str, str] = {}
        if raster_assets:
            urls.update(self.downloader.get_image_urls([a["id"] for a in raster_assets], fmt="png"))
        if svg_assets:
            urls.update(self.downloader.get_image_urls([a["id"] for a in svg_assets], fmt="svg"))

        for asset in assets:
            ref = asset["ref"]
            dest = _asset_dest_path(asset["id"], asset["name"], asset["format"], self.assets_dir)
            url = urls.get(asset["id"])

            if not url:
                print(f"[WARNING] No download URL for asset {asset['id']} ({asset['name']})")
                registry["stats"]["skipped"] += 1
                continue

            if self.downloader.download(url, dest):
                optimized = self.optimizer.optimize(dest, asset["format"])
                public_path = _public_path(dest, self.public_dir)
                entry: Dict[str, Any] = {
                    "publicPath": public_path,
                    "type": asset["type"],
                    "format": asset["format"],
                    "width": asset["width"],
                    "height": asset["height"],
                    "originalName": asset["name"],
                    "optimized": optimized,
                    "skipped": False,
                }
                if asset["format"] == "svg":
                    inline = self._inline_extractor.extract(dest)
                    if inline:
                        entry["inlineSvg"] = inline
                registry["assets"][ref] = entry
                registry["stats"]["downloaded"] += 1
                if optimized:
                    registry["stats"]["optimized"] += 1
            else:
                print(f"[WARNING] Failed to download asset {asset['id']} from {url}")
                registry["stats"]["skipped"] += 1

        return registry


def write_registry(registry: Dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(registry, f, ensure_ascii=False, indent=2)


def main() -> None:
    parser = argparse.ArgumentParser(description="Asset Pipeline: download & optimize Figma assets, build registry and font manifest.")
    parser.add_argument("--file", default="figma_node.json", help="Path to Figma JSON structure.")
    parser.add_argument("--public-dir", default=DEFAULT_PUBLIC_DIR, help="Public directory root.")
    parser.add_argument("--assets-dir", default=DEFAULT_ASSETS_DIR, help="Subdirectory under public-dir for assets.")
    parser.add_argument("--registry", default=DEFAULT_REGISTRY_FILE, help="Output asset registry JSON path.")
    parser.add_argument("--figma-token", default=os.environ.get("FIGMA_TOKEN", ""), help="Figma API token.")
    parser.add_argument("--figma-url", default=os.environ.get("FIGMA_URL", ""), help="Figma file URL.")
    parser.add_argument("--skip-download", action="store_true", help="Build registry without downloading (uses synthetic publicPath values).")
    parser.add_argument("--no-optimize", action="store_true", help="Disable svgo/sharp optimization.")
    parser.add_argument("--format", default=DEFAULT_IMAGES_FORMAT, help="Default raster format (png).")
    args = parser.parse_args()

    file_path = Path(args.file)
    if not file_path.exists():
        print(f"[ERROR] File not found: {args.file}")
        sys.exit(1)

    with open(file_path, "r", encoding="utf-8") as f:
        figma_data = json.load(f)

    downloader = AssetDownloader(token=args.figma_token, url=args.figma_url)
    optimizer = AssetOptimizer(enabled=not args.no_optimize)
    pipeline = AssetPipeline(
        public_dir=args.public_dir,
        assets_dir=args.assets_dir,
        downloader=downloader,
        optimizer=optimizer,
        skip_download=args.skip_download,
    )

    registry = pipeline.run(figma_data)

    registry_path = Path(args.registry)
    write_registry(registry, registry_path)
    print(f"[ASSETS] registry: {registry_path}")
    print(f"[ASSETS] discovered={registry['stats']['discovered']} downloaded={registry['stats']['downloaded']} optimized={registry['stats']['optimized']} skipped={registry['stats']['skipped']}")


if __name__ == "__main__":
    main()
