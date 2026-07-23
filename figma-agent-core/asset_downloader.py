import os
import re
import importlib.util
from pathlib import Path
from typing import Dict, List, Optional
from urllib.parse import urlparse


DEFAULT_PUBLIC_DIR = "public"
DEFAULT_IMAGES_DIR = "images"


def _load_asset_pipeline():
    here = Path(__file__).resolve().parent
    spec = importlib.util.spec_from_file_location("figma_asset_pipeline", str(here / "asset_pipeline.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _safe_filename(name: str, extension: str) -> str:
    """Превращает имя ноды в безопасное имя файла."""
    base = name.replace(".", "_").replace(" ", "_")
    base = re.sub(r"[^A-Za-z0-9_\-]", "", base)
    if not base:
        base = "asset"
    return f"{base}.{extension}"


def _is_safe_asset_url(url: str) -> bool:
    """Block non-public HTTP(S) targets to prevent SSRF via image URLs."""
    parsed = urlparse(url)
    scheme = parsed.scheme.lower()
    if scheme not in ("http", "https"):
        return False
    host = parsed.hostname or ""
    host_lower = host.lower()
    private_patterns = (
        r"^127\.",
        r"^10\.",
        r"^172\.(1[6-9]|2[0-9]|3[0-1])\.",
        r"^192\.168\.",
        r"^169\.254\.",
        r"^0\.0\.0\.0$",
        r"^::1$",
        r"^fc00:",
        r"^fe80:",
    )
    if any(re.match(p, host) for p in private_patterns):
        return False
    if host_lower in {"localhost", "metadata.google.internal", "metadata.aws.internal"}:
        return False
    if host_lower.startswith("metadata"):
        return False
    return True


def download_asset(url: str, dest_path: Path, timeout: int = 60) -> bool:
    """Скачивает ассет по URL и сохраняет в dest_path.

    Всегда использует AssetDownloader из asset_pipeline.py, который применяет
    rate limiting, retry, SSRF guard, content-type checks и SVG sanitization.
    Простого requests.get fallback больше нет — он обходил защиты и создавал
    повышенную поверхность атаки.
    """
    _ = timeout  # future use / API symmetry; AssetDownloader has its own timeout.
    # Reject non-public HTTP(S) targets to prevent local file exfiltration / SSRF.
    if not _is_safe_asset_url(url):
        return False
    try:
        module = _load_asset_pipeline()
        downloader = module.AssetDownloader()
        return downloader.download(url, dest_path)
    except Exception:
        # Fail closed: do not fall back to an unguarded raw HTTP client.
        return False


def save_asset(node_id: str, node_name: str, extension: str, image_url: str, public_dir: str = DEFAULT_PUBLIC_DIR) -> str:
    """
    Скачивает ассет и сохраняет его в public/images/.
    Возвращает путь, который можно использовать в Next.js-компоненте (начинается с /).
    """
    images_dir = Path(public_dir) / DEFAULT_IMAGES_DIR
    filename = _safe_filename(node_name, extension)
    # Добавляем уникальность по node_id, если имя совпадает.
    unique_name = f"{Path(filename).stem}_{node_id.replace(':', '_')}{Path(filename).suffix}"
    dest_path = images_dir / unique_name

    if download_asset(image_url, dest_path):
        return f"/{DEFAULT_IMAGES_DIR}/{unique_name}"
    return ""


def get_image_urls_from_figma(
    file_key: str,
    node_ids: List[str],
    figma_token: str,
    scale: float = 1.0,
    format: str = "png",
) -> Dict[str, str]:
    """
    Запрашивает URL'ы экспорта ассетов через Figma Images API.
    Возвращает {node_id: image_url}.
    """
    if not node_ids:
        return {}
    try:
        module = _load_asset_pipeline()
        downloader = module.AssetDownloader(token=figma_token, url=f"https://www.figma.com/file/{file_key}")
        return downloader.get_image_urls(node_ids, fmt=format, scale=scale)
    except Exception as e:
        print(f"[ERROR] Failed to fetch image URLs: {e}")
        return {}


def collect_assets_from_tree(node: Dict, result: Optional[List[Dict]] = None) -> List[Dict]:
    """Рекурсивно собирает все ноды, помеченные как isAsset."""
    if result is None:
        result = []
    if not isinstance(node, dict) or not node.get("visible", True):
        return result
    if node.get("isAsset"):
        result.append(node)
    for child in node.get("children", []):
        collect_assets_from_tree(child, result)
    return result
