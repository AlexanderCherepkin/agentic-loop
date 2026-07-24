"""SkillAutomation engine.

Detects new markdown sources worth turning into Claude Code skills and
decides whether the graphify knowledge graph needs a refresh after significant
workspace changes.
"""

from __future__ import annotations

import json
import logging
import re
import subprocess
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .config import SkillAutomationConfig

logger = logging.getLogger(__name__)

_PROCESS_SIGNALS = (
    "step", "algorithm", "flow", "pipeline", "process", "procedure",
    "how to", "howto", "guide", "tutorial", "workflow", "checklist",
    "recipe", "playbook", "runbook", "pattern", "protocol",
)


@dataclass
class SourceCandidate:
    """A markdown file that might become a skill."""

    path: str
    word_count: int
    process_signals: list[str] = field(default_factory=list)
    has_numbered_steps: bool = False
    estimated_reuse: str = "unknown"
    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "word_count": self.word_count,
            "process_signals": self.process_signals,
            "has_numbered_steps": self.has_numbered_steps,
            "estimated_reuse": self.estimated_reuse,
            "reason": self.reason,
        }


@dataclass
class GraphifyNeed:
    """Reasoning for a graphify update."""

    needs_update: bool
    changed_files: list[str] = field(default_factory=list)
    new_agents_detected: list[str] = field(default_factory=list)
    reason: str = ""
    warning_large_corpus: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "needs_update": self.needs_update,
            "changed_files": self.changed_files,
            "new_agents_detected": self.new_agents_detected,
            "reason": self.reason,
            "warning_large_corpus": self.warning_large_corpus,
        }


@dataclass
class SkillAutomationResult:
    """Output of a skill automation scan."""

    source_candidates: list[SourceCandidate] = field(default_factory=list)
    graphify_need: GraphifyNeed = field(default_factory=lambda: GraphifyNeed(False))
    already_proposed: list[str] = field(default_factory=list)
    scan_time: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_candidates": [c.to_dict() for c in self.source_candidates],
            "graphify_need": self.graphify_need.to_dict(),
            "already_proposed": self.already_proposed,
            "scan_time": self.scan_time,
        }


class SkillAutomationEngine:
    """Local engine for detecting skill sources and graphify refresh triggers."""

    def __init__(self, config: SkillAutomationConfig | None = None) -> None:
        self.config = config or SkillAutomationConfig()
        self.root = Path(self.config.workspace_root).resolve()
        self.state_path = self.root / self.config.state_file
        self.state_path.parent.mkdir(parents=True, exist_ok=True)

    # ── Public API ───────────────────────────────────────────────────────────

    def scan(self) -> SkillAutomationResult:
        """Run a full scan and return proposals."""
        already = self._load_already_proposed()
        candidates = self._detect_new_sources(already)
        graphify_need = self._detect_graphify_need()
        result = SkillAutomationResult(
            source_candidates=candidates,
            graphify_need=graphify_need,
            already_proposed=sorted(already),
        )
        self._append_state(result.to_dict())
        return result

    def propose_actions(self) -> list[dict[str, Any]]:
        """Return a flat list of actions suggested by the latest scan."""
        result = self.scan()
        actions: list[dict[str, Any]] = []
        if result.graphify_need.needs_update:
            actions.append({
                "type": "graphify_update",
                "reason": result.graphify_need.reason,
                "command": "graphify . --update",
                "warning_large_corpus": result.graphify_need.warning_large_corpus,
            })
        for candidate in result.source_candidates:
            actions.append({
                "type": "learn_from_source",
                "path": candidate.path,
                "reason": candidate.reason,
                "estimated_reuse": candidate.estimated_reuse,
                "requires_approval": True,
            })
        return actions

    def mark_proposed(self, path: str) -> None:
        """Record a source as already proposed so it is not repeated."""
        entry = {
            "type": "proposed",
            "path": path,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        self._append_state(entry)

    # ── Source detection ─────────────────────────────────────────────────────

    def _detect_new_sources(self, already_proposed: set[str]) -> list[SourceCandidate]:
        candidates: list[SourceCandidate] = []
        for ext in self.config.source_extensions:
            for path in self.root.rglob(f"*{ext}"):
                rel = path.relative_to(self.root).as_posix()
                if self._is_excluded(rel):
                    continue
                if rel in already_proposed:
                    continue
                try:
                    text = path.read_text(encoding="utf-8")
                except Exception:
                    continue
                candidate = self.assess_source_value(rel, text)
                if candidate:
                    candidates.append(candidate)
                if len(candidates) >= self.config.source_max_files_per_scan:
                    break
            if len(candidates) >= self.config.source_max_files_per_scan:
                break
        return candidates

    def assess_source_value(self, rel_path: str, text: str) -> SourceCandidate | None:
        """Heuristic assessment of whether a markdown file is worth a skill."""
        words = text.split()
        word_count = len(words)
        if word_count < self.config.source_min_words:
            return None

        lowered = text.lower()
        signals = [s for s in _PROCESS_SIGNALS if s in lowered]
        has_steps = bool(re.search(r"^\s*\d+\.\s+\S", text, re.MULTILINE))

        if not signals and not has_steps:
            return None

        estimated_reuse = "high" if (has_steps and len(signals) >= 2) else "medium" if has_steps else "low"
        reason_parts = [
            f"{word_count} words",
        ]
        if has_steps:
            reason_parts.append("numbered steps detected")
        if signals:
            reason_parts.append(f"process signals: {', '.join(signals[:3])}")

        return SourceCandidate(
            path=rel_path,
            word_count=word_count,
            process_signals=signals[:5],
            has_numbered_steps=has_steps,
            estimated_reuse=estimated_reuse,
            reason="; ".join(reason_parts),
        )

    # ── Graphify need detection ──────────────────────────────────────────────

    def _detect_graphify_need(self) -> GraphifyNeed:
        changed_files = self._git_changed_files()
        new_agents = self._detect_new_agents(changed_files)

        needs_update = bool(
            new_agents
            or len(changed_files) >= self.config.graphify_min_changed_files
        )

        reason_parts: list[str] = []
        if new_agents:
            reason_parts.append(
                f"new or renamed agents detected: {', '.join(new_agents[:3])}"
            )
        if len(changed_files) >= self.config.graphify_min_changed_files:
            reason_parts.append(f"{len(changed_files)} changed files >= threshold")

        warning_large = len(changed_files) >= self.config.graphify_large_corpus_warning
        if warning_large:
            reason_parts.append("large corpus — manual review recommended")

        return GraphifyNeed(
            needs_update=needs_update,
            changed_files=changed_files,
            new_agents_detected=new_agents,
            reason="; ".join(reason_parts) if reason_parts else "no significant changes",
            warning_large_corpus=warning_large,
        )

    def _git_changed_files(self) -> list[str]:
        """Return files changed since the last commit via git."""
        try:
            result = subprocess.run(
                ["git", "diff", "--name-only", "HEAD"],
                cwd=self.root,
                capture_output=True,
                text=True,
                check=False,
            )
            if result.returncode != 0:
                return []
            files = [line.strip() for line in result.stdout.splitlines() if line.strip()]
            # Also include staged but uncommitted changes if any.
            staged = subprocess.run(
                ["git", "diff", "--cached", "--name-only"],
                cwd=self.root,
                capture_output=True,
                text=True,
                check=False,
            )
            if staged.returncode == 0:
                files.extend(line.strip() for line in staged.stdout.splitlines() if line.strip())
            return sorted(set(files))
        except Exception as e:
            logger.warning("git diff failed: %s", e)
            return []

    def _detect_new_agents(self, changed_files: list[str]) -> list[str]:
        """Identify added/renamed agent markdown files under .agent_loop/."""
        new_agents: list[str] = []
        for f in changed_files:
            fpath = self.root / f
            if fpath.suffix != ".md":
                continue
            if ".agent_loop" not in f.replace("\\", "/"):
                continue
            try:
                if "## Role" in fpath.read_text(encoding="utf-8"):
                    new_agents.append(f)
            except Exception:
                continue
        return new_agents

    # ── State helpers ─────────────────────────────────────────────────────────

    def _load_already_proposed(self) -> set[str]:
        already: set[str] = set()
        if not self.state_path.exists():
            return already
        try:
            with self.state_path.open("r", encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        entry = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if entry.get("type") == "proposed" and "path" in entry:
                        already.add(entry["path"])
                    scan = entry.get("source_candidates") or []
                    for c in scan:
                        if isinstance(c, dict) and "path" in c:
                            already.add(c["path"])
        except Exception as e:
            logger.warning("failed to load skill automation state: %s", e)
        return already

    def _append_state(self, entry: dict[str, Any]) -> None:
        try:
            with self.state_path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except Exception as e:
            logger.warning("failed to write skill automation state: %s", e)

    def _is_excluded(self, rel_path: str) -> bool:
        rel_posix = rel_path.replace("\\", "/")
        return any(excluded.replace("\\", "/") in rel_posix for excluded in self.config.excluded_patterns)
