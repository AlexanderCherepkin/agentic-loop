import json
import re
import argparse
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


_SPACING_CACHE: Dict[int, str] = {}


def _spacing_class(value: float) -> str:
    """Возвращает Tailwind-класс для spacing-значения в px."""
    if value < 0:
        return f"-{_spacing_class(abs(value))}"
    rounded = int(round(value))
    if rounded in _SPACING_CACHE:
        return _SPACING_CACHE[rounded]
    if rounded == 0:
        return "0"
    scale = {
        1: "px",
        2: "0.5",
        4: "1",
        6: "1.5",
        8: "2",
        10: "2.5",
        12: "3",
        14: "3.5",
        16: "4",
        20: "5",
        24: "6",
        28: "7",
        32: "8",
        36: "9",
        40: "10",
        44: "11",
        48: "12",
        56: "14",
        64: "16",
        80: "20",
        96: "24",
        112: "28",
        128: "32",
        144: "36",
        160: "40",
        176: "44",
        192: "48",
        208: "52",
        224: "56",
        240: "60",
        256: "64",
        288: "72",
        320: "80",
        384: "96",
    }
    if rounded in scale:
        _SPACING_CACHE[rounded] = scale[rounded]
        return scale[rounded]
    arbitrary = f"{rounded}px"
    _SPACING_CACHE[rounded] = arbitrary
    return arbitrary


def _arbitrary(class_base: str, value: Any, unit: str = "px") -> str:
    """Собирает Tailwind-класс с произвольным значением."""
    return f"{class_base}-[{value}{unit}]"


def _hex_to_tailwind(hex_color: Optional[str]) -> Optional[str]:
    if not hex_color:
        return None
    hex_color = hex_color.lower().strip()
    if not re.match(r"^#[0-9a-f]{3,8}$", hex_color):
        return None
    palette = {
        "#000000": "black",
        "#ffffff": "white",
        "#ef4444": "red-500",
        "#f97316": "orange-500",
        "#eab308": "yellow-500",
        "#22c55e": "green-500",
        "#06b6d4": "cyan-500",
        "#3b82f6": "blue-500",
        "#6366f1": "indigo-500",
        "#a855f7": "purple-500",
        "#ec4899": "pink-500",
        "#f43f5e": "rose-500",
        "#94a3b8": "slate-400",
        "#64748b": "slate-500",
        "#475569": "slate-600",
    }
    return palette.get(hex_color, hex_color)


def _class_for_color(prefix: str, hex_color: Optional[str]) -> Optional[str]:
    mapped = _hex_to_tailwind(hex_color)
    if not mapped:
        return None
    if mapped.startswith("#"):
        return _arbitrary(prefix, mapped, unit="")
    return f"{prefix}-{mapped}"


def _px(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _safe_name(name: Any) -> str:
    return re.sub(r"[^\w\-]", "_", str(name or "unnamed")).strip("_") or "unnamed"


@dataclass
class TailwindNode:
    tag: str = "div"
    classes: List[str] = field(default_factory=list)
    inline_styles: Dict[str, str] = field(default_factory=dict)
    text: Optional[str] = None
    src: Optional[str] = None
    alt: Optional[str] = None
    children: List["TailwindNode"] = field(default_factory=list)
    figma_id: Optional[str] = None
    figma_name: Optional[str] = None

    def add_class(self, *classes: str) -> None:
        for cls in classes:
            if cls and cls not in self.classes:
                self.classes.append(cls)

    def to_dict(self) -> Dict[str, Any]:
        result: Dict[str, Any] = {
            "tag": self.tag,
            "classes": self.classes,
        }
        if self.inline_styles:
            result["inline_styles"] = self.inline_styles
        if self.text is not None:
            result["text"] = self.text
        if self.src is not None:
            result["src"] = self.src
        if self.alt is not None:
            result["alt"] = self.alt
        if self.children:
            result["children"] = [c.to_dict() for c in self.children]
        if self.figma_id is not None:
            result["figma_id"] = self.figma_id
        if self.figma_name is not None:
            result["figma_name"] = self.figma_name
        return result


@dataclass
class LayoutResult:
    root: TailwindNode
    node_count: int = 0
    text_node_count: int = 0
    asset_count: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "root": self.root.to_dict(),
            "node_count": self.node_count,
            "text_node_count": self.text_node_count,
            "asset_count": self.asset_count,
        }


class FigmaLayoutEngine:
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = config or {}
        self._use_arbitrary_sizes = self.config.get("use_arbitrary_sizes", True)

    def convert(self, node: Dict[str, Any]) -> LayoutResult:
        root = self._convert_node(node, parent_box=node.get("box"))
        stats = self._collect_stats(root)
        return LayoutResult(
            root=root,
            node_count=stats["nodes"],
            text_node_count=stats["texts"],
            asset_count=stats["assets"],
        )

    def _collect_stats(self, node: TailwindNode) -> Dict[str, int]:
        stats = {"nodes": 1, "texts": 0, "assets": 0}
        if node.text is not None:
            stats["texts"] += 1
        if node.src is not None:
            stats["assets"] += 1
        for child in node.children:
            child_stats = self._collect_stats(child)
            stats["nodes"] += child_stats["nodes"]
            stats["texts"] += child_stats["texts"]
            stats["assets"] += child_stats["assets"]
        return stats

    def _convert_node(
        self,
        node: Dict[str, Any],
        parent_box: Optional[Dict[str, Any]] = None,
        depth: int = 0,
    ) -> Optional[TailwindNode]:
        if not isinstance(node, dict) or not node.get("visible", True):
            return None

        node_type = node.get("type", "UNKNOWN")
        name = _safe_name(node.get("name"))

        if node_type == "TEXT":
            return self._convert_text(node)

        if node.get("isAsset") or node_type in ("IMAGE", "VECTOR"):
            return self._convert_asset(node)

        if node_type in ("RECTANGLE", "ELLIPSE"):
            return self._convert_shape(node)

        tw_node = TailwindNode(
            tag=self._semantic_tag(node, depth),
            figma_id=node.get("id"),
            figma_name=name,
        )

        box = node.get("box")
        self._apply_size(tw_node, box)
        self._apply_layout(tw_node, node)
        self._apply_position(tw_node, node, parent_box)
        self._apply_fills(tw_node, node)
        self._apply_strokes(tw_node, node)
        self._apply_effects(tw_node, node)
        self._apply_radius(tw_node, node)

        for child in node.get("children", []):
            converted = self._convert_node(child, parent_box=box, depth=depth + 1)
            if converted:
                tw_node.children.append(converted)

        return tw_node

    def _semantic_tag(self, node: Dict[str, Any], depth: int) -> str:
        name = (node.get("name") or "").lower()
        if depth == 0:
            return "section"
        if "button" in name or node.get("type") == "COMPONENT":
            return "button"
        if "image" in name or node.get("isAsset"):
            return "div"
        if "hero" in name or "header" in name or "nav" in name:
            return "header" if depth <= 1 else "div"
        if "footer" in name:
            return "footer"
        if "article" in name or "card" in name:
            return "article"
        return "div"

    def _convert_text(self, node: Dict[str, Any]) -> TailwindNode:
        tw_node = TailwindNode(
            tag=self._text_tag(node),
            text=node.get("characters", ""),
            figma_id=node.get("id"),
            figma_name=_safe_name(node.get("name")),
        )
        box = node.get("box")
        self._apply_size(tw_node, box)
        style = node.get("style", {})
        self._apply_text_style(tw_node, style)
        self._apply_position(tw_node, node, None)
        return tw_node

    def _text_tag(self, node: Dict[str, Any]) -> str:
        name = (node.get("name") or "").lower()
        if "h1" in name or "title" in name or "headline" in name:
            return "h1"
        if "h2" in name:
            return "h2"
        if "h3" in name:
            return "h3"
        if "button" in name or node.get("type") == "COMPONENT":
            return "span"
        return "p"

    def _convert_asset(self, node: Dict[str, Any]) -> TailwindNode:
        tw_node = TailwindNode(
            tag="img",
            src=node.get("publicPath"),
            alt=_safe_name(node.get("name")),
            figma_id=node.get("id"),
            figma_name=_safe_name(node.get("name")),
        )
        self._apply_size(tw_node, node.get("box"))
        self._apply_position(tw_node, node, None)
        return tw_node

    def _convert_shape(self, node: Dict[str, Any]) -> TailwindNode:
        tw_node = TailwindNode(
            tag="div",
            figma_id=node.get("id"),
            figma_name=_safe_name(node.get("name")),
        )
        self._apply_size(tw_node, node.get("box"))
        self._apply_position(tw_node, node, None)
        self._apply_fills(tw_node, node)
        self._apply_strokes(tw_node, node)
        self._apply_effects(tw_node, node)
        self._apply_radius(tw_node, node)
        return tw_node

    def _apply_size(self, tw_node: TailwindNode, box: Optional[Dict[str, Any]]) -> None:
        if not box:
            return
        width = _px(box.get("width"))
        height = _px(box.get("height"))
        if width is not None and width > 0:
            tw_node.add_class(_arbitrary("w", int(round(width))))
        if height is not None and height > 0:
            tw_node.add_class(_arbitrary("h", int(round(height))))

    def _apply_layout(self, tw_node: TailwindNode, node: Dict[str, Any]) -> None:
        layout_mode = node.get("layoutMode")
        if not layout_mode:
            return

        tw_node.add_class("flex")
        if layout_mode == "VERTICAL":
            tw_node.add_class("flex-col")
        else:
            tw_node.add_class("flex-row")

        spacing = _px(node.get("itemSpacing"))
        if spacing is not None and spacing > 0:
            tw_node.add_class(_arbitrary("gap", int(round(spacing))))
        elif spacing is not None and spacing == 0:
            tw_node.add_class("gap-0")

        primary = node.get("primaryAxisAlignItems")
        counter = node.get("counterAxisAlignItems")

        justify_map = {
            "MIN": "justify-start",
            "CENTER": "justify-center",
            "MAX": "justify-end",
            "SPACE_BETWEEN": "justify-between",
        }
        items_map = {
            "MIN": "items-start",
            "CENTER": "items-center",
            "MAX": "items-end",
            "BASELINE": "items-baseline",
        }

        if primary in justify_map:
            tw_node.add_class(justify_map[primary])
        if counter in items_map:
            tw_node.add_class(items_map[counter])

        self._apply_padding(tw_node, node)

    def _apply_padding(self, tw_node: TailwindNode, node: Dict[str, Any]) -> None:
        top = _px(node.get("paddingTop", 0)) or 0
        right = _px(node.get("paddingRight", 0)) or 0
        bottom = _px(node.get("paddingBottom", 0)) or 0
        left = _px(node.get("paddingLeft", 0)) or 0

        if top == right == bottom == left:
            if top > 0:
                tw_node.add_class(_arbitrary("p", int(round(top))))
            return

        if top == bottom and left == right:
            if top > 0:
                tw_node.add_class(_arbitrary("py", int(round(top))))
            if left > 0:
                tw_node.add_class(_arbitrary("px", int(round(left))))
            return

        if top > 0:
            tw_node.add_class(_arbitrary("pt", int(round(top))))
        if right > 0:
            tw_node.add_class(_arbitrary("pr", int(round(right))))
        if bottom > 0:
            tw_node.add_class(_arbitrary("pb", int(round(bottom))))
        if left > 0:
            tw_node.add_class(_arbitrary("pl", int(round(left))))

    def _apply_position(
        self,
        tw_node: TailwindNode,
        node: Dict[str, Any],
        parent_box: Optional[Dict[str, Any]],
    ) -> None:
        if node.get("layoutMode"):
            return

        node_type = node.get("type")
        if node_type == "TEXT":
            return

        box = node.get("box")
        if not box or not parent_box:
            return

        parent_x = _px(parent_box.get("x")) or 0
        parent_y = _px(parent_box.get("y")) or 0
        x = _px(box.get("x")) or 0
        y = _px(box.get("y")) or 0

        rel_x = int(round(x - parent_x))
        rel_y = int(round(y - parent_y))

        tw_node.add_class("absolute")
        tw_node.inline_styles["left"] = f"{rel_x}px"
        tw_node.inline_styles["top"] = f"{rel_y}px"

    def _apply_fills(self, tw_node: TailwindNode, node: Dict[str, Any]) -> None:
        fills = node.get("fills") or []
        for fill in fills:
            fill_type = fill.get("type")
            if fill_type == "SOLID":
                hex_color = fill.get("hex")
                cls = _class_for_color("bg", hex_color)
                if cls:
                    tw_node.add_class(cls)
                opacity = fill.get("opacity")
                if opacity is not None and opacity < 1.0:
                    tw_node.inline_styles["opacity"] = str(opacity)
            elif fill_type == "GRADIENT_LINEAR":
                stops = fill.get("stops", [])
                if stops:
                    gradient = self._build_gradient(stops)
                    tw_node.inline_styles["background"] = gradient
            elif fill_type == "IMAGE":
                tw_node.inline_styles["background-image"] = f"url('{fill.get('imageRef')}')"
                tw_node.inline_styles["background-size"] = "cover"

    def _build_gradient(self, stops: List[Dict[str, Any]]) -> str:
        parts = []
        for stop in stops:
            color = stop.get("hex") or stop.get("rgb", "transparent")
            pos = stop.get("position", 0)
            parts.append(f"{color} {int(round(pos * 100))}%")
        return f"linear-gradient(180deg, {', '.join(parts)})"

    def _apply_strokes(self, tw_node: TailwindNode, node: Dict[str, Any]) -> None:
        strokes = node.get("strokes") or []
        if not strokes:
            return
        for stroke in strokes:
            if stroke.get("type") == "SOLID":
                cls = _class_for_color("border", stroke.get("hex"))
                if cls:
                    tw_node.add_class(cls)
                width = _px(node.get("strokeWeight", 1))
                if width is not None and width > 0:
                    tw_node.add_class(_arbitrary("border", int(round(width))))
                break

    def _apply_effects(self, tw_node: TailwindNode, node: Dict[str, Any]) -> None:
        effects = node.get("effects") or []
        for effect in effects:
            e_type = effect.get("type")
            if e_type in ("DROP_SHADOW", "INNER_SHADOW"):
                color = effect.get("hex") or effect.get("rgb", "rgba(0,0,0,0.25)")
                offset = effect.get("offset", {"x": 0, "y": 0})
                radius = effect.get("radius", 0)
                x = int(round(offset.get("x", 0)))
                y = int(round(offset.get("y", 0)))
                inset = "inset " if e_type == "INNER_SHADOW" else ""
                tw_node.inline_styles["box-shadow"] = (
                    f"{inset}{x}px {y}px {int(round(radius))}px {color}"
                )
            elif e_type == "LAYER_BLUR":
                radius = effect.get("radius", 0)
                tw_node.inline_styles["filter"] = f"blur({int(round(radius))}px)"

    def _apply_radius(self, tw_node: TailwindNode, node: Dict[str, Any]) -> None:
        radius = _px(node.get("cornerRadius"))
        if radius is None or radius <= 0:
            return
        rounded = int(round(radius))
        scale = {
            2: "rounded-sm",
            4: "rounded",
            6: "rounded-md",
            8: "rounded-lg",
            12: "rounded-xl",
            16: "rounded-2xl",
            24: "rounded-3xl",
            9999: "rounded-full",
        }
        if rounded in scale:
            tw_node.add_class(scale[rounded])
        else:
            tw_node.add_class(_arbitrary("rounded", rounded))

    def _apply_text_style(self, tw_node: TailwindNode, style: Dict[str, Any]) -> None:
        font_size = _px(style.get("fontSize"))
        if font_size is not None and font_size > 0:
            tw_node.add_class(_arbitrary("text", int(round(font_size))))

        weight = style.get("fontWeight")
        if weight is not None:
            tw_node.add_class(_arbitrary("font", weight, unit=""))

        family = style.get("fontFamily")
        if family:
            tw_node.add_class(_arbitrary("font", family.replace(" ", "_"), unit=""))

        align = style.get("textAlignHorizontal")
        align_map = {
            "LEFT": "text-left",
            "CENTER": "text-center",
            "RIGHT": "text-right",
            "JUSTIFIED": "text-justify",
        }
        if align in align_map:
            tw_node.add_class(align_map[align])

        line_height_px = _px(style.get("lineHeightPx"))
        if line_height_px is not None and font_size:
            ratio = round(line_height_px / font_size, 3)
            tw_node.add_class(_arbitrary("leading", ratio, unit=""))

        letter_spacing = _px(style.get("letterSpacing"))
        if letter_spacing is not None:
            tw_node.add_class(_arbitrary("tracking", int(round(letter_spacing))))

        fills = style.get("fills") or []
        for fill in fills:
            if fill.get("type") == "SOLID":
                cls = _class_for_color("text", fill.get("hex"))
                if cls:
                    tw_node.add_class(cls)
                break


def convert_figma_node(node: Dict[str, Any], config: Optional[Dict[str, Any]] = None) -> LayoutResult:
    engine = FigmaLayoutEngine(config)
    return engine.convert(node)


def main():
    parser = argparse.ArgumentParser(description="Layout Engine: Figma JSON → Tailwind AST")
    parser.add_argument(
        "--file",
        default="figma_node.json",
        help="Путь к JSON-файлу Figma-структуры.",
    )
    parser.add_argument(
        "--node-id",
        default=None,
        help="ID конкретной ноды (пример: 662:808).",
    )
    parser.add_argument(
        "--output",
        default="layout_ast.json",
        help="Путь для сохранения AST.",
    )
    args = parser.parse_args()

    import analyzer

    data = analyzer.load_figma_json(args.file)
    if not data:
        print(f"[ERROR] Could not load {args.file}")
        return

    node = data
    if args.node_id:
        target = analyzer.find_node_by_id(data, args.node_id)
        if not target:
            print(f"[ERROR] Node {args.node_id} not found in {args.file}")
            return
        node = target

    result = convert_figma_node(node)
    output_path = Path(args.output)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(result.to_dict(), f, ensure_ascii=False, indent=2)
    print(f"[LAYOUT] AST saved to {output_path}")


if __name__ == "__main__":
    main()
