import pytest

TIER_MARKERS = {
    "tests/figma/": "figma",
    "tests/mcp/": "mcp",
    "tests/runtime/": "core",
    "tests/backend/": "core",
    "tests/integration/": "core",
    "runtime/": "core",
}


def pytest_collection_modifyitems(config, items):
    for item in items:
        path = str(item.path).replace("\\", "/")
        for prefix, marker in TIER_MARKERS.items():
            if prefix in path and not item.get_closest_marker(marker):
                item.add_marker(marker)
                break
