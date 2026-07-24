"""Configuration for the skill integration engine."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class SkillIntegrationConfig:
    """Configuration for SkillIntegrationEngine."""

    workspace_root: str | Path = "."
    skills_dir: str = ".claude/skills"
    wiki_dir: str = "memory/wiki"
    allowed_operations: tuple[str, ...] = (
        "create_skill",
        "update_skill",
        "ingest_wiki",
        "lint_wiki",
        "none",
    )
    blocked_components: tuple[str, ...] = (
        ".env",
        ".env.local",
        ".env.production",
        ".env.development",
        ".ssh",
        "id_rsa",
        "id_ed25519",
        "id_ecdsa",
        "known_hosts",
        "authorized_keys",
        "node_modules",
        "__pycache__",
        ".git",
    )
    audit_log_dir: str = ".audit"

    def to_dict(self) -> dict[str, Any]:
        return {
            "workspace_root": str(self.workspace_root),
            "skills_dir": self.skills_dir,
            "wiki_dir": self.wiki_dir,
            "allowed_operations": list(self.allowed_operations),
            "blocked_components": list(self.blocked_components),
            "audit_log_dir": self.audit_log_dir,
        }
