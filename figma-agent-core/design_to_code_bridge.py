"""Unified Design-to-Code bridge.

Translates a Figma document into three coordinated artifacts:
1. Design tokens (colors, typography, spacing, effects) as DTCG-compatible JSON.
2. Layout data — autolayout hierarchy mapped to Flexbox behavior.
3. Component tree — strict JSON schema describing React/Tailwind component relationships.

This module orchestrates existing extractors so that downstream agents receive a
complete technical blueprint instead of a flat picture.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


def _import_module(name: str, path: Path) -> Any:
    import importlib.util
    import sys

    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, str(path))
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _load_design_tokens() -> Any:
    return _import_module("design_tokens", Path(__file__).with_name("design_tokens.py"))


def _load_layout_engine() -> Any:
    return _import_module("layout_engine", Path(__file__).with_name("layout_engine.py"))


def _load_component_extractor() -> Any:
    return _import_module("component_extractor", Path(__file__).with_name("component_extractor.py"))


def _load_analyzer() -> Any:
    return _import_module("analyzer", Path(__file__).with_name("analyzer.py"))


@dataclass
class DesignTokenOutput:
    colors: dict[str, Any] = field(default_factory=dict)
    typography: dict[str, Any] = field(default_factory=dict)
    spacing: dict[str, Any] = field(default_factory=dict)
    effects: dict[str, Any] = field(default_factory=dict)
    raw_registry: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "colors": self.colors,
            "typography": self.typography,
            "spacing": self.spacing,
            "effects": self.effects,
            "raw_registry": self.raw_registry,
        }

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, ensure_ascii=False)


@dataclass
class LayoutNode:
    id: str
    name: str
    semantic_name: str
    type: str
    layout_mode: str | None
    flex_direction: str | None
    justify_content: str | None
    align_items: str | None
    gap_px: float | None
    padding: dict[str, float] = field(default_factory=dict)
    bounding_box: dict[str, float | None] = field(default_factory=dict)
    resize_constraints: dict[str, str | None] = field(default_factory=dict)
    children: list["LayoutNode"] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "semantic_name": self.semantic_name,
            "type": self.type,
            "layout_mode": self.layout_mode,
            "flex_direction": self.flex_direction,
            "justify_content": self.justify_content,
            "align_items": self.align_items,
            "gap_px": self.gap_px,
            "padding": self.padding,
            "bounding_box": self.bounding_box,
            "resize_constraints": self.resize_constraints,
            "children": [c.to_dict() for c in self.children],
        }


@dataclass
class LayoutDataOutput:
    root: LayoutNode | None = None
    node_count: int = 0
    autolayout_count: int = 0
    text_count: int = 0
    asset_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "root": self.root.to_dict() if self.root else None,
            "node_count": self.node_count,
            "autolayout_count": self.autolayout_count,
            "text_count": self.text_count,
            "asset_count": self.asset_count,
        }

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, ensure_ascii=False)


@dataclass
class ComponentNode:
    id: str
    name: str
    react_component: str | None
    import_path: str | None
    props_schema: dict[str, Any] = field(default_factory=dict)
    children: list["ComponentNode"] = field(default_factory=list)
    tailwind_classes: list[str] = field(default_factory=list)
    inline_styles: dict[str, str] = field(default_factory=dict)
    data_binding: dict[str, Any] | None = None
    semantic_tag: str = "div"
    text_content: str | None = None
    asset_src: str | None = None

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "id": self.id,
            "name": self.name,
            "semantic_tag": self.semantic_tag,
            "react_component": self.react_component,
            "import_path": self.import_path,
            "props_schema": self.props_schema,
            "children": [c.to_dict() for c in self.children],
            "tailwind_classes": self.tailwind_classes,
            "inline_styles": self.inline_styles,
        }
        if self.data_binding is not None:
            result["data_binding"] = self.data_binding
        if self.text_content is not None:
            result["text_content"] = self.text_content
        if self.asset_src is not None:
            result["asset_src"] = self.asset_src
        return result


@dataclass
class ComponentTreeOutput:
    root: ComponentNode | None = None
    components: list[dict[str, Any]] = field(default_factory=list)
    page_component: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "root": self.root.to_dict() if self.root else None,
            "components": self.components,
            "page_component": self.page_component,
        }

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, ensure_ascii=False)


@dataclass
class DesignToCodeResult:
    tokens: DesignTokenOutput
    layout: LayoutDataOutput
    component_tree: ComponentTreeOutput
    summary: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "tokens": self.tokens.to_dict(),
            "layout": self.layout.to_dict(),
            "component_tree": self.component_tree.to_dict(),
            "summary": self.summary,
        }

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, ensure_ascii=False)


class DesignToCodeBridge:
    """Orchestrate token extraction, layout analysis, and component tree generation."""

    def __init__(self, workspace_root: str = "."):
        self.workspace_root = Path(workspace_root).resolve()

    def process(self, figma_document: dict[str, Any]) -> DesignToCodeResult:
        tokens = self._extract_tokens(figma_document)
        layout = self._extract_layout(figma_document)
        component_tree = self._build_component_tree(figma_document, tokens)
        summary = {
            "color_tokens": len(tokens.colors),
            "typography_tokens": len(tokens.typography),
            "layout_nodes": layout.node_count,
            "autolayout_nodes": layout.autolayout_count,
            "extracted_components": len(component_tree.components),
            "text_nodes": layout.text_count,
            "asset_nodes": layout.asset_count,
        }
        return DesignToCodeResult(
            tokens=tokens,
            layout=layout,
            component_tree=component_tree,
            summary=summary,
        )

    def _extract_tokens(self, figma_document: dict[str, Any]) -> DesignTokenOutput:
        design_tokens_mod = _load_design_tokens()
        extractor = design_tokens_mod.FigmaTokenExtractor(figma_document)
        registry = extractor.extract()

        colors: dict[str, Any] = {}
        for name, token in registry.colors.items():
            colors[name] = {
                "$value": token.hex,
                "$type": "color",
                "rgb": token.rgb,
                "css_var": token.css_var,
                "source": token.source,
                "contexts": token.contexts,
            }

        typography: dict[str, Any] = {
            "fonts": {family: f"var(--font-{token})" for family, token in registry.fonts.items()},
            "font_sizes": {str(px): name for px, name in registry.font_sizes.items()},
            "font_weights": {str(w): name for w, name in registry.font_weights.items()},
            "line_heights": {str(lh): name for lh, name in registry.line_heights.items()},
        }

        spacing: dict[str, Any] = {}
        effects: dict[str, Any] = {}

        raw_registry = registry.to_dict()

        return DesignTokenOutput(
            colors=colors,
            typography=typography,
            spacing=spacing,
            effects=effects,
            raw_registry=raw_registry,
        )

    def _extract_layout(self, figma_document: dict[str, Any]) -> LayoutDataOutput:
        analyzer_mod = _load_analyzer()

        def _justify_map(primary: str | None) -> str | None:
            return {
                "MIN": "flex-start",
                "CENTER": "center",
                "MAX": "flex-end",
                "SPACE_BETWEEN": "space-between",
            }.get(primary or "")

        def _items_map(counter: str | None) -> str | None:
            return {
                "MIN": "flex-start",
                "CENTER": "center",
                "MAX": "flex-end",
                "BASELINE": "baseline",
                "STRETCH": "stretch",
                "SPACE_BETWEEN": "space-between",
            }.get(counter or "")

        def _build_layout_node(node: dict[str, Any]) -> LayoutNode | None:
            if not isinstance(node, dict) or not node.get("visible", True):
                return None

            node_id = node.get("id", "")
            name = node.get("name", "")
            node_type = node.get("type", "")
            layout_mode = node.get("layoutMode")
            box = node.get("box") or node.get("absoluteBoundingBox") or {}

            semantic_name = analyzer_mod.infer_semantic_name(node)

            flex_direction = None
            if layout_mode == "VERTICAL":
                flex_direction = "column"
            elif layout_mode == "HORIZONTAL":
                flex_direction = "row"

            justify_content = _justify_map(node.get("primaryAxisAlignItems"))
            align_items = _items_map(node.get("counterAxisAlignItems"))
            gap_px = node.get("itemSpacing")
            if gap_px is not None:
                try:
                    gap_px = float(gap_px)
                except Exception:
                    gap_px = None

            padding = {
                "top": float(node.get("paddingTop", 0) or 0),
                "right": float(node.get("paddingRight", 0) or 0),
                "bottom": float(node.get("paddingBottom", 0) or 0),
                "left": float(node.get("paddingLeft", 0) or 0),
            }

            constraints = node.get("constraints") or {}
            resize_constraints = {
                "horizontal": constraints.get("horizontal"),
                "vertical": constraints.get("vertical"),
            }

            children: list[LayoutNode] = []
            for child in node.get("children", []):
                built = _build_layout_node(child)
                if built:
                    children.append(built)

            return LayoutNode(
                id=node_id,
                name=name,
                semantic_name=semantic_name,
                type=node_type,
                layout_mode=layout_mode,
                flex_direction=flex_direction,
                justify_content=justify_content,
                align_items=align_items,
                gap_px=gap_px,
                padding=padding,
                bounding_box={
                    "x": box.get("x"),
                    "y": box.get("y"),
                    "width": box.get("width"),
                    "height": box.get("height"),
                },
                resize_constraints=resize_constraints,
                children=children,
            )

        root = _build_layout_node(figma_document)
        stats = self._collect_layout_stats(root)
        return LayoutDataOutput(
            root=root,
            node_count=stats["nodes"],
            autolayout_count=stats["autolayout"],
            text_count=stats["texts"],
            asset_count=stats["assets"],
        )

    def _collect_layout_stats(self, node: LayoutNode | None) -> dict[str, int]:
        if node is None:
            return {"nodes": 0, "autolayout": 0, "texts": 0, "assets": 0}
        stats: dict[str, int] = {"nodes": 1, "autolayout": 0, "texts": 0, "assets": 0}
        if node.layout_mode:
            stats["autolayout"] += 1
        if node.type == "TEXT":
            stats["texts"] += 1
        if node.type in ("IMAGE", "VECTOR"):
            stats["assets"] += 1
        for child in node.children:
            child_stats = self._collect_layout_stats(child)
            for k in stats:
                stats[k] += child_stats[k]
        return stats

    def _build_component_tree(
        self, figma_document: dict[str, Any], tokens: DesignTokenOutput
    ) -> ComponentTreeOutput:
        layout_mod = _load_layout_engine()
        extractor_mod = _load_component_extractor()
        analyzer_mod = _load_analyzer()

        config: dict[str, Any] = {
            "tokens": tokens.raw_registry,
            "use_arbitrary_sizes": True,
        }

        # Convert the entire document to Tailwind AST.
        layout_result = layout_mod.convert_figma_node(figma_document, config=config)
        ast_root = layout_result.root.to_dict()

        # Extract reusable components from the AST.
        extractor = extractor_mod.ComponentExtractor(
            output_dir=str(self.workspace_root / "src" / "app" / "components"),
            root_dir=str(self.workspace_root),
        )
        page_ast, extracted_components = extractor.extract({"root": ast_root})
        page_root = page_ast.get("root", ast_root)

        components: list[dict[str, Any]] = []
        for comp in extracted_components:
            components.append({
                "name": comp.name,
                "file_path": str(comp.file_path),
                "figma_id": comp.node.get("figma_id"),
                "figma_name": comp.node.get("figma_name"),
                "imports": comp.imports,
            })

        def _build_component_node(node: dict[str, Any]) -> ComponentNode:
            node_id = node.get("figma_id") or node.get("id") or ""
            name = node.get("figma_name") or node.get("name") or ""
            semantic_name = analyzer_mod.infer_semantic_name(node, fallback=name or "Component")
            semantic_tag = node.get("tag", "div")
            react_component = node.get("component_name") or node.get("component_ref")
            import_path = node.get("component_path")

            props_schema: dict[str, Any] = {}
            for k, v in (node.get("variant_props") or {}).items():
                props_schema[k] = {"type": "string", "default": v}

            children = [
                _build_component_node(child)
                for child in node.get("children", [])
            ]

            return ComponentNode(
                id=node_id,
                name=name or semantic_name,
                react_component=react_component,
                import_path=import_path,
                props_schema=props_schema,
                children=children,
                tailwind_classes=node.get("classes", []),
                inline_styles=node.get("inline_styles", {}),
                data_binding=node.get("data_binding"),
                semantic_tag=semantic_tag,
                text_content=node.get("text"),
                asset_src=node.get("src"),
            )

        root_component = _build_component_node(page_root)
        page_component = {
            "id": root_component.id,
            "name": root_component.name,
            "semantic_tag": root_component.semantic_tag,
            "tailwind_classes": root_component.tailwind_classes,
            "children_count": len(root_component.children),
        }

        return ComponentTreeOutput(
            root=root_component,
            components=components,
            page_component=page_component,
        )

    def write_artifacts(
        self,
        result: DesignToCodeResult,
        target_dir: Path | str,
    ) -> dict[str, Path]:
        target = Path(target_dir).resolve()
        target.mkdir(parents=True, exist_ok=True)

        tokens_path = target / "design_tokens.json"
        layout_path = target / "layout_data.json"
        tree_path = target / "component_tree.json"
        summary_path = target / "design_to_code_summary.json"

        tokens_path.write_text(result.tokens.to_json(), encoding="utf-8")
        layout_path.write_text(result.layout.to_json(), encoding="utf-8")
        tree_path.write_text(result.component_tree.to_json(), encoding="utf-8")
        summary_path.write_text(json.dumps(result.summary, indent=2, ensure_ascii=False), encoding="utf-8")

        return {
            "design_tokens": tokens_path,
            "layout_data": layout_path,
            "component_tree": tree_path,
            "summary": summary_path,
        }


def process_figma_document(figma_document: dict[str, Any], workspace_root: str = ".") -> DesignToCodeResult:
    """High-level entry point for agent/runtime usage."""
    bridge = DesignToCodeBridge(workspace_root=workspace_root)
    return bridge.process(figma_document)
