"""SkillIntegration engine: deterministic write gate for skills and wiki.

Implements the contract of tooll_subagents/execution/skill_integrator.md:
- writes files only when user_approval is approved or modify
- rejects paths outside .claude/skills/ and memory/wiki/
- logs every write or rejection to the audit logger
- emits durable memory notes for created skills/wiki pages
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from runtime.safety.audit_logger import AuditEvent, AuditEventType, AuditLogger
from runtime.safety.file_system_guard import FileSystemGuardError, safe_write_file

from .config import SkillIntegrationConfig


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


@dataclass
class SkillProposal:
    """A proposed SKILL.md to create or update."""

    name: str
    trigger: str
    description: str
    decision_flow: list[str] = field(default_factory=list)
    failure_modes: list[dict[str, Any]] = field(default_factory=list)
    gotchas: list[dict[str, Any]] = field(default_factory=list)
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "trigger": self.trigger,
            "description": self.description,
            "decision_flow": self.decision_flow,
            "failure_modes": self.failure_modes,
            "gotchas": self.gotchas,
        }

    def render(self) -> str:
        lines = [
            "---",
            f"name: {self.name}",
            f"description: {self.description}",
            "---",
            "",
            f"# /{self.name}",
            "",
            f"> {self.description}",
            "",
            "## When to use",
            "",
            self.trigger,
            "",
        ]
        if self.decision_flow:
            lines.extend(["## Decision Flow", ""])
            for i, step in enumerate(self.decision_flow, start=1):
                lines.append(f"{i}. {step}")
            lines.append("")
        if self.failure_modes:
            lines.extend(["## Failure Modes", "", "| Condition | Response |", "|---|---|"])
            for fm in self.failure_modes:
                condition = fm.get("condition", "")
                response = fm.get("response", "")
                lines.append(f"| {condition} | {response} |")
            lines.append("")
        if self.gotchas:
            lines.extend(["## Gotchas", ""])
            for g in self.gotchas:
                title = g.get("title", "")
                symptom = g.get("symptom", "")
                fix = g.get("fix", "")
                lines.append(f"- **{title}** — {symptom} Fix: {fix}")
            lines.append("")
        return "\n".join(lines)


@dataclass
class WikiProposal:
    """A proposed wiki page to create or update."""

    name: str
    page_type: str
    description: str
    content: str
    links: list[str] = field(default_factory=list)
    existing: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "type": self.page_type,
            "description": self.description,
            "links": self.links,
            "existing": self.existing,
        }


@dataclass
class IntegrationResult:
    """Result of a skill integration operation."""

    status: str = "skipped"
    written_paths: list[str] = field(default_factory=list)
    rejected_paths: list[str] = field(default_factory=list)
    summary: str = ""
    memory_notes: list[dict[str, Any]] = field(default_factory=list)
    errors: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "written_paths": self.written_paths,
            "rejected_paths": self.rejected_paths,
            "summary": self.summary,
            "memory_notes": self.memory_notes,
            "errors": self.errors,
        }


class SkillIntegrationEngine:
    """Single write gate for all skill-related file mutations."""

    _NAME_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")

    def __init__(self, config: SkillIntegrationConfig | None = None) -> None:
        self.config = config or SkillIntegrationConfig()
        self.root = Path(self.config.workspace_root).resolve()
        self.skills_root = self.root / self.config.skills_dir
        self.wiki_root = self.root / self.config.wiki_dir
        self.audit_logger = AuditLogger(
            log_dir=self.root / self.config.audit_log_dir, buffer_size=1
        )

    # ── Public API ────────────────────────────────────────────────────────────

    def apply(
        self,
        operation: str,
        user_approval: str,
        skill_candidate: dict[str, Any] | None = None,
        wiki_updates: list[dict[str, Any]] | None = None,
        lint_plan: list[dict[str, Any]] | None = None,
        session_id: str = "",
    ) -> IntegrationResult:
        """Apply an approved skill/wiki operation."""
        result = IntegrationResult()

        if operation not in self.config.allowed_operations:
            result.status = "error"
            result.summary = f"Unknown operation: {operation}"
            return result

        if user_approval not in ("approved", "modify"):
            result.status = "rejected"
            result.summary = "User approval is required before writing files."
            self._log_rejected(operation, "approval_missing", result.summary, session_id)
            return result

        if operation == "create_skill" and skill_candidate:
            result = self._create_skill(skill_candidate, user_approval, session_id)
        elif operation == "update_skill" and skill_candidate:
            result = self._update_skill(skill_candidate, user_approval, session_id)
        elif operation == "ingest_wiki" and wiki_updates:
            result = self._ingest_wiki(wiki_updates, user_approval, session_id)
        elif operation == "lint_wiki" and lint_plan:
            result = self._apply_lint_plan(lint_plan, user_approval, session_id)
        else:
            result.status = "skipped"
            result.summary = "No actionable candidates provided."

        self.audit_logger.close()
        return result

    def prepare_skill_proposal(
        self,
        name: str,
        trigger: str,
        description: str,
        decision_flow: list[str] | None = None,
        failure_modes: list[dict[str, Any]] | None = None,
        gotchas: list[dict[str, Any]] | None = None,
    ) -> SkillProposal:
        """Normalize a raw skill candidate into a SkillProposal."""
        safe_name = self._normalize_name(name)
        return SkillProposal(
            name=safe_name,
            trigger=trigger,
            description=description,
            decision_flow=decision_flow or [],
            failure_modes=failure_modes or [],
            gotchas=gotchas or [],
        )

    def prepare_wiki_proposals(
        self, pages: list[dict[str, Any]]
    ) -> list[WikiProposal]:
        """Normalize raw wiki pages and detect duplicates against memory/wiki/."""
        existing = {p.stem for p in self.wiki_root.glob("*.md") if not p.name.startswith("_")}
        proposals: list[WikiProposal] = []
        for raw in pages:
            page_type = raw.get("type", raw.get("page_type", "concept"))
            name = self._normalize_wiki_name(raw.get("name", "untitled"))
            stem = f"{page_type}-{name}"
            content = raw.get("content", "")
            if "[[" not in content:
                for link in raw.get("links", []):
                    content += f"\n\nSee also: [[{link}]]."
            proposals.append(
                WikiProposal(
                    name=name,
                    page_type=page_type,
                    description=raw.get("description", ""),
                    content=self._render_wiki_page(stem, raw, content),
                    links=raw.get("links", []),
                    existing=stem in existing,
                )
            )
        return proposals

    # ── Skill write helpers ───────────────────────────────────────────────────

    def _create_skill(
        self, candidate: dict[str, Any], user_approval: str, session_id: str
    ) -> IntegrationResult:
        result = IntegrationResult(status="created")
        proposal = self.prepare_skill_proposal(
            name=candidate.get("name", ""),
            trigger=candidate.get("trigger", candidate.get("when_to_use", "")),
            description=candidate.get("description", ""),
            decision_flow=candidate.get("decision_flow", []),
            failure_modes=candidate.get("failure_modes", []),
            gotchas=candidate.get("gotchas", []),
        )

        skill_dir = self.skills_root / proposal.name
        skill_path = skill_dir / "SKILL.md"

        if not self._is_allowed_path(skill_path, self.skills_root):
            result.status = "error"
            result.rejected_paths.append(str(skill_path))
            result.summary = f"Path blocked by filesystem guard: {skill_path}"
            self._log_rejected("create_skill", "path_guard", result.summary, session_id)
            return result

        if skill_path.exists() and user_approval != "modify":
            result.status = "rejected"
            result.rejected_paths.append(str(skill_path))
            result.summary = f"Skill '{proposal.name}' already exists. Pass modify approval to overwrite."
            self._log_rejected("create_skill", "exists", result.summary, session_id)
            return result

        try:
            safe_write_file(skill_dir, "SKILL.md", proposal.render())
            result.written_paths.append(str(skill_path))
            result.summary = f"Created skill '{proposal.name}'."
            result.memory_notes.append(
                {
                    "type": "project",
                    "title": f"Skill created: {proposal.name}",
                    "body": f"Trigger: {proposal.trigger}. Description: {proposal.description}",
                    "tags": ["skill"],
                    "source": str(skill_path),
                }
            )
            self._log_written("create_skill", str(skill_path), session_id)
        except FileSystemGuardError as exc:
            result.status = "error"
            result.rejected_paths.append(str(skill_path))
            result.errors.append({"path": str(skill_path), "reason": str(exc)})
            result.summary = f"Filesystem guard blocked skill write: {exc}"
            self._log_rejected("create_skill", "fs_guard", str(exc), session_id)
        except Exception as exc:
            result.status = "error"
            result.errors.append({"path": str(skill_path), "reason": str(exc)})
            result.summary = f"Failed to write skill: {exc}"

        return result

    def _update_skill(
        self, candidate: dict[str, Any], user_approval: str, session_id: str
    ) -> IntegrationResult:
        if user_approval != "modify":
            result = IntegrationResult(status="rejected")
            result.rejected_paths.append(candidate.get("name", "unknown"))
            result.summary = "Update skill requires modify approval."
            return result
        return self._create_skill(candidate, "modify", session_id)

    # ── Wiki write helpers ────────────────────────────────────────────────────

    def _ingest_wiki(
        self, updates: list[dict[str, Any]], user_approval: str, session_id: str
    ) -> IntegrationResult:
        result = IntegrationResult(status="created")
        proposals = self.prepare_wiki_proposals(updates)

        for proposal in proposals:
            stem = f"{proposal.page_type}-{proposal.name}"
            path = self.wiki_root / f"{stem}.md"

            if not self._is_allowed_path(path, self.wiki_root):
                result.rejected_paths.append(str(path))
                result.errors.append({"path": str(path), "reason": "path outside wiki root"})
                self._log_rejected("ingest_wiki", "path_guard", str(path), session_id)
                continue

            if proposal.existing and user_approval != "modify":
                result.rejected_paths.append(str(path))
                result.errors.append(
                    {"path": str(path), "reason": "page exists; per-page modify approval required"}
                )
                self._log_rejected("ingest_wiki", "exists", str(path), session_id)
                continue

            try:
                safe_write_file(self.wiki_root, f"{stem}.md", proposal.content)
                result.written_paths.append(str(path))
                self._log_written("ingest_wiki", str(path), session_id)
                result.memory_notes.append(
                    {
                        "type": "project",
                        "title": f"Wiki page ingested: {proposal.name}",
                        "body": proposal.description,
                        "tags": ["wiki", "ingest"],
                        "source": str(path),
                    }
                )
            except FileSystemGuardError as exc:
                result.rejected_paths.append(str(path))
                result.errors.append({"path": str(path), "reason": str(exc)})
                self._log_rejected("ingest_wiki", "fs_guard", str(exc), session_id)
            except Exception as exc:
                result.rejected_paths.append(str(path))
                result.errors.append({"path": str(path), "reason": str(exc)})

        if result.written_paths:
            self._update_wiki_index(proposals)
            result.summary = f"Ingested {len(result.written_paths)} wiki page(s)."
            result.status = "created"
        elif result.rejected_paths and not result.errors:
            result.status = "rejected"
            result.summary = "All wiki pages rejected; check approvals and duplicates."
        else:
            result.status = "error" if result.errors else "skipped"
            result.summary = (
                "No wiki pages written." if not result.errors else "Errors occurred during wiki ingest."
            )

        return result

    def _apply_lint_plan(
        self, plan: list[dict[str, Any]], user_approval: str, session_id: str
    ) -> IntegrationResult:
        result = IntegrationResult(status="skipped")
        for action in plan:
            target = Path(action.get("target", ""))
            if not target.is_absolute():
                target = self.wiki_root / target
            if not self._is_allowed_path(target, self.wiki_root):
                result.rejected_paths.append(str(target))
                continue
            op = action.get("action")
            if op == "delete":
                try:
                    if target.exists():
                        target.unlink()
                        result.written_paths.append(str(target))
                        self._log_written("lint_wiki_delete", str(target), session_id)
                except Exception as exc:
                    result.errors.append({"path": str(target), "reason": str(exc)})
            elif op in ("merge", "relink", "mark_deprecated"):
                # Merge/relink are human-approved in the plan; mark deprecated rewrites page.
                if op == "mark_deprecated":
                    content = target.read_text(encoding="utf-8") if target.exists() else ""
                    if "status: deprecated" not in content:
                        content = f"---\nname: {target.stem}\nmetadata:\n  type: wiki\n  status: deprecated\n  updated: {_now()}\n---\n\n{content}"
                        try:
                            safe_write_file(self.wiki_root, target.name, content)
                            result.written_paths.append(str(target))
                            self._log_written("lint_wiki_deprecate", str(target), session_id)
                        except Exception as exc:
                            result.errors.append({"path": str(target), "reason": str(exc)})
        if result.written_paths:
            result.status = "created"
            result.summary = f"Applied {len(result.written_paths)} lint action(s)."
        elif result.rejected_paths:
            result.status = "rejected"
            result.summary = "Lint plan rejected by guard."
        return result

    # ── Index management ──────────────────────────────────────────────────────

    def _update_wiki_index(self, proposals: list[WikiProposal]) -> None:
        index_path = self.wiki_root / "index.md"
        lines: list[str] = []
        if index_path.exists():
            lines = index_path.read_text(encoding="utf-8").splitlines()
        else:
            lines = ["# Wiki Index", ""]
        existing_links = {name.strip("[]") for name in re.findall(r"\[\[([^\]]+)\]\]", "\n".join(lines))}
        new_links = [f"- [[{p.name}]] — {p.description}" for p in proposals if p.name not in existing_links]
        if new_links:
            if lines and lines[-1].strip():
                lines.append("")
            lines.extend(new_links)
            safe_write_file(self.wiki_root, "index.md", "\n".join(lines) + "\n")

    # ── Normalization and rendering ───────────────────────────────────────────

    def _normalize_name(self, name: str) -> str:
        safe = re.sub(r"[^a-z0-9\-_]+", "-", name.lower()).strip("-")
        safe = re.sub(r"-+", "-", safe)
        if not self._NAME_RE.match(safe):
            safe = re.sub(r"[^a-z0-9-]", "-", safe).strip("-") or "skill"
        return safe[:64]

    def _normalize_wiki_name(self, name: str) -> str:
        safe = re.sub(r"[^a-z0-9\-_ ]+", "-", name.lower()).strip("-")
        safe = re.sub(r"\s+", "-", safe)
        safe = re.sub(r"-+", "-", safe)
        return safe[:64] or "untitled"

    def _render_wiki_page(self, stem: str, raw: dict[str, Any], content: str) -> str:
        page_type = raw.get("type", raw.get("page_type", "concept"))
        description = raw.get("description", "")
        lines = [
            "---",
            f"name: {stem}",
            f"description: {description}",
            "metadata:",
            f"  type: {page_type}",
            "  status: draft",
            f"  created: {_now()}",
            f"  updated: {_now()}",
        ]
        sources = raw.get("sources", [])
        if sources:
            lines.append(f"  sources: {sources}")
        lines.extend(["---", ""])
        if not content.startswith("#"):
            lines.append(f"# {stem}")
            lines.append("")
        lines.append(content)
        return "\n".join(lines) + "\n"

    # ── Guards and audit helpers ──────────────────────────────────────────────

    def _is_allowed_path(self, path: Path, base: Path) -> bool:
        try:
            path.relative_to(base)
        except ValueError:
            return False
        posix = path.as_posix().lower()
        for blocked in self.config.blocked_components:
            if blocked.lower() in posix.split("/"):
                return False
        return True

    def _log_written(self, operation: str, path: str, session_id: str) -> None:
        self.audit_logger.log(
            AuditEvent(
                event_type=AuditEventType.STATE_CHANGE,
                audit_anchor="skill_integration",
                agent_path=f"skill_integration/{operation}",
                session_id=session_id,
                payload={"operation": operation, "path": path, "verdict": "written"},
            )
        )

    def _log_rejected(self, operation: str, reason_code: str, reason: str, session_id: str) -> None:
        self.audit_logger.log(
            AuditEvent(
                event_type=AuditEventType.SAFETY_BLOCKED,
                audit_anchor="skill_integration",
                agent_path=f"skill_integration/{operation}",
                session_id=session_id,
                payload={"operation": operation, "reason_code": reason_code, "reason": reason},
            )
        )
