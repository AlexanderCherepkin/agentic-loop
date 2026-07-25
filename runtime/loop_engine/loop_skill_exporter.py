"""Export verified workflows to memory/wiki/ and optionally .claude/skills/."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class SkillExportResult:
    wiki_path: Path | None = None
    skill_path: Path | None = None
    approved: bool = False
    reason: str = ""


class LoopSkillExporter:
    """Save loop-derived artifacts.

    Policy:
    - Always auto-write successful workflows to memory/wiki/.
    - Write to .claude/skills/ only after explicit human approval.
    """

    def __init__(
        self,
        wiki_dir: Path | str = Path("memory") / "wiki" / "loop",
        skills_dir: Path | str = Path(".claude") / "skills",
    ):
        self.wiki_dir = Path(wiki_dir)
        self.skills_dir = Path(skills_dir)

    def export(
        self,
        workflow_name: str,
        workflow: dict[str, Any],
        human_approved: bool = False,
    ) -> SkillExportResult:
        safe_name = self._slugify(workflow_name)
        wiki_path = self._write_wiki(safe_name, workflow)

        if not human_approved:
            return SkillExportResult(
                wiki_path=wiki_path,
                skill_path=None,
                approved=False,
                reason="skill export requires explicit human approval",
            )

        skill_path = self._write_skill(safe_name, workflow)
        return SkillExportResult(
            wiki_path=wiki_path,
            skill_path=skill_path,
            approved=True,
            reason="human approved; skill materialized",
        )

    def export_wiki(self, name: str, content: str) -> Path:
        """Test-friendly alias: write raw markdown to the wiki directory."""
        self.wiki_dir.mkdir(parents=True, exist_ok=True)
        path = self.wiki_dir / f"{self._slugify(name)}.md"
        path.write_text(content, encoding="utf-8")
        return path

    def export_skill(self, name: str, content: str, approved: bool = False) -> Path:
        """Test-friendly alias: write raw markdown to .claude/skills/ only if approved."""
        if not approved:
            raise RuntimeError("Skill export requires explicit human approval")
        self.skills_dir.mkdir(parents=True, exist_ok=True)
        skill_dir = self.skills_dir / self._slugify(name)
        skill_dir.mkdir(parents=True, exist_ok=True)
        path = skill_dir / "SKILL.md"
        path.write_text(content, encoding="utf-8")
        return path

    def _write_wiki(self, safe_name: str, workflow: dict[str, Any]) -> Path:
        self.wiki_dir.mkdir(parents=True, exist_ok=True)
        path = self.wiki_dir / f"{safe_name}.md"
        body = self._render_markdown(safe_name, workflow)
        path.write_text(body, encoding="utf-8")
        return path

    def _write_skill(self, safe_name: str, workflow: dict[str, Any]) -> Path:
        skill_dir = self.skills_dir / safe_name
        skill_dir.mkdir(parents=True, exist_ok=True)
        path = skill_dir / "SKILL.md"
        body = self._render_skill_md(safe_name, workflow)
        path.write_text(body, encoding="utf-8")
        return path

    def _render_markdown(self, safe_name: str, workflow: dict[str, Any]) -> str:
        lines = [
            f"# Loop Workflow: {safe_name}",
            "",
            f"**Goal:** {workflow.get('goal', 'n/a')}",
            "",
            "## Preset",
            "",
            f"- ID: `{workflow.get('id', safe_name)}`",
            f"- Trust level: {workflow.get('trust_level', 'L1')}",
            f"- Max iterations: {workflow.get('max_iterations', 'n/a')}",
            "",
            "## Steps",
            "",
        ]
        for step in workflow.get("steps", []):
            lines.append(f"- **{step.get('name', 'step')}**: {step.get('description', '')}")
        lines.extend(["", "## Exit conditions", ""])
        for cond in workflow.get("exit_conditions", []):
            lines.append(f"- {cond}")
        lines.extend(["", "## Verification", ""])
        for item in workflow.get("verification_plan", []):
            lines.append(f"- {item}")
        lines.append("")
        return "\n".join(lines)

    def _render_skill_md(self, safe_name: str, workflow: dict[str, Any]) -> str:
        lines = [
            f"# {safe_name}",
            "",
            f"Trigger: `/{safe_name}`",
            "",
            f"{workflow.get('description', '')}",
            "",
            "## Goal",
            "",
            workflow.get("goal", "n/a"),
            "",
            "## Steps",
            "",
        ]
        for i, step in enumerate(workflow.get("steps", []), start=1):
            lines.append(f"{i}. {step.get('name', 'step')}: {step.get('description', '')}")
        lines.extend(
            [
                "",
                "## Verification",
                "",
                f"- Executor: {workflow.get('executor_model', 'claude-haiku-4-5')}",
                f"- Verifier: {workflow.get('verifier_model', 'claude-opus-4-8')}",
                f"- Critics: {workflow.get('min_critics', 2)}",
                "",
                "## Human zones",
                "",
            ]
        )
        for zone in workflow.get("human_zones", []):
            lines.append(f"- {zone}")
        lines.append("")
        return "\n".join(lines)

    @staticmethod
    def _slugify(name: str) -> str:
        return re.sub(r"[^a-z0-9_-]+", "-", name.lower().replace(" ", "-")).strip("-")
