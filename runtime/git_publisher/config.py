from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class GitPublisherConfig:
    provider: str = "github"  # github | gitlab
    github_token: str | None = None
    gitlab_token: str | None = None
    private: bool = True
    base_commit_message: str = "Initial commit by Agentic Loop"

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "GitPublisherConfig":
        return cls(
            provider=data.get("provider", "github"),
            github_token=data.get("github_token"),
            gitlab_token=data.get("gitlab_token"),
            private=bool(data.get("private", True)),
            base_commit_message=data.get(
                "base_commit_message", "Initial commit by Agentic Loop"
            ),
        )

    def token_for_provider(self) -> str | None:
        if self.provider == "github":
            return self.github_token
        if self.provider == "gitlab":
            return self.gitlab_token
        return None
