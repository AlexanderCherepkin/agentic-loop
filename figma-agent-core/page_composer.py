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


def _to_camel_case(kebab: str) -> str:
    parts = kebab.split("-")
    return parts[0] + "".join(p.capitalize() for p in parts[1:])


def _render_inline_styles(styles: Dict[str, str]) -> str:
    if not styles:
        return ""
    entries = [
        f"{_to_camel_case(key)}: {json.dumps(value)}"
        for key, value in sorted(styles.items())
    ]
    return f' style={{{{{", ".join(entries)}}}}}'


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


GOOGLE_FONT_FAMILIES = {
    "Inter", "Roboto", "Poppins", "Manrope", "Open Sans", "Lato", "Montserrat",
    "Raleway", "Nunito", "Playfair Display", "Merriweather", "Space Grotesk",
    "DM Sans", "Outfit", "Work Sans", "Fira Sans", "Source Sans 3", "IBM Plex Sans", "PT Sans",
}


def _font_variable_name(family: str) -> str:
    return re.sub(r"[^a-zA-Z0-9]", "", family).lower() or "font"


def _detect_font_imports(ast: Dict[str, Any]) -> List[str]:
    """Возвращает строки импортов и объявлений next/font/google переменных."""
    fonts: set = set()
    root = ast.get("root", ast)
    for node in _collect_all_nodes(root):
        for cls in node.get("classes", []):
            match = re.match(r"font-\[([^\]]+)\]", cls)
            if match:
                family = match.group(1).replace("_", " ")
                if family in GOOGLE_FONT_FAMILIES:
                    fonts.add(family)
            # Поддержка токенизированных шрифтов, например font-sans.
            if cls == "font-sans" and node.get("inline_styles", {}).get("fontFamily"):
                family = node["inline_styles"]["fontFamily"].strip("'")
                if family in GOOGLE_FONT_FAMILIES:
                    fonts.add(family)

    import_names = sorted(f.replace(" ", "_") for f in fonts)
    import_line = 'import { ' + ', '.join(import_names) + ' } from "next/font/google"'
    declarations: List[str] = []
    for family in sorted(fonts):
        import_name = family.replace(" ", "_")
        var_name = _font_variable_name(family)
        declarations.append(
            f'const {var_name} = {import_name}({{" subsets: ["latin"], variable: "--font-{var_name}" }})'
        )
    return [import_line] + declarations


def _detect_image_imports(ast: Dict[str, Any]) -> List[str]:
    root = ast.get("root", ast)
    for node in _collect_all_nodes(root):
        if node.get("asset_type") == "raster" and node.get("asset_width") and node.get("asset_height"):
            return ['import Image from "next/image"']
    return []


def _detect_backend_imports(ast: Dict[str, Any]) -> List[str]:
    root = ast.get("root", ast)
    imports: set = set()
    for node in _collect_all_nodes(root):
        action = node.get("backend_action")
        model = node.get("backend_model")
        if action and model:
            imports.add(f'import {{ {action} }} from "@/app/actions/{model.lower()}Action"')
    return sorted(imports)


def _detect_component_imports(ast: Dict[str, Any]) -> List[str]:
    root = ast.get("root", ast)
    imports: set = set()
    for node in _collect_all_nodes(root):
        if node.get("component"):
            name = node.get("component_name", node.get("tag", "Unknown"))
            path = node.get("component_path", f"@/app/components/{name}")
            imports.add(f'import {name} from "{path}"')
    return sorted(imports)


def _find_node_by_figma_id(node: Dict[str, Any], figma_id: str) -> Optional[Dict[str, Any]]:
    if node.get("figma_id") == figma_id:
        return node
    for child in node.get("children", []):
        found = _find_node_by_figma_id(child, figma_id)
        if found:
            return found
    return None


def _state_setter(state_key: str) -> str:
    if not state_key:
        return "setState"
    return f"set{state_key[0].upper()}{state_key[1:]}"


def _build_handler(trigger: Dict[str, Any], state_key: str) -> str:
    ttype = trigger.get("type")
    if ttype == "navigate":
        route = trigger.get("route", "/")
        return f"() => router.push({_safe_prop(route)})"
    if ttype == "url":
        url = trigger.get("url", "")
        if trigger.get("external"):
            return f"() => window.open({_safe_prop(url)}, '_blank')"
        return f"() => router.push({_safe_prop(url)})"
    if ttype == "overlay":
        setter = _state_setter(state_key)
        return f"() => {setter}(true)"
    if ttype == "variant":
        setter = _state_setter(state_key)
        return f"() => {setter}(v => !v)"
    return "() => {}"


def _build_state_hooks(nodes: List[Dict[str, Any]]) -> List[str]:
    hooks: List[str] = []
    seen: set = set()
    for node in nodes:
        interactive = node.get("interactive", {})
        state_key = interactive.get("state_key", "")
        if not state_key or state_key in seen:
            continue
        seen.add(state_key)
        setter = _state_setter(state_key)
        hooks.append(f"const [{state_key}, {setter}] = useState(false);")
    return hooks


def _detect_interactive_imports(ast: Dict[str, Any]) -> tuple[List[str], bool]:
    root = ast.get("root", ast)
    needs_state = any(n.get("interactive") for n in _collect_all_nodes(root))
    needs_router = False
    for node in _collect_all_nodes(root):
        for trigger in node.get("interactive", {}).get("triggers", []):
            if trigger.get("type") in ("navigate", "url") and not trigger.get("external"):
                needs_router = True
    imports: List[str] = []
    if needs_state:
        imports.append('import { useState } from "react"')
    if needs_router:
        imports.append('import { useRouter } from "next/navigation"')
    return imports, needs_router


def _wrap_conditional(rendered: str, state_key: Optional[str], start_indent: str) -> str:
    if not state_key:
        return rendered
    return f"{start_indent}{{{state_key}}} && (\n{rendered}\n{start_indent})"


def _node_to_tsx(node: Dict[str, Any], depth: int = 1) -> str:
    tag = node.get("tag", "div")
    classes = list(node.get("classes", []))
    variants = node.get("responsive_variants") or {}
    for token in ("sm", "md", "lg", "xl"):
        classes.extend(variants.get(token, []))
    class_attr = f' className="{_class_string(classes)}"' if classes else ""
    style_attr = _render_inline_styles(node.get("inline_styles", {}))

    text = node.get("text")
    src = node.get("src")
    alt = node.get("alt", "")

    inner_indent = _indent(depth + 1)
    start_indent = _indent(depth)

    extra_attrs = ""
    inline_svg = node.get("inline_svg")
    asset_type = node.get("asset_type")
    asset_width = node.get("asset_width")
    asset_height = node.get("asset_height")
    backend_action = node.get("backend_action")
    backend_field = node.get("backend_field")
    input_type = node.get("input_type", "text")
    required = node.get("required", False)
    interactive = node.get("interactive")
    conditional_state = node.get("conditional_render")

    if backend_action:
        tag = "form"
        extra_attrs += f" action={{{backend_action}}}"

    if backend_field:
        tag = "input"
        extra_attrs += f" name={_safe_prop(backend_field)} type={_safe_prop(input_type)}"
        if required:
            extra_attrs += " required"
        if text is not None:
            extra_attrs += f" placeholder={_safe_prop(text)}"
            text = None

    if tag == "img" and src:
        if asset_type == "raster" and asset_width and asset_height:
            tag = "Image"
            extra_attrs += (
                f' src={_safe_prop(src)} alt={_safe_prop(alt)}'
                f' width={{{asset_width}}} height={{{asset_height}}}'
            )
        elif inline_svg:
            # inline SVG рендерится напрямую; class/style применяются к обёртке.
            pass
        else:
            extra_attrs += f' src={_safe_prop(src)} alt={_safe_prop(alt)}'

    if interactive:
        state_key = interactive.get("state_key", "")
        for trigger in interactive.get("triggers", []):
            event = trigger.get("event", "on_click")
            handler = _build_handler(trigger, state_key)
            if event == "on_click":
                extra_attrs += f" onClick={{{handler}}}"
            elif event in ("on_hover", "on_mouse_enter"):
                extra_attrs += f" onMouseEnter={{{handler}}}"
            elif event == "on_mouse_leave":
                extra_attrs += f" onMouseLeave={{{handler}}}"

    children = node.get("children", [])

    if tag == "input":
        return _wrap_conditional(
            f"{start_indent}<{tag}{class_attr}{style_attr}{extra_attrs} />",
            conditional_state,
            start_indent,
        )

    if inline_svg and tag == "img":
        wrapper = f'{start_indent}<div{class_attr}{style_attr}>\n{inner_indent}{inline_svg}\n{start_indent}</div>'
        return _wrap_conditional(wrapper, conditional_state, start_indent)

    if node.get("component"):
        name = node.get("component_name", tag)
        props = node.get("props", {})
        props_str = ""
        if props:
            props_str = " " + " ".join(f'{k}={_safe_prop(v)}' for k, v in props.items())
        return _wrap_conditional(
            f"{start_indent}<{name}{props_str} />",
            conditional_state,
            start_indent,
        )

    if children:
        rendered_children = "\n".join(_node_to_tsx(child, depth + 1) for child in children)
        return _wrap_conditional(
            (
                f"{start_indent}<{tag}{class_attr}{style_attr}{extra_attrs}>\n"
                f"{rendered_children}\n"
                f"{start_indent}</{tag}>"
            ),
            conditional_state,
            start_indent,
        )

    if text is not None:
        if tag in ("span", "p", "a", "label"):
            rendered = f"{start_indent}<{tag}{class_attr}{style_attr}{extra_attrs}>{text}</{tag}>"
        else:
            rendered = f"{start_indent}<{tag}{class_attr}{style_attr}{extra_attrs}>\n{inner_indent}{text}\n{start_indent}</{tag}>"
        return _wrap_conditional(rendered, conditional_state, start_indent)

    if tag == "img":
        return _wrap_conditional(
            f"{start_indent}<{tag}{class_attr}{style_attr}{extra_attrs} />",
            conditional_state,
            start_indent,
        )

    return _wrap_conditional(
        f"{start_indent}<{tag}{class_attr}{style_attr}{extra_attrs} />",
        conditional_state,
        start_indent,
    )


def _wrap_page(
    title: str,
    imports: List[str],
    sections: List[str],
    state_hooks: Optional[List[str]] = None,
    needs_router: bool = False,
    is_client: bool = False,
) -> str:
    import_block = "\n".join(imports)
    sections_block = "\n".join(sections)

    hooks_lines: List[str] = []
    if needs_router:
        hooks_lines.append("const router = useRouter();")
    if state_hooks:
        hooks_lines.extend(state_hooks)

    hooks_block = ""
    if hooks_lines:
        hooks_block = "\n  " + "\n  ".join(hooks_lines) + "\n"

    if is_client:
        return f'''"use client"

{import_block}

export default function Page() {{{hooks_block}
  return (
    <div className="{DEFAULT_ROOT_CLASS}">
{sections_block}
    </div>
  );
}}
'''

    return f'''{import_block}

export const metadata = {{
  title: {json.dumps(title)},
}};

export default function Page() {{{hooks_block}
  return (
    <div className="{DEFAULT_ROOT_CLASS}">
{sections_block}
    </div>
  );
}}
'''


def _collect_fonts(ast: Dict[str, Any]) -> List[str]:
    """Возвращает список Google Font family names, используемых в AST."""
    families: set = set()
    root = ast.get("root", ast)
    for node in _collect_all_nodes(root):
        for cls in node.get("classes", []):
            match = re.match(r"font-\[([^\]]+)\]", cls)
            if match:
                family = match.group(1).replace("_", " ")
                if family in GOOGLE_FONT_FAMILIES:
                    families.add(family)
        if "font-sans" in node.get("classes", []) and node.get("inline_styles", {}).get("fontFamily"):
            family = node["inline_styles"]["fontFamily"].strip("'")
            if family in GOOGLE_FONT_FAMILIES:
                families.add(family)
    return sorted(families)


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
    imports = _detect_image_imports(ast)
    imports.extend(_detect_backend_imports(ast))
    imports.extend(_detect_font_imports(ast))
    imports.extend(_detect_component_imports(ast))

    root = ast.get("root", ast)
    interactive_nodes = [n for n in _collect_all_nodes(root) if n.get("interactive")]
    interactive_imports, needs_router = _detect_interactive_imports(ast)
    imports.extend(interactive_imports)

    if not imports:
        imports = ['import React from "react"']

    for node in interactive_nodes:
        for trigger in node["interactive"].get("triggers", []):
            if trigger.get("type") == "overlay":
                dest_id = trigger.get("destination_id")
                if dest_id:
                    dest_node = _find_node_by_figma_id(root, dest_id)
                    if dest_node:
                        dest_node["conditional_render"] = node["interactive"]["state_key"]

    sections: List[str] = []
    top_level = root.get("children", [])
    if not top_level:
        top_level = [root]

    for section in top_level:
        rendered = _node_to_tsx(section, depth=2)
        if rendered.strip():
            sections.append(rendered)

    state_hooks = _build_state_hooks(interactive_nodes)
    is_client = bool(interactive_nodes)
    return _wrap_page(
        page_title,
        imports,
        sections,
        state_hooks=state_hooks,
        needs_router=needs_router,
        is_client=is_client,
    )


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




def compose_layout(title: str, fonts: Optional[List[str]] = None) -> str:
    fonts = fonts or []
    import_block = 'import type { Metadata } from "next";\nimport React from "react";\nimport "./globals.css";'
    font_declarations: List[str] = []
    class_attr = '"antialiased"'
    if fonts:
        import_block += '\nimport { ' + ', '.join(sorted(f.replace(" ", "_") for f in fonts)) + ' } from "next/font/google";'
        for family in sorted(fonts):
            var_name = _font_variable_name(family)
            font_declarations.append(
                f'const {var_name} = {family.replace(" ", "_")}({{ subsets: ["latin"], variable: "--font-{var_name}" }})'
            )
        var_refs = " ".join(f"{_font_variable_name(f)}.variable" for f in sorted(fonts))
        class_attr = f"{{`${{{var_refs}}} antialiased`}}"
    declarations_block = "\n".join(font_declarations)
    return f"""{import_block}
{declarations_block}

export const metadata: Metadata = {{
  title: {json.dumps(title)},
}};

export default function RootLayout({{
  children,
}}: {{
  children: React.ReactNode;
}}) {{
  return (
    <html lang="en">
      <body className={class_attr}>{{children}}</body>
    </html>
  );
}}
"""


def write_layout(title: str, output_path: str, root_dir: Optional[str] = None, fonts: Optional[List[str]] = None) -> str:
    target = _sanitize_path(output_path, root_dir=root_dir)
    target.parent.mkdir(parents=True, exist_ok=True)
    code = compose_layout(title, fonts=fonts)
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
        "--layout-output",
        default="src/app/layout.tsx",
        help="Путь для сохранения Next.js layout.tsx.",
    )
    parser.add_argument(
        "--title",
        default=None,
        help="Заголовок страницы (по умолчанию извлекается из первого заголовка AST).",
    )
    args = parser.parse_args()

    ast = json.loads(Path(args.ast).read_text(encoding="utf-8"))
    code = compose_page(ast, title=args.title)
    written_path = write_page(code, args.output)
    print(f"[COMPOSE] Page written to {written_path}")

    page_title = args.title or _infer_page_title(ast)
    fonts = _collect_fonts(ast)
    layout_path = write_layout(page_title, args.layout_output, fonts=fonts)
    print(f"[COMPOSE] Layout written to {layout_path}")


if __name__ == "__main__":
    main()
