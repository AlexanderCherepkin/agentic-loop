import json
import re
import argparse
from pathlib import Path
from typing import Any, Dict, List, Optional


DEFAULT_OUTPUT = "src/app/page.tsx"
DEFAULT_ROOT_CLASS = "relative w-full min-h-screen overflow-x-hidden"


def _indent(depth: int, spaces: int = 2) -> str:
    return " " * (depth * spaces)


def _safe_prop(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return str(value).lower()
    if isinstance(value, (int, float)):
        return str(value)
    return json.dumps(value, ensure_ascii=False)


def _style_to_string(styles: Dict[str, str]) -> str:
    if not styles:
        return ""
    pairs = []
    for key, value in sorted(styles.items()):
        kebab = re.sub(r"([A-Z])", r"-\1", key).lower()
        pairs.append(f"{kebab}: {value}")
    return "; ".join(pairs)


def _class_string(classes: List[str]) -> str:
    if not classes:
        return ""
    return " ".join(classes)


def _render_inline_styles(styles: Dict[str, str]) -> str:
    if not styles:
        return ""
    style_str = _style_to_string(styles)
    return f' style={{{json.dumps(style_str)}}}'


def _sanitize_path(path: str, root_dir: Optional[str] = None) -> Path:
    target = Path(path).resolve()
    root = Path(root_dir).resolve() if root_dir else Path.cwd().resolve()
    if not str(target).startswith(str(root)):
        raise ValueError(f"Path traversal detected: {path}")
    return target


def _extract_text_nodes(node: Dict[str, Any]) -> List[Dict[str, Any]]:
    if node.get("text") is not None:
        return [node]
    results: List[Dict[str, Any]] = []
    for child in node.get("children", []):
        results.extend(_extract_text_nodes(child))
    return results


def _collect_all_nodes(node: Dict[str, Any]) -> List[Dict[str, Any]]:
    results = [node]
    for child in node.get("children", []):
        results.extend(_collect_all_nodes(child))
    return results


def _detect_font_imports(ast: Dict[str, Any]) -> List[str]:
    fonts: set = set()
    root = ast.get("root", ast)
    for node in _collect_all_nodes(root):
        for cls in node.get("classes", []):
            match = re.match(r"font-\[([^\]]+)\]", cls)
            if match:
                family = match.group(1).replace("_", " ")
                if family in ("Inter", "Roboto", "Poppins", "Manrope", "Open Sans", "Lato", "Montserrat"):
                    fonts.add(family.replace(" ", "+"))
    imports = []
    for font in sorted(fonts):
        imports.append(f'import {{ {font.replace("+", " ")} }} from "next/font/google"')
    return imports


def _detect_component_imports(ast: Dict[str, Any]) -> List[str]:
    root = ast.get("root", ast)
    imports: set = set()
    for node in _collect_all_nodes(root):
        if node.get("component"):
            name = node.get("component_name", node.get("tag", "Unknown"))
            path = node.get("component_path", f"@/app/components/{name}")
            imports.add(f'import {name} from "{path}"')
    return sorted(imports)


def _node_to_tsx(node: Dict[str, Any], depth: int = 1) -> str:
    tag = node.get("tag", "div")
    classes = node.get("classes", [])
    class_attr = f' className="{_class_string(classes)}"' if classes else ""
    style_attr = _render_inline_styles(node.get("inline_styles", {}))

    text = node.get("text")
    src = node.get("src")
    alt = node.get("alt", "")

    inner_indent = _indent(depth + 1)
    start_indent = _indent(depth)

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


def _wrap_page(title: str, imports: List[str], sections: List[str]) -> str:
    import_block = "\n".join(imports)
    sections_block = "\n".join(sections)
    return f"""{import_block}

export const metadata = {{
  title: {json.dumps(title)},
}};

export default function Page() {{
  return (
    <div className="{DEFAULT_ROOT_CLASS}">
{sections_block}
    </div>
  );
}}
"""


def _infer_page_title(ast: Dict[str, Any]) -> str:
    root = ast.get("root", ast)
    nodes = _collect_all_nodes(root)
    for node in nodes:
        text = node.get("text", "")
        if node.get("tag") in ("h1", "h2") and text:
            return text.strip()
    for node in nodes:
        text = node.get("text", "")
        if text:
            return text.strip()
    return "Landing"


def compose_page(ast: Dict[str, Any], title: Optional[str] = None) -> str:
    """Превращает Tailwind AST в Next.js page.tsx."""
    page_title = title or _infer_page_title(ast)
    imports = _detect_font_imports(ast)
    imports.extend(_detect_component_imports(ast))

    if not imports:
        imports = ['import React from "react"']

    root = ast.get("root", ast)
    sections: List[str] = []

    top_level = root.get("children", [])
    if not top_level:
        top_level = [root]

    for section in top_level:
        rendered = _node_to_tsx(section, depth=2)
        if rendered.strip():
            sections.append(rendered)

    return _wrap_page(page_title, imports, sections)


def compose_page_from_ast_file(ast_path: str, title: Optional[str] = None) -> str:
    path = Path(ast_path)
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return compose_page(data, title=title)


def write_page(code: str, output_path: str, root_dir: Optional[str] = None) -> str:
    target = _sanitize_path(output_path, root_dir=root_dir)
    target.parent.mkdir(parents=True, exist_ok=True)
    with open(target, "w", encoding="utf-8") as f:
        f.write(code)
    return str(target)


def main():
    parser = argparse.ArgumentParser(description="Section Composer: Tailwind AST → Next.js page.tsx")
    parser.add_argument(
        "--ast",
        default="layout_ast.json",
        help="Путь к JSON-файлу с Tailwind AST от layout_engine.py.",
    )
    parser.add_argument(
        "--output",
        default=DEFAULT_OUTPUT,
        help=f"Путь для сохранения Next.js-страницы (по умолчанию {DEFAULT_OUTPUT}).",
    )
    parser.add_argument(
        "--title",
        default=None,
        help="Заголовок страницы (по умолчанию извлекается из первого заголовка AST).",
    )
    args = parser.parse_args()

    code = compose_page_from_ast_file(args.ast, title=args.title)
    written_path = write_page(code, args.output)
    print(f"[COMPOSE] Page written to {written_path}")


if __name__ == "__main__":
    main()
