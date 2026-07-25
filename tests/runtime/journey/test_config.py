"""Tests for /journey configuration."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))

from runtime.journey.config import JourneyConfig


class TestJourneyConfig:
    def test_paths_resolve(self, tmp_path):
        config = JourneyConfig(workspace_root=tmp_path)
        assert config.wiki_root == tmp_path / "memory" / "wiki"
        assert config.skills_root == tmp_path / ".claude" / "skills"
        assert config.output_path == tmp_path / "journey-out" / "index.html"
