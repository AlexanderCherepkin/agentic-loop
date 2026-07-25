"""Tests for the /journey CLI."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))

from runtime.journey.cli import main


class TestJourneyCli:
    def test_cli_generates_html(self, tmp_path, monkeypatch):
        wiki_root = tmp_path / "memory" / "wiki"
        wiki_root.mkdir(parents=True)
        (wiki_root / "index.md").write_text("# Index", encoding="utf-8")
        output = tmp_path / "journey-out" / "index.html"
        code = main(["--workspace", str(tmp_path), "--output", str(output), "--no-open"])
        assert code == 0
        assert output.exists()
        html = output.read_text(encoding="utf-8")
        assert "Journey" in html
        assert "1 nodes" in html or " nodes" in html
