from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from .base import MCPServer, MCPToolResult
from runtime.notifications import NotificationsConfig, NotificationsEngine
from runtime.notifications.engine import NotificationPayload


class NotificationMCPServer(MCPServer):
    """MCP server for dispatching pipeline completion notifications."""

    def __init__(self, workspace_root: str = "."):
        super().__init__(name="notifications", version="1.0.0")
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
            "dispatch_notification",
            "Dispatch a pipeline completion notification to configured channels",
            self._schema({
                "project_id": "string",
                "status": "string",
                "brief?": "string",
                "message?": "string",
                "url?": "string",
                "error?": "string",
            }),
            self.dispatch_notification,
        )

    async def dispatch_notification(
        self,
        project_id: str,
        status: str,
        brief: str = "",
        message: str = "",
        url: str | None = None,
        error: str | None = None,
    ) -> dict[str, Any]:
        try:
            config = NotificationsConfig()
            engine = NotificationsEngine(config)
            payload = NotificationPayload(
                project_id=project_id,
                status=status,
                brief=brief,
                message=message,
                url=url,
                error=error,
            )
            result = await engine.dispatch(payload)
            return {
                "status": "success",
                "dispatched": result.dispatched,
                "failed": result.failed,
                "results": [
                    {"channel": r.channel, "ok": r.ok, "detail": r.detail}
                    for r in result.results
                ],
            }
        except Exception as exc:
            return {"status": "error", "detail": str(exc)}
