from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from .base import MCPServer


class HermesMemoryMCPServer(MCPServer):
    """MCP server that bridges Agentic Loop to a local Hermes memory workspace.

    Exposes five tools:
      - hermes_memory_list   — list Hermes memory entries.
      - hermes_memory_read   — read a Hermes memory .md file.
      - hermes_memory_write  — append a new Hermes memory note.
      - hermes_memory_search — keyword search across Hermes memory files.
      - hermes_journey_query — query the Hermes journey graph via CLI if available.

    The server is lazy-loaded and reports degraded if `~/.hermes/memory/` is
    absent or if the Hermes CLI is not installed.
    """

    def __init__(self, workspace_root: str = "."):
        super().__init__(name="hermes_memory", version="1.0.0")
        self.workspace = Path(workspace_root).resolve()
        self._degraded_reason: str | None = None
        self._client: Any = None
        self._ensure_client()
        self._register_tools()
        self._initialized = True

    def _ensure_client(self) -> None:
        try:
            from runtime.engine.hermes_memory_client import HermesMemoryClient, HermesMemoryConfig

            self._client = HermesMemoryClient(
                HermesMemoryConfig(
                    enabled=os.getenv("HERMES_MEMORY_ENABLED", "true").lower()
                    not in ("false", "0", "off", "no"),
                    hermes_dir=Path(os.getenv("HERMES_DIR", Path.home() / ".hermes")),
                    cli_path=os.getenv("HERMES_CLI", "hermes"),
                )
            )
            if not self._client.is_available:
                self._degraded_reason = (
                    "Hermes memory workspace not found. Install Hermes or set HERMES_DIR."
                )
        except Exception as exc:
            self._degraded_reason = f"Hermes memory client failed to initialize: {exc}"

    def _register_tools(self) -> None:
        s = self._schema
        self.register(
            "hermes_memory_list",
            "List Hermes memory entries.",
            s({"limit?": "int"}),
            self.hermes_memory_list,
        )
        self.register(
            "hermes_memory_read",
            "Read a Hermes memory .md file by name.",
            s({"name": "string"}),
            self.hermes_memory_read,
        )
        self.register(
            "hermes_memory_write",
            "Append a new note to a Hermes memory .md file.",
            s({"name": "string", "content": "string", "append?": "bool"}),
            self.hermes_memory_write,
        )
        self.register(
            "hermes_memory_search",
            "Keyword search across Hermes memory files.",
            s({"query": "string", "limit?": "int"}),
            self.hermes_memory_search,
        )
        self.register(
            "hermes_journey_query",
            "Query the Hermes journey graph via CLI if available.",
            s({"query?": "string"}),
            self.hermes_journey_query,
        )

    @staticmethod
    def _schema(props: dict[str, str]) -> dict[str, Any]:
        required = [k for k in props if not k.endswith("?")]
        properties: dict[str, Any] = {}
        type_map = {
            "string": "string",
            "int": "integer",
            "bool": "boolean",
            "float": "number",
            "array": "array",
            "object": "object",
        }
        for k, v in props.items():
            name = k.rstrip("?")
            properties[name] = {"type": type_map.get(v, "string"), "description": f"The {name} parameter"}
        return {"type": "object", "properties": properties, "required": required}

    def _check_degraded(self) -> dict[str, Any] | None:
        if self._degraded_reason:
            return {
                "status": "degraded",
                "error": self._degraded_reason,
                "fallback": "Install Hermes or configure HERMES_DIR/HERMES_MEMORY_ENABLED.",
            }
        return None

    def hermes_memory_list(self, limit: int = 200) -> dict[str, Any]:
        degraded = self._check_degraded()
        if degraded:
            return degraded
        return self._client.list_entries(limit=limit)

    def hermes_memory_read(self, name: str) -> dict[str, Any]:
        degraded = self._check_degraded()
        if degraded:
            return degraded
        return self._client.read_entry(name)

    def hermes_memory_write(
        self,
        name: str,
        content: str,
        append: bool = True,
    ) -> dict[str, Any]:
        degraded = self._check_degraded()
        if degraded:
            return degraded
        return self._client.write_entry(name, content, append=append)

    def hermes_memory_search(self, query: str, limit: int = 5) -> dict[str, Any]:
        degraded = self._check_degraded()
        if degraded:
            return degraded
        return self._client.search_entries(query, limit=limit)

    def hermes_journey_query(self, query: str = "") -> dict[str, Any]:
        degraded = self._check_degraded()
        if degraded:
            return degraded
        return self._client.journey_query(query)

    async def ping(self) -> bool:
        return True
