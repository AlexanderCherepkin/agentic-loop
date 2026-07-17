"""AI Website Cloner — parallel section builder via git worktrees.

Splits a landing page or multi-section design into independent sections,
spawns each section in its own git worktree, runs an AI code-generation
runner there, then merges the validated results back into the main tree.

This keeps the main worktree clean, allows failures per-section without
corrupting the whole build, and makes section-level rollbacks trivial.
"""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from .motion_executor import MotionExecutor
from .open_lovable_bridge import OpenLovableBridge, OpenLovableBridgeResult


@dataclass
class SectionResult:
    section_id: str
    ok: bool = False
    worktree_path: Path | None = None
    output_dir: Path | None = None
    files: list[Path] = field(default_factory=list)
    violations: list[dict[str, Any]] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


@dataclass
class ParallelBuildResult:
    ok: bool = False
    section_results: list[SectionResult] = field(default_factory=list)
    merged_files: list[Path] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


class ParallelSectionBuilder:
    """Build landing-page sections in isolated git worktrees and merge back."""

    def __init__(
        self,
        workspace_root: Path | str,
        runner: OpenLovableBridge | None = None,
        worktree_prefix: str = "section-",
        worktrees_dir: Path | str | None = None,
    ):
        self.workspace = Path(workspace_root).resolve()
        self.runner = runner or OpenLovableBridge(workspace_root=self.workspace)
        self.worktree_prefix = worktree_prefix
        self.worktrees_dir = Path(worktrees_dir) if worktrees_dir else self.workspace / ".claude" / "worktrees"

    def _git(self, *args: str, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["git", *args],
            cwd=str(cwd or self.workspace),
            capture_output=True,
            text=True,
            check=False,
        )

    def _create_worktree(
        self,
        section_id: str,
        base_ref: str = "HEAD",
    ) -> tuple[Path, SectionResult]:
        result = SectionResult(section_id=section_id)
        branch = f"{self.worktree_prefix}{section_id}"
        path = self.worktrees_dir / branch

        # Ensure a clean branch exists.
        branch_check = self._git("branch", "--list", branch)
        if branch not in branch_check.stdout:
            create = self._git("branch", branch, base_ref)
            if create.returncode != 0:
                result.errors.append(f"Could not create branch {branch}: {create.stderr}")
                return path, result

        # Remove stale worktree directory if it exists from a previous run.
        if path.exists():
            shutil.rmtree(path, ignore_errors=True)

        add = self._git("worktree", "add", "-B", branch, str(path))
        if add.returncode != 0:
            result.errors.append(f"Could not add worktree {path}: {add.stderr}")
            return path, result

        result.worktree_path = path
        result.notes.append(f"worktree created at {path}")
        return path, result

    def _remove_worktree(self, path: Path) -> None:
        self._git("worktree", "remove", "-f", str(path))
        # Best-effort cleanup of directory if git left it behind.
        if path.exists():
            shutil.rmtree(path, ignore_errors=True)

    def _prepare_section_brief(
        self,
        worktree: Path,
        section_id: str,
        master_design_md: Path,
        section_overrides: dict[str, Any] | None = None,
    ) -> Path:
        """Write a section-scoped DESIGN.md into the worktree."""
        brief_dir = worktree / "section-briefs"
        brief_dir.mkdir(parents=True, exist_ok=True)
        brief_path = brief_dir / f"{section_id}.md"

        master_text = master_design_md.read_text(encoding="utf-8") if master_design_md.exists() else ""
        overrides = section_overrides or {}

        lines = [
            f"# Section brief: {section_id}",
            "",
            f"Build only the `{section_id}` section. Do not generate other sections.",
            "",
            "## Master design context",
            "",
            master_text,
            "",
            "## Section overrides",
            "",
        ]
        for key, value in overrides.items():
            lines.append(f"- **{key}**: {value}")
        lines.append("")

        brief_path.write_text("\n".join(lines), encoding="utf-8")
        return brief_path

    def build_section(
        self,
        section_id: str,
        master_design_md: Path | str,
        section_overrides: dict[str, Any] | None = None,
        output_subdir: str = "section-output",
        keep_worktree: bool = False,
    ) -> SectionResult:
        """Build a single section in its own git worktree."""
        master_design_md = Path(master_design_md).resolve()
        worktree, result = self._create_worktree(section_id)
        if result.errors:
            return result

        brief_path = self._prepare_section_brief(
            worktree, section_id, master_design_md, section_overrides
        )

        out_dir = worktree / output_subdir
        runner_result = self.runner.run_from_design_md(brief_path, output_dir=out_dir)

        result.ok = runner_result.ok
        result.output_dir = runner_result.output_dir
        result.files = runner_result.files
        result.violations = runner_result.violations_after + runner_result.violations_before
        result.notes.extend(runner_result.notes)
        result.errors.extend(runner_result.errors)

        # Merge needs the files before the worktree is deleted.
        if not keep_worktree:
            # Copy outputs into a stable temp location so they survive worktree removal.
            stable_dir = self.workspace / ".claude" / "section-staging" / section_id
            if stable_dir.exists():
                shutil.rmtree(stable_dir, ignore_errors=True)
            stable_dir.mkdir(parents=True, exist_ok=True)
            staged_files: list[Path] = []
            for src in result.files:
                if src.is_file():
                    dst = stable_dir / src.name
                    shutil.copy2(src, dst)
                    staged_files.append(dst)
            result.files = staged_files
            result.output_dir = stable_dir
            self._remove_worktree(worktree)
        else:
            result.notes.append(f"worktree kept at {worktree}")

        return result

    def build_all(
        self,
        section_ids: list[str],
        master_design_md: Path | str,
        section_overrides: dict[str, dict[str, Any]] | None = None,
        output_subdir: str = "section-output",
        keep_worktrees: bool = False,
        merge_target: Path | str | None = None,
    ) -> ParallelBuildResult:
        """Build all sections sequentially (git worktrees are per-section and safe)."""
        overrides = section_overrides or {}
        result = ParallelBuildResult()

        for section_id in section_ids:
            section_result = self.build_section(
                section_id=section_id,
                master_design_md=master_design_md,
                section_overrides=overrides.get(section_id),
                output_subdir=output_subdir,
                keep_worktree=keep_worktrees,
            )
            result.section_results.append(section_result)

        result.ok = all(r.ok for r in result.section_results)

        if merge_target and result.ok:
            result.merged_files = self.merge_sections(result.section_results, merge_target)

        result.notes.append(
            f"{sum(1 for r in result.section_results if r.ok)}/{len(section_ids)} sections built successfully"
        )
        return result

    def merge_sections(
        self,
        section_results: list[SectionResult],
        target_dir: Path | str,
    ) -> list[Path]:
        """Copy all successful section outputs into a single target directory."""
        target = Path(target_dir).resolve()
        target.mkdir(parents=True, exist_ok=True)
        merged: list[Path] = []

        for section in section_results:
            if not section.ok or not section.output_dir:
                continue
            section_target = target / section.section_id
            section_target.mkdir(parents=True, exist_ok=True)
            for src in section.files:
                if src.is_file():
                    try:
                        rel = src.relative_to(section.output_dir)
                    except ValueError:
                        rel = src.name
                    dst = section_target / rel
                    dst.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(src, dst)
                    merged.append(dst)

        return merged

    def apply_to_main(
        self,
        section_results: list[SectionResult],
        target_dir: Path | str,
        copy_motion: bool = True,
    ) -> list[Path]:
        """Merge sections into main tree and optionally copy motion artifacts."""
        merged = self.merge_sections(section_results, target_dir)

        if copy_motion:
            for section in section_results:
                if not section.ok:
                    continue
                tokens_path = section.output_dir / "design_tokens.json" if section.output_dir else None
                if tokens_path and tokens_path.exists():
                    try:
                        import json
                        tokens = json.loads(tokens_path.read_text(encoding="utf-8"))
                        executor = MotionExecutor(tokens)
                        motion_result = executor.execute()
                        if motion_result.ok:
                            section_target = Path(target_dir).resolve() / section.section_id
                            executor.write_artifacts(motion_result, section_target, prefix="motion")
                    except Exception:
                        pass

        return merged
