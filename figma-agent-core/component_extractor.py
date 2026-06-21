import json
import os
import re
import argparse
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple
from dataclasses import dataclass, field


DEFAULT_COMPONENT_PATTERNS: List[str] = [
    "button",
    "card",
    "feature",
    "header",
    "footer",
    "nav",
    "hero",
    "pricing",
    "testimonial",
    "logo",
    "badge",
    "chip",
    "input",
    "form",
    "section",
    "cta",
    "faq",
    "stat",
    "step",
    "team",
    "review",
]

DEFAULT_COMPONENT_NAMES: List[str] = [
    "FeatureCard",
    "InfoCard",
    "PricingCard",
    "TestimonialCard",
    "StatCard",
    "StepCard",
    "TeamCard",
    "ReviewCard",
    "BenefitCard",
    "ValueProp",
]


@dataclass
class ExtractedComponent:
    name: str
    node: Dict[str, Any]
    file_path: Path
    imports: List[str] = field(default_factory=list)


def _to_pascal_case(name: str) -> str:
    name = name.strip()
    name = re.sub(r"[^\w\s_]+", " ", name)
    name = re.sub(r"[\s_]+", " ", name).strip()
    words = name.split(" ")
    result = "".join(word[:1].upper() + word[1:] for word in words if word)
    result = re.sub(r"[^A-Za-z0-9]+", "", result)
    if not result or not result[0].isalpha():
        result = "Figma" + result
    return result


def _sanitize_component_name(name: str) -> str:
    name = name.replace(".tsx", "").replace(".jsx", "").strip()
    if not name:
        raise ValueError("Component name cannot be empty.")
    if not re.match(r"^[A-Za-z][A-Za-z0-9_]*$", name):
        raise ValueError(
            f"Invalid component name: '{name}'. "
            "Use PascalCase alphanumeric name starting with a letter."
        )
    return name


def _pattern_base_name(node: Dict[str, Any], patterns: List[str]) -> Optional[str]:
    name = (node.get("figma_name") or "").lower()
    for pattern in patterns:
        if pattern.lower() in name:
            return _to_pascal_case(pattern)
    return None


def _validate_target_dir(target_dir: str, root_dir: str = ".") -> Path:
    abs_root = Path(root_dir).resolve()
    abs_target = Path(target_dir).resolve()
    common = os.path.commonpath([str(abs_root), str(abs_target)])
    if Path(common).resolve() != abs_root:
        raise ValueError(
            f"Path traversal detected: target_dir '{target_dir}' resolves outside root '{root_dir}'."
        )
    return abs_target


def _class_string(classes: List[str]) -> str:
    if not classes:
        return ""
    return " ".join(classes)


def _style_to_string(styles: Dict[str, str]) -> str:
    if not styles:
        return ""
    pairs = []
    for key, value in sorted(styles.items()):
        kebab = re.sub(r"([A-Z])", r"-\1", key).lower()
        pairs.append(f"{kebab}: {value}")
    return "; ".join(pairs)


def _render_inline_styles(styles: Dict[str, str]) -> str:
    if not styles:
        return ""
    style_str = _style_to_string(styles)
    return f' style={{{json.dumps(style_str)}}}'


def _safe_prop(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return str(value).lower()
    if isinstance(value, (int, float)):
        return str(value)
    return json.dumps(value, ensure_ascii=False)


def _node_to_tsx(node: Dict[str, Any], depth: int = 1) -> str:
    tag = node.get("tag", "div")
    classes = node.get("classes", [])
    class_attr = f' className="{_class_string(classes)}"' if classes else ""
    style_attr = _render_inline_styles(node.get("inline_styles", {}))

    text = node.get("text")
    src = node.get("src")
    alt = node.get("alt", "")

    inner_indent = " " * ((depth + 1) * 2)
    start_indent = " " * (depth * 2)

    extra_attrs = ""
    if tag == "img" and src:
        extra_attrs += f' src={_safe_prop(src)} alt={_safe_prop(alt)}'

    children = node.get("children", [])

    if node.get("component"):
        name = node.get("component_name", tag)
        props = node.get("props", {})
        props_str = ""
        if props:
            props_str = " " + " ".join(f'{k}={_safe_prop(v)}' for k, v in props.items())
        return f"{start_indent}<{name}{props_str} />"

    if children:
        rendered_children = "\n".join(_node_to_tsx(child, depth + 1) for child in children)
        return (
            f"{start_indent}<{tag}{class_attr}{style_attr}{extra_attrs}>\n"
            f"{rendered_children}\n"
            f"{start_indent}</{tag}>"
        )

    if text is not None:
        if tag in ("span", "p", "a", "label"):
            return f"{start_indent}<{tag}{class_attr}{style_attr}{extra_attrs}>{text}</{tag}>"
        return f"{start_indent}<{tag}{class_attr}{style_attr}{extra_attrs}>\n{inner_indent}{text}\n{start_indent}</{tag}>"

    if tag == "img":
        return f"{start_indent}<{tag}{class_attr}{style_attr}{extra_attrs} />"

    return f"{start_indent}<{tag}{class_attr}{style_attr}{extra_attrs} />"


def _collect_all_nodes(node: Dict[str, Any]) -> List[Dict[str, Any]]:
    results = [node]
    for child in node.get("children", []):
        results.extend(_collect_all_nodes(child))
    return results


def _detect_font_imports(node: Dict[str, Any]) -> List[str]:
    fonts: Set[str] = set()
    for n in _collect_all_nodes(node):
        for cls in n.get("classes", []):
            match = re.match(r"font-\[([^\]]+)\]", cls)
            if match:
                family = match.group(1).replace("_", " ")
                if family in (
                    "Inter", "Roboto", "Poppins", "Manrope", "Open Sans", "Lato", "Montserrat"
                ):
                    fonts.add(family.replace(" ", "+"))
    imports = []
    for font in sorted(fonts):
        imports.append(f'import {{ {font.replace("+", " ")} }} from "next/font/google"')
    return imports


def _signature(node: Dict[str, Any]) -> Tuple[Any, ...]:
    tag = node.get("tag", "div")
    classes = node.get("classes", [])
    token_classes = sorted([c for c in classes if "[" not in c])
    child_sigs = tuple(_signature(c) for c in node.get("children", []))
    has_text = 1 if node.get("text") is not None else 0
    has_image = 1 if node.get("src") is not None else 0
    return (tag, tuple(token_classes), child_sigs, has_text, has_image)


def _is_named_candidate(node: Dict[str, Any], patterns: List[str]) -> bool:
    name = (node.get("figma_name") or "").lower()
    if not name:
        return False
    for pattern in patterns:
        if pattern.lower() in name:
            return True
    return False


def _is_component_type(node: Dict[str, Any]) -> bool:
    return node.get("figma_type") in ("COMPONENT", "INSTANCE")


def _has_substance(node: Dict[str, Any]) -> bool:
    children = node.get("children", [])
    classes = node.get("classes", [])
    if node.get("src") is not None:
        return True
    if node.get("text") is not None and len(classes) > 1:
        return True
    if len(children) >= 2:
        return True
    if len(children) == 1:
        child = children[0]
        if child.get("children") and len(classes) > 0:
            return True
        if len(classes) > 1:
            return True
    return False


def _collect_substantial_nodes(
    node: Dict[str, Any],
    patterns: List[str],
    depth: int = 0,
    parent_is_candidate: bool = False,
) -> List[Tuple[Dict[str, Any], int]]:
    results: List[Tuple[Dict[str, Any], int]] = []
    is_candidate = False
    if depth > 0 and not parent_is_candidate:
        if _is_named_candidate(node, patterns) or _is_component_type(node) or _has_substance(node):
            is_candidate = True
    if is_candidate:
        results.append((node, depth))
        return results
    for child in node.get("children", []):
        results.extend(_collect_substantial_nodes(child, patterns, depth + 1, is_candidate))
    return results


def _name_for_duplicate(sig: Tuple[Any, ...], index: int) -> str:
    name = DEFAULT_COMPONENT_NAMES[index % len(DEFAULT_COMPONENT_NAMES)]
    quotient = index // len(DEFAULT_COMPONENT_NAMES)
    if quotient > 0:
        name = f"{name}{quotient}"
    return name


def _assign_component_names(
    candidates: List[Tuple[Dict[str, Any], int]],
    patterns: List[str],
    min_duplicates: int = 2,
) -> List[Tuple[Dict[str, Any], str]]:
    component_type_nodes: List[Dict[str, Any]] = []
    duplicate_groups: Dict[Tuple[Any, ...], List[Dict[str, Any]]] = {}

    for node, _ in candidates:
        if _is_component_type(node):
            component_type_nodes.append(node)
        else:
            sig = _signature(node)
            duplicate_groups.setdefault(sig, []).append(node)

    assignments: List[Tuple[Dict[str, Any], str]] = []
    used: Set[str] = set()

    def _claim_name(base: str) -> str:
        safe = _sanitize_component_name(_to_pascal_case(base))
        if safe not in used:
            used.add(safe)
            return safe
        counter = 2
        while True:
            candidate = f"{safe}{counter}"
            if candidate not in used:
                used.add(candidate)
                return candidate
            counter += 1

    duplicate_index = 0
    for sig, group in duplicate_groups.items():
        if len(group) >= min_duplicates:
            # Prefer a pattern-derived name from any group member, else generic.
            base_name: Optional[str] = None
            for node in group:
                base_name = _pattern_base_name(node, patterns)
                if base_name:
                    break
            if not base_name:
                base_name = _name_for_duplicate(sig, duplicate_index)
                duplicate_index += 1
            for idx, node in enumerate(group):
                name = base_name if idx == 0 else f"{base_name}{idx + 1}"
                assignments.append((node, _claim_name(name)))
        else:
            for node in group:
                if _is_named_candidate(node, patterns):
                    base_name = _to_pascal_case(node.get("figma_name") or "Component")
                    assignments.append((node, _claim_name(base_name)))

    for node in component_type_nodes:
        base_name = _to_pascal_case(node.get("figma_name") or "Component")
        assignments.append((node, _claim_name(base_name)))

    return assignments


def _find_node_by_id(root: Dict[str, Any], figma_id: str) -> Optional[Dict[str, Any]]:
    if not isinstance(root, dict):
        return None
    if root.get("figma_id") == figma_id:
        return root
    for child in root.get("children", []):
        found = _find_node_by_id(child, figma_id)
        if found:
            return found
    return None


def _replace_node_in_tree(
    node: Dict[str, Any],
    figma_id: str,
    replacement: Dict[str, Any],
) -> bool:
    for idx, child in enumerate(node.get("children", [])):
        if child.get("figma_id") == figma_id:
            node["children"][idx] = replacement
            return True
        if _replace_node_in_tree(child, figma_id, replacement):
            return True
    return False


def _wrap_component_code(name: str, node: Dict[str, Any], imports: List[str]) -> str:
    import_block = "\n".join(imports)
    if import_block:
        import_block += "\n\n"
    rendered = _node_to_tsx(node, depth=2)
    return f"""{import_block}export default function {name}() {{
  return (
{rendered}
  );
}}
"""


class ComponentExtractor:
    def __init__(
        self,
        output_dir: str = "src/app/components",
        root_dir: str = ".",
        patterns: Optional[List[str]] = None,
        min_duplicates: int = 2,
    ):
        self.output_dir = _validate_target_dir(output_dir, root_dir)
        self.patterns = patterns or DEFAULT_COMPONENT_PATTERNS
        self.min_duplicates = max(min_duplicates, 2)
        self.root_dir = Path(root_dir).resolve()

    def extract(
        self,
        ast: Dict[str, Any],
    ) -> Tuple[Dict[str, Any], List[ExtractedComponent]]:
        root = ast.get("root", ast)
        if not isinstance(root, dict):
            raise ValueError("AST root must be a dict")

        candidates = _collect_substantial_nodes(root, self.patterns)
        assigned = _assign_component_names(candidates, self.patterns, self.min_duplicates)

        extracted_ids: Set[str] = set()
        extracted: List[ExtractedComponent] = []
        page_root = json.loads(json.dumps(root, ensure_ascii=False))

        for node, name in assigned:
            figma_id = node.get("figma_id")
            if not figma_id:
                continue
            if figma_id in extracted_ids:
                continue

            existing = _find_node_by_id(page_root, figma_id)
            if not existing:
                continue

            self.output_dir.mkdir(parents=True, exist_ok=True)
            file_path = self.output_dir / f"{name}.tsx"

            component_node = json.loads(json.dumps(existing, ensure_ascii=False))
            imports = _detect_font_imports(component_node)
            if not imports:
                imports = ['import React from "react"']

            code = _wrap_component_code(name, component_node, imports)
            file_path.write_text(code, encoding="utf-8")

            component_path = "@/app/components/" + name
            replacement = {
                "tag": name,
                "component": True,
                "component_name": name,
                "component_path": component_path,
                "props": {},
                "children": [],
                "figma_id": figma_id,
            }
            _replace_node_in_tree(page_root, figma_id, replacement)

            extracted.append(ExtractedComponent(
                name=name,
                node=component_node,
                file_path=file_path,
                imports=imports,
            ))
            extracted_ids.add(figma_id)

        page_ast = {"root": page_root}
        return page_ast, extracted


def run_extraction(
    ast_path: str,
    output_dir: str = "src/app/components",
    page_ast_output: str = "page_ast.json",
    component_map_output: str = "component_map.json",
    patterns: Optional[List[str]] = None,
    min_duplicates: int = 2,
    root_dir: str = ".",
) -> Dict[str, Any]:
    ast_file = Path(ast_path)
    if not ast_file.exists():
        raise FileNotFoundError(f"AST file not found: {ast_path}")

    with open(ast_file, "r", encoding="utf-8") as f:
        ast = json.load(f)

    extractor = ComponentExtractor(
        output_dir=output_dir,
        root_dir=root_dir,
        patterns=patterns,
        min_duplicates=min_duplicates,
    )
    page_ast, components = extractor.extract(ast)

    page_ast_path = Path(page_ast_output)
    page_ast_path.parent.mkdir(parents=True, exist_ok=True)
    with open(page_ast_path, "w", encoding="utf-8") as f:
        json.dump(page_ast, f, ensure_ascii=False, indent=2)

    root_path = Path(root_dir).resolve()
    component_map = {
        "components": [
            {
                "name": c.name,
                "file": str(c.file_path.relative_to(root_path)),
                "figma_id": c.node.get("figma_id"),
                "figma_name": c.node.get("figma_name"),
                "import_path": "@/app/components/" + c.name,
            }
            for c in components
        ],
        "extracted_count": len(components),
        "page_ast": str(page_ast_path.resolve()),
    }

    map_path = Path(component_map_output)
    map_path.parent.mkdir(parents=True, exist_ok=True)
    with open(map_path, "w", encoding="utf-8") as f:
        json.dump(component_map, f, ensure_ascii=False, indent=2)

    return component_map


def main():
    parser = argparse.ArgumentParser(
        description="Component Extractor: Tailwind AST → reusable Next.js components + page AST"
    )
    parser.add_argument(
        "--ast",
        default="layout_ast.json",
        help="Путь к JSON-файлу с Tailwind AST от layout_engine.py.",
    )
    parser.add_argument(
        "--output-dir",
        default="src/app/components",
        help="Директория для сохранения компонентов.",
    )
    parser.add_argument(
        "--page-ast-output",
        default="page_ast.json",
        help="Путь для сохранения урезанного AST страницы.",
    )
    parser.add_argument(
        "--component-map-output",
        default="component_map.json",
        help="Путь для сохранения реестра компонентов.",
    )
    parser.add_argument(
        "--patterns",
        default=None,
        help='JSON-список строк паттернов имён для извлечения, например ["card", "hero"].',
    )
    parser.add_argument(
        "--min-duplicates",
        type=int,
        default=2,
        help="Минимальное число структурных дубликатов для извлечения (по умолчанию 2).",
    )
    parser.add_argument(
        "--workspace-root",
        default=".",
        help="Корень рабочего пространства для проверки path traversal.",
    )
    args = parser.parse_args()

    patterns: Optional[List[str]] = None
    if args.patterns:
        try:
            patterns = json.loads(args.patterns)
            if not isinstance(patterns, list) or not all(isinstance(p, str) for p in patterns):
                raise ValueError("patterns must be a JSON list of strings")
        except Exception as e:
            print(f"[ERROR] Invalid --patterns value: {e}")
            raise SystemExit(1)

    result = run_extraction(
        ast_path=args.ast,
        output_dir=args.output_dir,
        page_ast_output=args.page_ast_output,
        component_map_output=args.component_map_output,
        patterns=patterns,
        min_duplicates=args.min_duplicates,
        root_dir=args.workspace_root,
    )
    print(f"[EXTRACT] {result['extracted_count']} component(s) written to {args.output_dir}")
    for c in result["components"]:
        print(f"  - {c['name']} -> {c['file']}")


if __name__ == "__main__":
    main()
