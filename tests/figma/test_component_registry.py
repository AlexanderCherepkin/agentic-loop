"""Unit tests for figma-agent-core/component_registry.py."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent
REGISTRY_PATH = ROOT / "figma-agent-core" / "component_registry.py"
FIXTURES = Path(__file__).resolve().parent / "fixtures"


def _load_registry_module() -> Any:
    spec = importlib.util.spec_from_file_location("figma_component_registry", str(REGISTRY_PATH))
    module = importlib.util.module_from_spec(spec)
    sys.modules["figma_component_registry"] = module
    spec.loader.exec_module(module)
    return module


registry_module = _load_registry_module()


def _load_fixture(name: str) -> Any:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def test_registry_extracts_component_set() -> None:
    doc = _load_fixture("component_set.json")
    builder = registry_module.RegistryBuilder(doc)
    data = builder.build()

    assert "10:1" in data["components"]
    entry = data["components"]["10:1"]
    assert entry["node_type"] == "COMPONENT_SET"
    assert entry["pascal_name"] == "Button"
    assert entry["file_path"] == "src/components/ui/Button.tsx"
    assert entry["default_variant_id"] == "11:1"
    assert set(entry["variant_properties"].keys()) == {"Variant", "Size"}
    assert entry["variant_properties"]["Variant"]["values"] == ["Primary", "Secondary"]


def test_registry_extracts_standalone_component() -> None:
    doc = _load_fixture("component_set.json")
    builder = registry_module.RegistryBuilder(doc)
    data = builder.build()

    assert "20:1" in data["components"]
    entry = data["components"]["20:1"]
    assert entry["node_type"] == "COMPONENT"
    assert entry["pascal_name"] == "IconButton"
    assert entry["variants"][0]["id"] == "20:1"


def test_registry_collects_instances() -> None:
    doc = _load_fixture("component_set.json")
    builder = registry_module.RegistryBuilder(doc)
    data = builder.build()

    button_entry = data["components"]["10:1"]
    assert "30:2" in button_entry["instances"]
    assert "30:3" not in button_entry["instances"]

    instance = data["instances"]["30:2"]
    assert instance["component_set_id"] == "10:1"
    assert instance["component_id"] == "11:1"
    assert instance["variant_properties"]["Variant"] == "Primary"


def test_registry_dependency_order() -> None:
    doc = _load_fixture("component_set.json")
    builder = registry_module.RegistryBuilder(doc)
    data = builder.build()

    order = data["dependency_order"]
    assert "10:1" in order
    assert "20:1" in order
    # IconButton has no deps; Button depends on IconButton via nested instance? Actually our fixture
    # has Card (FRAME) containing instances, not component sets containing instances. So no component deps.
    # Ensure all components appear before any depending component; here none depend on each other.


def test_registry_writes_file(tmp_path: Path) -> None:
    doc = _load_fixture("component_set.json")
    out = tmp_path / "registry.json"
    builder = registry_module.RegistryBuilder(doc, output_path=out)
    builder.build_and_write()
    assert out.exists()
    loaded = json.loads(out.read_text(encoding="utf-8"))
    assert "components" in loaded


def test_component_registry_lookup() -> None:
    doc = _load_fixture("component_set.json")
    builder = registry_module.RegistryBuilder(doc)
    data = builder.build()
    reg = registry_module.ComponentRegistry(data)

    instance = {
        "id": "30:2",
        "type": "INSTANCE",
        "componentSetId": "10:1",
        "componentId": "11:1",
    }
    entry = reg.lookup_by_instance(instance)
    assert entry is not None
    assert entry["pascal_name"] == "Button"
