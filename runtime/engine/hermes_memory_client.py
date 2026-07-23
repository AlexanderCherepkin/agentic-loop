from __future__ import annotations

import os
import re
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class HermesMemoryConfig:
    """Runtime configuration for the optional Hermes memory bridge.

    Hermes stores memories as `.md` files under `~/.hermes/memory/` and exposes
    a journey graph. This client reads/writes those files and, when available,
    calls the `hermes` CLI. If Hermes is not installed or configured, the
    client degrades gracefully.
    """

    enabled: bool = field(
        default_factory=lambda: os.getenv("HERMES_MEMORY_ENABLED", "true").lower()
        not in ("false", "0", "off", "no")
    )
    hermes_dir: Path = field(
        default_factory=lambda: Path.home() / ".hermes"
    )
    memory_dir: Path | None = None
    cli_path: str = field(default_factory=lambda: shutil.which("hermes") or "hermes")
    timeout: float = 10.0

    def __post_init__(self) -> None:
        env_dir = os.getenv("HERMES_DIR")
        if env_dir:
            self.hermes_dir = Path(env_dir)
        if self.memory_dir is None:
            self.memory_dir = self.hermes_dir / "memory"


class HermesUnavailable:
    """Sentinel returned when Hermes workspace is not reachable."""

    pass


class HermesMemoryClient:
    """Runtime client that bridges Agentic Loop to a local Hermes memory workspace.

    Operations are filesystem-first and CLI-second so the bridge works even
    when the Hermes process is not running. Writes are append-only Markdown
    notes; reads are constrained to the Hermes memory directory.
    """

    def __init__(self, config: HermesMemoryConfig | None = None):
        self.config = config or HermesMemoryConfig()

    @property
    def is_available(self) -> bool:
        if not self.config.enabled:
            return False
        if self.config.memory_dir is None:
            return False
        try:
            return self.config.memory_dir.exists()
        except Exception:
            return False

    def _safe_path(self, name: str) -> Path | None:
        if self.config.memory_dir is None:
            return None
        base = self.config.memory_dir
        # Normalize name and ensure it stays under memory_dir.
        clean = re.sub(r"[^\w\-.]", "_", name).strip("_")
        if not clean.endswith(".md"):
            clean += ".md"
        target = (base / clean).resolve()
        if not str(target).startswith(str(base.resolve())):
            return None
        return target

    def list_entries(self, limit: int = 200) -> dict[str, Any]:
        if not self.is_available:
            return {
                "available": False,
                "operation": "list",
                "entries": [],
                "note": "Hermes memory workspace not found. Configure ~/.hermes/memory or set HERMES_DIR.",
            }
        try:
            files = sorted(self.config.memory_dir.glob("*.md"), key=lambda p: p.stat().st_mtime, reverse=True)
            entries = [
                {
                    "name": f.stem,
                    "path": str(f),
                    "mtime": f.stat().st_mtime,
                }
                for f in files[:limit]
            ]
            return {
                "available": True,
                "operation": "list",
                "entries": entries,
                "total_found": len(files),
            }
        except Exception as exc:
            return {
                "available": False,
                "operation": "list",
                "entries": [],
                "note": f"Error reading Hermes memory: {exc}",
            }

    def read_entry(self, name: str) -> dict[str, Any]:
        target = self._safe_path(name)
        if target is None:
            return {
                "available": False,
                "operation": "read",
                "content": "",
                "note": "Invalid or unsafe Hermes memory name.",
            }
        if not self.is_available:
            return {
                "available": False,
                "operation": "read",
                "content": "",
                "note": "Hermes memory workspace not available.",
            }
        try:
            content = target.read_text(encoding="utf-8") if target.exists() else ""
            return {
                "available": True,
                "operation": "read",
                "name": name,
                "path": str(target),
                "content": content,
                "exists": target.exists(),
            }
        except Exception as exc:
            return {
                "available": False,
                "operation": "read",
                "content": "",
                "note": f"Error reading {target}: {exc}",
            }

    def write_entry(
        self,
        name: str,
        content: str,
        append: bool = True,
    ) -> dict[str, Any]:
        target = self._safe_path(name)
        if target is None:
            return {
                "available": False,
                "operation": "write",
                "written": False,
                "note": "Invalid or unsafe Hermes memory name.",
            }
        if not self.is_available:
            return {
                "available": False,
                "operation": "write",
                "written": False,
                "note": "Hermes memory workspace not available.",
            }
        try:
            self.config.memory_dir.mkdir(parents=True, exist_ok=True)
            if append and target.exists():
                existing = target.read_text(encoding="utf-8")
                full = f"{existing}\n\n---\n\n{content}"
            else:
                full = content
            target.write_text(full, encoding="utf-8")
            return {
                "available": True,
                "operation": "write",
                "written": True,
                "path": str(target),
            }
        except Exception as exc:
            return {
                "available": False,
                "operation": "write",
                "written": False,
                "note": f"Error writing {target}: {exc}",
            }

    def search_entries(
        self,
        query: str,
        limit: int = 5,
    ) -> dict[str, Any]:
        if not self.is_available:
            return {
                "available": False,
                "operation": "search",
                "results": [],
                "note": "Hermes memory workspace not available.",
            }
        try:
            files = list(self.config.memory_dir.glob("*.md"))
            q = query.lower()
            scored: list[tuple[float, Path]] = []
            for f in files:
                text = f.read_text(encoding="utf-8").lower()
                count = sum(1 for token in q.split() if token in text)
                if count:
                    scored.append((count, f))
            scored.sort(key=lambda x: x[0], reverse=True)
            results = [
                {
                    "name": f.stem,
                    "path": str(f),
                    "score": score,
                }
                for score, f in scored[:limit]
            ]
            return {
                "available": True,
                "operation": "search",
                "results": results,
                "total_found": len(scored),
            }
        except Exception as exc:
            return {
                "available": False,
                "operation": "search",
                "results": [],
                "note": f"Error searching Hermes memory: {exc}",
            }

    def journey_query(self, query: str = "") -> dict[str, Any]:
        """Query the Hermes journey graph if the CLI is available."""
        if not self.is_available:
            return {
                "available": False,
                "operation": "journey_query",
                "results": [],
                "note": "Hermes memory workspace not available.",
            }
        try:
            result = subprocess.run(
                [self.config.cli_path, "journey", "query", query],
                capture_output=True,
                text=True,
                timeout=self.config.timeout,
                check=False,
            )
            if result.returncode == 0:
                return {
                    "available": True,
                    "operation": "journey_query",
                    "raw": result.stdout,
                    "note": "Hermes CLI journey query succeeded.",
                }
        except FileNotFoundError:
            pass
        except Exception as exc:
            return {
                "available": False,
                "operation": "journey_query",
                "results": [],
                "note": f"Hermes CLI journey query failed: {exc}",
            }
        return {
            "available": False,
            "operation": "journey_query",
            "results": [],
            "note": "Hermes CLI not available; journey query degraded.",
        }

    def stats(self) -> dict[str, Any]:
        return {
            "available": self.is_available,
            "enabled": self.config.enabled,
            "hermes_dir": str(self.config.hermes_dir),
            "memory_dir": str(self.config.memory_dir) if self.config.memory_dir else None,
            "cli_path": self.config.cli_path,
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "available": self.is_available,
            "enabled": self.config.enabled,
            "hermes_dir": str(self.config.hermes_dir),
        }
