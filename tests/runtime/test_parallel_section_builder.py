"""pytest tests for the parallel section builder (AI Website Cloner runner).

Uses a fake runner and mocked git/worktree commands so tests do not require
a real git repository or a real Open Lovable runner.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import pytest

from runtime.premium_design.parallel_section_builder import ParallelSectionBuilder, SectionResult
from runtime.premium_design.open_lovable_bridge import OpenLovableBridgeResult


class FakeRunner:
    def __init__(self, success: bool = True, files: list[Path] | None = None):
        self.success = success
        self.files = files or []
        self.calls: list[tuple[str, Path]] = []

    def run_from_design_md(
        self,
        design_md_path: Path | str,
        output_dir: Path | str | None = None,
        extra_args: list[str] | None = None,
    ) -> OpenLovableBridgeResult:
        out = Path(output_dir).resolve() if output_dir else Path.cwd()
        self.calls.append((str(design_md_path), out))
        result = OpenLovableBridgeResult(ok=self.success, output_dir=out)
        resolved_files = [out / f for f in self.files]
        result.files = resolved_files
        for f in resolved_files:
            f.parent.mkdir(parents=True, exist_ok=True)
            f.write_text("// generated", encoding="utf-8")
        if not self.success:
            result.errors.append("runner failed")
        return result


@pytest.fixture
def git_repo(tmp_path: Path) -> Path:
    """Create a minimal git repository for worktree tests."""
    import subprocess

    subprocess.run(["git", "init"], cwd=str(tmp_path), check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=str(tmp_path), check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=str(tmp_path), check=True, capture_output=True)
    (tmp_path / "README.md").write_text("# Test", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=str(tmp_path), check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=str(tmp_path), check=True, capture_output=True)
    return tmp_path


@pytest.fixture
def master_design_md(git_repo: Path) -> Path:
    path = git_repo / "DESIGN.md"
    path.write_text(
        "# Design\n\nColor System\nTypography\nAnti-Slop Gates\n", encoding="utf-8"
    )
    return path


def test_create_worktree(git_repo: Path) -> None:
    builder = ParallelSectionBuilder(workspace_root=git_repo)
    path, result = builder._create_worktree("hero")
    assert path.exists()
    assert result.worktree_path == path
    assert not result.errors
    builder._remove_worktree(path)


def test_prepare_section_brief(git_repo: Path, master_design_md: Path) -> None:
    builder = ParallelSectionBuilder(workspace_root=git_repo)
    worktree = git_repo / "section-brief"
    worktree.mkdir(parents=True)
    brief = builder._prepare_section_brief(worktree, "hero", master_design_md)
    assert brief.exists()
    text = brief.read_text(encoding="utf-8")
    assert "Section brief: hero" in text
    assert "Color System" in text


def test_build_section_success(git_repo: Path, master_design_md: Path) -> None:
    generated = Path("Hero.tsx")
    fake_runner = FakeRunner(success=True, files=[generated])
    builder = ParallelSectionBuilder(workspace_root=git_repo, runner=fake_runner)

    result = builder.build_section("hero", master_design_md, keep_worktree=False)

    assert result.ok is True
    assert result.section_id == "hero"
    assert any(f.name == generated.name for f in result.files)
    assert len(fake_runner.calls) == 1


def test_build_section_failure(git_repo: Path, master_design_md: Path) -> None:
    fake_runner = FakeRunner(success=False, files=[])
    builder = ParallelSectionBuilder(workspace_root=git_repo, runner=fake_runner)

    result = builder.build_section("hero", master_design_md, keep_worktree=False)

    assert result.ok is False
    assert result.errors


def test_build_all_and_merge(git_repo: Path, master_design_md: Path) -> None:
    # Files must live inside the runner's output_dir so merge works via relative_to.
    hero_file = Path("Hero.tsx")
    cta_file = Path("Cta.tsx")
    runner = FakeRunner(success=True, files=[hero_file, cta_file])
    builder = ParallelSectionBuilder(workspace_root=git_repo, runner=runner)

    result = builder.build_all(
        section_ids=["hero", "cta"],
        master_design_md=master_design_md,
        merge_target=git_repo / "merged",
    )

    assert result.ok is True
    assert len(result.section_results) == 2
    assert len(result.merged_files) == 4  # 2 files × 2 sections


def test_merge_sections(git_repo: Path, tmp_path: Path) -> None:
    out_a = tmp_path / "a"
    out_a.mkdir(parents=True)
    file_a = out_a / "Hero.tsx"
    file_a.write_text("a", encoding="utf-8")

    out_b = tmp_path / "b"
    out_b.mkdir(parents=True)
    file_b = out_b / "Cta.tsx"
    file_b.write_text("b", encoding="utf-8")

    builder = ParallelSectionBuilder(workspace_root=git_repo)
    results = [
        SectionResult(section_id="hero", ok=True, output_dir=out_a, files=[file_a]),
        SectionResult(section_id="cta", ok=True, output_dir=out_b, files=[file_b]),
    ]

    merged = builder.merge_sections(results, tmp_path / "merged")
    assert (tmp_path / "merged" / "hero" / "Hero.tsx").exists()
    assert (tmp_path / "merged" / "cta" / "Cta.tsx").exists()
    assert len(merged) == 2


def test_apply_to_main_copies_motion(git_repo: Path, master_design_md: Path, tmp_path: Path) -> None:
    import json

    out_dir = tmp_path / "section-output"
    out_dir.mkdir(parents=True)
    tokens = {
        "motion": {
            "allowed_properties": {"$value": ["transform", "opacity"]},
            "duration": {
                "base": {"$type": "duration", "$value": "0.25s"},
                "fast": {"$type": "duration", "$value": "0.15s"},
            },
            "easing": {
                "product": {"$type": "cubicBezier", "$value": [0.16, 1, 0.3, 1]},
                "exit": {"$type": "cubicBezier", "$value": [0.4, 0, 1, 1]},
            },
        }
    }
    (out_dir / "design_tokens.json").write_text(json.dumps(tokens), encoding="utf-8")
    component = out_dir / "Hero.tsx"
    component.write_text("// hero", encoding="utf-8")

    builder = ParallelSectionBuilder(workspace_root=git_repo)
    section = SectionResult(section_id="hero", ok=True, output_dir=out_dir, files=[component])
    merged = builder.apply_to_main([section], tmp_path / "main")

    assert (tmp_path / "main" / "hero" / "Hero.tsx").exists()
    assert (tmp_path / "main" / "hero" / "motion.ts").exists()
    assert merged
