from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from .base import MCPServer, MCPToolResult
from runtime.git_publisher import GitPublisherConfig, GitPublisherEngine


class GitPublisherMCPServer(MCPServer):
    """MCP server for publishing generated codebases to GitHub/GitLab."""

    def __init__(self, workspace_root: str = "."):
        super().__init__(name="git_publisher", version="1.0.0")
        self.workspace = Path(workspace_root).resolve()
        self._register_all()

    def _schema(self, props: dict[str, str]) -> dict[str, Any]:
        required = [k for k in props if not k.endswith("?")]
        properties: dict[str, Any] = {}
        for k, v in props.items():
            name = k[:-1] if k.endswith("?") else k
            properties[name] = {"type": v}
        return {
            "type": "object",
            "properties": properties,
            "required": required,
        }

    def _register_all(self):
        self.register(
            "publish_repository",
            "Create a GitHub/GitLab repository and commit generated files",
            self._schema({
                "project_id": "string",
                "provider?": "string",
                "codebase": "object",
                "private?": "boolean",
            }),
            self.publish_repository,
        )
        self.register(
            "check_configured",
            "Check whether the configured provider token is available",
            self._schema({"provider?": "string"}),
            self.check_configured,
        )

    async def publish_repository(
        self,
        project_id: str,
        codebase: dict[str, str],
        provider: str = "github",
        private: bool = True,
    ) -> dict[str, Any]:
        try:
            config = GitPublisherConfig(
                provider=provider,
                github_token=os.environ.get("GITHUB_TOKEN"),
                gitlab_token=os.environ.get("GITLAB_TOKEN"),
                private=private,
            )
            engine = GitPublisherEngine(config)
            result = engine.publish(project_id, codebase)
            return {
                "status": "success" if result.success else "failed",
                "provider": result.provider,
                "url": result.url,
                "clone_url": result.clone_url,
                "files_committed": result.files_committed,
                "error": result.error,
            }
        except Exception as exc:
            return {"status": "error", "detail": str(exc)}

    async def check_configured(self, provider: str = "github") -> dict[str, Any]:
        token = os.environ.get("GITHUB_TOKEN") if provider == "github" else os.environ.get("GITLAB_TOKEN")
        return {"provider": provider, "configured": bool(token)}
