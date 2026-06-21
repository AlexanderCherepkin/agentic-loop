from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple


def _to_pascal(name: str) -> str:
    cleaned = re.sub(r"[^\w\s/]+", " ", name)
    parts = re.split(r"[\s/]+", cleaned)
    return "".join(part.capitalize() for part in parts if part)


def _is_component_set(node: Dict[str, Any]) -> bool:
    return node.get("type") == "COMPONENT_SET"


def _is_component(node: Dict[str, Any]) -> bool:
    return node.get("type") == "COMPONENT"


def _is_instance(node: Dict[str, Any]) -> bool:
    return node.get("type") == "INSTANCE"


class ComponentRegistryError(Exception):
    pass


@dataclass
class RegistryEntry:
    id: str
    name: str
    node_type: str
    pascal_name: str
    file_path: str
    variants: List[Dict[str, Any]] = field(default_factory=list)
    variant_properties: Dict[str, Any] = field(default_factory=dict)
    default_variant_id: Optional[str] = None
    instances: List[str] = field(default_factory=list)
    dependencies: List[str] = field(default_factory=list)
    is_library: bool = False


@dataclass
class InstanceEntry:
    id: str
    name: str
    component_id: Optional[str]
    component_set_id: Optional[str]
    variant_properties: Dict[str, str] = field(default_factory=dict)
    overrides: List[Dict[str, Any]] = field(default_factory=list)


class RegistryBuilder:
    def __init__(self, document: Dict[str, Any], output_path: Optional[Path | str] = None):
        self.document = document
        self.output_path = output_path or Path("component_registry.json")
        self._sets: Dict[str, Dict[str, Any]] = {}
        self._components: Dict[str, Dict[str, Any]] = {}
        self._instances: Dict[str, Dict[str, Any]] = {}
        self._entries: Dict[str, RegistryEntry] = {}
        self._parent_map: Dict[str, Optional[str]] = {}

    def build(self) -> Dict[str, Any]:
        self._collect(self.document)
        self._build_entries()
        self._build_dependencies()
        graph = self._build_dependency_graph()
        order = self._topological_sort(graph)
        registry = {
            "version": "1.0",
            "components": {e.id: self._entry_to_dict(e) for e in self._entries.values()},
            "instances": {iid: self._instance_to_dict(node) for iid, node in self._instances.items()},
            "dependency_graph": graph,
            "dependency_order": order,
        }
        return registry

    def build_and_write(self) -> Path:
        registry = self.build()
        path = Path(self.output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(registry, indent=2, ensure_ascii=False), encoding="utf-8")
        return path

    def _collect(self, node: Dict[str, Any], parent_id: Optional[str] = None) -> None:
        nid = node.get("id")
        if nid is None:
            return
        self._parent_map[nid] = parent_id

        if _is_component_set(node):
            self._sets[nid] = node
        elif _is_component(node):
            self._components[nid] = node
        elif _is_instance(node):
            self._instances[nid] = node

        for child in node.get("children", []):
            self._collect(child, nid)

    def _build_entries(self) -> None:
        for cid, node in self._sets.items():
            pascal = _to_pascal(node.get("name", "Component"))
            entry = RegistryEntry(
                id=cid,
                name=node.get("name", ""),
                node_type="COMPONENT_SET",
                pascal_name=pascal,
                file_path=f"src/components/ui/{pascal}.tsx",
                is_library=node.get("is_external", False),
            )
            self._extract_variant_metadata(entry, node)
            self._entries[cid] = entry

        for cid, node in self._components.items():
            if node.get("componentSetId") in self._entries:
                continue
            pascal = _to_pascal(node.get("name", "Component"))
            entry = RegistryEntry(
                id=cid,
                name=node.get("name", ""),
                node_type="COMPONENT",
                pascal_name=pascal,
                file_path=f"src/components/ui/{pascal}.tsx",
                variants=[{"id": cid, "name": node.get("name", ""), "variant_properties": {}}],
                default_variant_id=cid,
                is_library=node.get("is_external", False),
            )
            self._entries[cid] = entry

        for iid, node in self._instances.items():
            ref_set = node.get("componentSetId")
            ref_comp = node.get("componentId")
            if ref_set and ref_set in self._entries:
                self._entries[ref_set].instances.append(iid)
            elif ref_comp and ref_comp in self._entries:
                self._entries[ref_comp].instances.append(iid)

    def _extract_variant_metadata(self, entry: RegistryEntry, node: Dict[str, Any]) -> None:
        children = [c for c in node.get("children", []) if _is_component(c)]
        variants = []
        for child in children:
            vp = child.get("variantProperties") or {}
            variants.append({"id": child.get("id"), "name": child.get("name", ""), "variant_properties": vp})
        entry.variants = variants

        group_props = node.get("variantGroupProperties") or node.get("variantProperties") or {}
        schema: Dict[str, Any] = {}
        if group_props and isinstance(group_props, dict):
            for prop_name, prop_info in group_props.items():
                if isinstance(prop_info, dict):
                    schema[prop_name] = {
                        "type": "enum",
                        "values": prop_info.get("values", []),
                        "default": prop_info.get("defaultValue"),
                    }
                elif isinstance(prop_info, list):
                    schema[prop_name] = {"type": "enum", "values": list(prop_info), "default": prop_info[0] if prop_info else None}
                else:
                    schema[prop_name] = {"type": "enum", "values": [str(prop_info)], "default": str(prop_info)}

        if not schema:
            all_values: Dict[str, Set[str]] = {}
            for variant in variants:
                for key, value in variant["variant_properties"].items():
                    all_values.setdefault(key, set()).add(str(value))
            for key, values in all_values.items():
                sorted_values = sorted(values)
                schema[key] = {"type": "enum", "values": sorted_values, "default": sorted_values[0] if sorted_values else None}

        entry.variant_properties = schema
        entry.default_variant_id = None
        for variant in variants:
            if all(
                variant["variant_properties"].get(key) == schema.get(key, {}).get("default")
                for key in schema
            ):
                entry.default_variant_id = variant["id"]
                break
        if not entry.default_variant_id and variants:
            entry.default_variant_id = variants[0]["id"]

    def _build_dependencies(self) -> None:
        for iid, node in self._instances.items():
            containing_entry_id = self._find_containing_entry_id(iid)
            if not containing_entry_id:
                continue
            target_id = node.get("componentSetId") or node.get("componentId")
            if target_id and target_id in self._entries and target_id != containing_entry_id:
                self._entries[containing_entry_id].dependencies.append(target_id)

    def _find_containing_entry_id(self, node_id: str) -> Optional[str]:
        while node_id:
            if node_id in self._entries:
                return node_id
            node_id = self._parent_map.get(node_id)
        return None

    def _build_dependency_graph(self) -> Dict[str, List[str]]:
        graph: Dict[str, List[str]] = {eid: [] for eid in self._entries}
        for eid, entry in self._entries.items():
            for dep in set(entry.dependencies):
                if dep in self._entries:
                    graph[eid].append(dep)
        return graph

    def _topological_sort(self, graph: Dict[str, List[str]]) -> List[str]:
        visited: Set[str] = set()
        temp: Set[str] = set()
        order: List[str] = []
        cycles: List[Tuple[str, str]] = []

        def visit(node: str) -> None:
            if node in visited:
                return
            if node in temp:
                cycles.append((node, node))
                return
            temp.add(node)
            for dep in graph.get(node, []):
                if dep in temp:
                    cycles.append((node, dep))
                    continue
                visit(dep)
            temp.remove(node)
            visited.add(node)
            order.append(node)

        for node in graph:
            visit(node)

        if cycles:
            print(f"[component_registry] dependency cycles detected (broken): {cycles}")

        order.reverse()
        return order

    def _entry_to_dict(self, entry: RegistryEntry) -> Dict[str, Any]:
        return {
            "id": entry.id,
            "name": entry.name,
            "node_type": entry.node_type,
            "pascal_name": entry.pascal_name,
            "file_path": entry.file_path,
            "variants": entry.variants,
            "variant_properties": entry.variant_properties,
            "default_variant_id": entry.default_variant_id,
            "instances": entry.instances,
            "dependencies": entry.dependencies,
            "is_library": entry.is_library,
        }

    def _instance_to_dict(self, node: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "id": node.get("id"),
            "name": node.get("name", ""),
            "component_set_id": node.get("componentSetId"),
            "component_id": node.get("componentId"),
            "variant_properties": node.get("variantProperties") or {},
            "overrides": node.get("overrides") or [],
        }


class ComponentRegistry:
    def __init__(self, data: Dict[str, Any]):
        self.data = data

    @classmethod
    def load(cls, path: Path | str) -> ComponentRegistry:
        with open(path, encoding="utf-8") as f:
            return cls(json.load(f))

    @property
    def components(self) -> Dict[str, Any]:
        return self.data.get("components", {})

    @property
    def instances(self) -> Dict[str, Any]:
        return self.data.get("instances", {})

    @property
    def dependency_order(self) -> List[str]:
        return self.data.get("dependency_order", [])

    def lookup_by_instance(self, instance: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        set_id = instance.get("componentSetId")
        comp_id = instance.get("componentId")
        if set_id and set_id in self.components:
            return self.components[set_id]
        if comp_id and comp_id in self.components:
            return self.components[comp_id]
        return None

    def lookup(self, component_id: str) -> Optional[Dict[str, Any]]:
        return self.components.get(component_id)

    def get_pascal_name(self, component_id: str) -> Optional[str]:
        entry = self.components.get(component_id)
        return entry.get("pascal_name") if entry else None


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Component Registry: Figma document → component_registry.json")
    parser.add_argument("--file", default="figma_node.json", help="Путь к JSON-файлу Figma-структуры.")
    parser.add_argument("--output", default="component_registry.json", help="Путь для сохранения реестра.")
    parser.add_argument("--node-id", default=None, help="ID конкретной ноды (опционально).")
    args = parser.parse_args()

    doc_path = Path(args.file)
    if not doc_path.exists():
        print(f"[ERROR] File not found: {doc_path}")
        sys.exit(1)
    doc = json.loads(doc_path.read_text(encoding="utf-8"))
    if args.node_id:
        def _find(nid: str, node: Dict[str, Any]) -> Optional[Dict[str, Any]]:
            if node.get("id") == nid:
                return node
            for child in node.get("children", []):
                found = _find(nid, child)
                if found:
                    return found
            return None
        target = _find(args.node_id, doc)
        if target:
            doc = target
        else:
            print(f"[WARN] Node {args.node_id} not found, using full document")
    out_path = Path(args.output)
    builder = RegistryBuilder(doc, out_path)
    builder.build_and_write()
    print(f"[REGISTRY] wrote {out_path}")
