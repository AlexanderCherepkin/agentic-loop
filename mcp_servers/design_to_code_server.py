"""Design-to-Code MCP bridge.

Exposes `figma-agent-core/design_to_code_bridge.py` as an MCP category
`design_to_code`. Provides in-process translation of a Figma JSON document into
design tokens, autolayout/Flexbox layout data, and a React/Tailwind component tree.

The server degrades gracefully if `figma-agent-core/design_to_code_bridge.py` is
missing or if its optional siblings fail to load.
"""

from __future__ import annotations

import importlib.util
import json
import sys
import traceback
from pathlib import Path
from typing import Any

from .base import MCPServer


class DesignToCodeMCPServer(MCPServer):
    """MCP server wrapping the Design-to-Code bridge."""

    def __init__(self, workspace_root: str = "."):
        super().__init__(name="design_to_code", version="1.0.0")
        self.workspace = Path(workspace_root).resolve()
        self._core_dir = self.workspace / "figma-agent-core"
        self._degraded_reason: str | None = None
        self._bridge_module: Any | None = None
        self._register_tools()
        self._initialized = True

    def _register_tools(self) -> None:
        s = self._schema
        self.register(
            "process_figma_document",
            "Run the full Design-to-Code pipeline on a Figma JSON file",
            s({"figma_json_path": "string", "output_dir?": "string", "workspace_root?": "string"}),
            self.process_figma_document,
        )
        self.register(
            "extract_tokens",
            "Extract DTCG-compatible design tokens from a Figma JSON file",
            s({"figma_json_path": "string", "workspace_root?": "string"}),
            self.extract_tokens,
        )
        self.register(
            "extract_layout",
            "Extract autolayout/Flexbox layout data from a Figma JSON file",
            s({"figma_json_path": "string", "workspace_root?": "string"}),
            self.extract_layout,
        )
        self.register(
            "extract_component_tree",
            "Extract a React/Tailwind component tree from a Figma JSON file",
            s({"figma_json_path": "string", "workspace_root?": "string"}),
            self.extract_component_tree,
        )
        self.register(
            "write_design_to_code_artifacts",
            "Write a previously computed Design-to-Code result to JSON artifacts",
            s({"result_json": "string", "output_dir": "string"}),
            self.write_design_to_code_artifacts,
        )
        self.register(
            "check_bridge_available",
            "Check whether the Design-to-Code bridge can be loaded",
            s({}),
            self.check_bridge_available,
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

    def _load_bridge(self) -> Any:
        """Lazy-load the design_to_code_bridge module from figma-agent-core."""
        if self._bridge_module is not None:
            return self._bridge_module

        bridge_path = self._core_dir / "design_to_code_bridge.py"
        if not bridge_path.exists():
            self._degraded_reason = f"design_to_code_bridge not found at {bridge_path}"
            raise ImportError(self._degraded_reason)

        try:
            if "design_to_code_bridge" in sys.modules:
                mod = sys.modules["design_to_code_bridge"]
            else:
                spec = importlib.util.spec_from_file_location(
                    "design_to_code_bridge", str(bridge_path)
                )
                mod = importlib.util.module_from_spec(spec)
                sys.modules["design_to_code_bridge"] = mod
                spec.loader.exec_module(mod)
            self._bridge_module = mod
            return mod
        except Exception as exc:
            self._degraded_reason = f"failed to load design_to_code_bridge: {exc}"
            raise

    def _check_degraded(self) -> dict[str, Any] | None:
        if self._degraded_reason:
            return {
                "status": "degraded",
                "is_error": False,
                "degraded_reason": self._degraded_reason,
            }
        return None

    @staticmethod
    def _error_response(exc: Exception) -> dict[str, Any]:
        return {
            "status": "error",
            "is_error": True,
            "error": str(exc),
            "traceback": traceback.format_exc(),
        }

    def _read_figma_json(self, figma_json_path: str) -> dict[str, Any]:
        path = Path(figma_json_path).resolve()
        if not path.exists():
            raise FileNotFoundError(f"Figma JSON not found: {path}")
        return json.loads(path.read_text(encoding="utf-8"))

    def _run_bridge(self, figma_json_path: str, workspace_root: str) -> Any:
        mod = self._load_bridge()
        root = workspace_root if workspace_root else str(self.workspace)
        doc = self._read_figma_json(figma_json_path)
        bridge = mod.DesignToCodeBridge(workspace_root=root)
        return bridge.process(doc)

    def process_figma_document(
        self,
        figma_json_path: str,
        output_dir: str = "",
        workspace_root: str = "",
    ) -> dict[str, Any]:
        degraded = self._check_degraded()
        if degraded:
            return degraded

        try:
            result = self._run_bridge(figma_json_path, workspace_root)
            artifacts: dict[str, str] = {}
            if output_dir:
                out = Path(output_dir).resolve()
                out.mkdir(parents=True, exist_ok=True)
                mod = self._load_bridge()
                bridge = mod.DesignToCodeBridge(
                    workspace_root=workspace_root if workspace_root else str(self.workspace)
                )
                written = bridge.write_artifacts(result, out)
                artifacts = {k: str(v) for k, v in written.items()}

            return {
                "status": "success",
                "is_error": False,
                "tokens": result.tokens.to_dict(),
                "layout": result.layout.to_dict(),
                "component_tree": result.component_tree.to_dict(),
                "summary": result.summary,
                "artifacts": artifacts,
            }
        except Exception as exc:
            return self._error_response(exc)

    def extract_tokens(
        self, figma_json_path: str, workspace_root: str = ""
    ) -> dict[str, Any]:
        degraded = self._check_degraded()
        if degraded:
            return degraded

        try:
            result = self._run_bridge(figma_json_path, workspace_root)
            return {
                "status": "success",
                "is_error": False,
                "tokens": result.tokens.to_dict(),
                "summary": result.summary,
            }
        except Exception as exc:
            return self._error_response(exc)

    def extract_layout(
        self, figma_json_path: str, workspace_root: str = ""
    ) -> dict[str, Any]:
        degraded = self._check_degraded()
        if degraded:
            return degraded

        try:
            result = self._run_bridge(figma_json_path, workspace_root)
            return {
                "status": "success",
                "is_error": False,
                "layout": result.layout.to_dict(),
                "summary": result.summary,
            }
        except Exception as exc:
            return self._error_response(exc)

    def extract_component_tree(
        self, figma_json_path: str, workspace_root: str = ""
    ) -> dict[str, Any]:
        degraded = self._check_degraded()
        if degraded:
            return degraded

        try:
            result = self._run_bridge(figma_json_path, workspace_root)
            return {
                "status": "success",
                "is_error": False,
                "component_tree": result.component_tree.to_dict(),
                "summary": result.summary,
            }
        except Exception as exc:
            return self._error_response(exc)

    def write_design_to_code_artifacts(
        self, result_json: str, output_dir: str
    ) -> dict[str, Any]:
        degraded = self._check_degraded()
        if degraded:
            return degraded

        try:
            data = json.loads(result_json)
            target = Path(output_dir).resolve()
            target.mkdir(parents=True, exist_ok=True)

            artifact_map = {
                "tokens": "design_tokens.json",
                "layout": "layout_data.json",
                "component_tree": "component_tree.json",
                "summary": "design_to_code_summary.json",
            }
            artifacts: dict[str, str] = {}
            for key, filename in artifact_map.items():
                path = target / filename
                path.write_text(
                    json.dumps(data.get(key, {}), indent=2, ensure_ascii=False),
                    encoding="utf-8",
                )
                artifacts[key] = str(path)

            return {
                "status": "success",
                "is_error": False,
                "artifacts": artifacts,
            }
        except Exception as exc:
            return self._error_response(exc)

    def check_bridge_available(self) -> dict[str, Any]:
        try:
            self._load_bridge()
            return {
                "status": "success",
                "is_error": False,
                "available": True,
                "degraded_reason": None,
            }
        except Exception:
            return {
                "status": "degraded",
                "is_error": False,
                "available": False,
                "degraded_reason": self._degraded_reason,
            }

    async def ping(self) -> bool:
        return True
