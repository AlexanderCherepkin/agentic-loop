"""21st.dev MCP server.

Exposes the 21st.dev component registry as an MCP category `components_21st`.
Provides deterministic search, preview, and install-planning tools so the
Agentic Loop can pull vetted React/Tailwind components instead of generating
slop from scratch.

The server degrades gracefully when the 21st.dev public API is unavailable
or when `requests` is not installed: it falls back to a curated offline
snapshot of high-quality components.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .base import MCPServer


@dataclass
class Component21st:
    name: str
    category: str
    author: str
    install_command: str
    preview_url: str = ""
    dependencies: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)


class TwentyFirstMCPServer(MCPServer):
    """MCP server wrapping the 21st.dev component registry."""

    DEFAULT_COMPONENTS: list[Component21st] = [
        Component21st(
            name="@21st-century/hero",
            category="marketing",
            author="21st",
            install_command="npx shadcn add @21st-century/hero",
            tags=["hero", "landing", "marketing"],
        ),
        Component21st(
            name="@aceternity/animated-card",
            category="effect",
            author="aceternity",
            install_command="npx shadcn add @aceternity/animated-card",
            tags=["card", "animation", "effect"],
        ),
        Component21st(
            name="@magicui/particles",
            category="background",
            author="magicui",
            install_command="npx shadcn add @magicui/particles",
            tags=["particles", "background", "canvas"],
        ),
        Component21st(
            name="@number-flow/react",
            category="data",
            author="number-flow",
            install_command="npm install @number-flow/react",
            dependencies=["@number-flow/react"],
            tags=["number", "animation", "data"],
        ),
        Component21st(
            name="@react-bits/text-rotate",
            category="text",
            author="react-bits",
            install_command="npx shadcn add @react-bits/text-rotate",
            tags=["text", "animation", "typography"],
        ),
    ]

    def __init__(self, workspace_root: str = "."):
        super().__init__(name="21st_components", version="1.0.0")
        self._initialized = True
        self.workspace = Path(workspace_root).resolve()
        self._components: list[Component21st] = list(self.DEFAULT_COMPONENTS)
        self._degraded_reason: str | None = None
        self._register_tools()
        self._load_remote_catalog()

    def _register_tools(self) -> None:
        s = self._schema
        self.register(
            "search_components",
            "Search 21st.dev components by keyword, category, or tag",
            s({"query?": "string", "category?": "string", "tag?": "string", "limit?": "int"}),
            self.search_components,
        )
        self.register(
            "get_component_details",
            "Get full details for a specific 21st.dev component",
            s({"name": "string"}),
            self.get_component_details,
        )
        self.register(
            "plan_install",
            "Generate an install plan for one or more components",
            s({"names": "array"}),
            self.plan_install,
        )
        self.register(
            "check_stack_compatibility",
            "Check whether selected components fit the current project stack",
            s({"names": "array", "framework?": "string", "tailwind?": "bool"}),
            self.check_stack_compatibility,
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
            properties[name] = {
                "type": type_map.get(v, "string"),
                "description": f"The {name} parameter",
            }
        return {"type": "object", "properties": properties, "required": required}

    def _load_remote_catalog(self) -> None:
        try:
            import urllib.request
            url = "https://21st.dev/api/components"
            with urllib.request.urlopen(url, timeout=8) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                if isinstance(data, list):
                    self._components = [
                        Component21st(
                            name=c.get("name", ""),
                            category=c.get("category", "uncategorized"),
                            author=c.get("author", ""),
                            install_command=c.get("installCommand", ""),
                            preview_url=c.get("previewUrl", ""),
                            dependencies=c.get("dependencies", []),
                            tags=c.get("tags", []),
                        )
                        for c in data
                        if c.get("name")
                    ]
        except Exception as exc:
            self._degraded_reason = f"remote catalog unavailable: {exc}"

    def _component_to_dict(self, c: Component21st) -> dict[str, Any]:
        return {
            "name": c.name,
            "category": c.category,
            "author": c.author,
            "install_command": c.install_command,
            "preview_url": c.preview_url,
            "dependencies": c.dependencies,
            "tags": c.tags,
        }

    def search_components(
        self,
        query: str = "",
        category: str = "",
        tag: str = "",
        limit: int = 10,
    ) -> dict[str, Any]:
        query_lower = query.lower()
        results: list[Component21st] = []
        for c in self._components:
            matches = (
                (not query or query_lower in c.name.lower() or any(query_lower in t.lower() for t in c.tags))
                and (not category or category.lower() in c.category.lower())
                and (not tag or any(tag.lower() in t.lower() for t in c.tags))
            )
            if matches:
                results.append(c)

        return {
            "status": "success" if results else "empty",
            "is_error": False,
            "degraded": bool(self._degraded_reason),
            "degraded_reason": self._degraded_reason,
            "count": len(results),
            "components": [self._component_to_dict(c) for c in results[:limit]],
        }

    def get_component_details(self, name: str) -> dict[str, Any]:
        for c in self._components:
            if c.name.lower() == name.lower() or c.name.lower().endswith(f"/{name.lower()}"):
                return {
                    "status": "success",
                    "is_error": False,
                    "component": self._component_to_dict(c),
                }
        return {
            "status": "not_found",
            "is_error": True,
            "message": f"Component '{name}' not found in 21st.dev catalog",
        }

    def plan_install(self, names: list[str]) -> dict[str, Any]:
        plan: list[dict[str, Any]] = []
        missing: list[str] = []
        all_deps: set[str] = set()
        for name in names:
            details = self.get_component_details(name)
            if details["is_error"]:
                missing.append(name)
                continue
            c = details["component"]
            plan.append(c)
            for dep in c.get("dependencies", []):
                if not re.match(r"^react$|^next$|^tailwindcss$", dep, re.IGNORECASE):
                    all_deps.add(dep)

        result: dict[str, Any] = {
            "status": "success" if plan else "error",
            "is_error": bool(missing),
            "install_steps": [c["install_command"] for c in plan if c.get("install_command")],
            "dependencies": sorted(all_deps),
            "missing": missing,
            "components": plan,
        }
        if missing:
            result["message"] = f"Components not found: {', '.join(missing)}"
        return result

    def check_stack_compatibility(
        self,
        names: list[str],
        framework: str = "nextjs",
        tailwind: bool = True,
    ) -> dict[str, Any]:
        issues: list[dict[str, Any]] = []
        compatible: list[str] = []
        for name in names:
            details = self.get_component_details(name)
            if details["is_error"]:
                issues.append({"component": name, "issue": "not found in catalog"})
                continue
            c = details["component"]
            deps = [d.lower() for d in c.get("dependencies", [])]
            if not tailwind and any("tailwind" in d for d in deps):
                issues.append({"component": c["name"], "issue": "requires Tailwind"})
            if framework.lower() not in ("nextjs", "react"):
                issues.append({"component": c["name"], "issue": f"framework '{framework}' not verified"})
            if not issues or issues[-1]["component"] != c["name"]:
                compatible.append(c["name"])

        return {
            "status": "success",
            "is_error": False,
            "framework": framework,
            "tailwind": tailwind,
            "compatible": compatible,
            "issues": issues,
            "ok": not issues,
        }

    async def ping(self) -> bool:
        return True
