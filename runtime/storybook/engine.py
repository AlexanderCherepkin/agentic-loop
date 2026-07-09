from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .config import StorybookConfig


def _stable_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True)


@dataclass
class StorybookResult:
    files_written: list[str] = field(default_factory=list)
    files_modified: list[str] = field(default_factory=list)
    stories: list[dict[str, Any]] = field(default_factory=list)
    errors: list[dict[str, Any]] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


class StorybookEngine:
    def __init__(self, target_dir: Path | str, config: StorybookConfig | None = None):
        self.target_dir = Path(target_dir).resolve()
        self.config = config or StorybookConfig()
        self.config.target_dir = self.target_dir
        self.result = StorybookResult()

    def run(self) -> StorybookResult:
        validation_errors = self.config.validate()
        if validation_errors:
            for err in validation_errors:
                self.result.errors.append({"file": "", "reason": err})
            return self.result

        components = self._discover_components()
        if not components:
            self.result.notes.append("No React components found; nothing to storybook.")
            return self.result

        self._write_storybook_config()
        self._write_preview_config()
        for component in components:
            self._write_story(component)
        self._update_package_json()

        return self.result

    def _discover_components(self) -> list[dict[str, Any]]:
        components: list[dict[str, Any]] = []
        for rel_dir in self.config.component_dirs:
            comp_dir = self.target_dir / rel_dir
            if not comp_dir.exists():
                continue
            for path in sorted(comp_dir.glob("*.tsx")):
                if path.name.endswith(".stories.tsx"):
                    continue
                if path.name.startswith("page") or path.name.startswith("layout"):
                    continue
                name = self._infer_component_name(path)
                if not name:
                    continue
                import_path = self._import_path(path)
                components.append({
                    "name": name,
                    "file": str(path.relative_to(self.target_dir).as_posix()),
                    "import_path": import_path,
                })
        return components

    def _infer_component_name(self, path: Path) -> str:
        content = path.read_text(encoding="utf-8")
        # Default export function name.
        match = re.search(r"export\s+default\s+function\s+(\w+)", content)
        if match:
            return match.group(1)
        # Named export function.
        match = re.search(r"export\s+function\s+(\w+)", content)
        if match:
            return match.group(1)
        # const Name = () => ... export default Name
        match = re.search(r"export\s+default\s+(\w+)", content)
        if match:
            return match.group(1)
        # Fallback to filename.
        return path.stem

    def _import_path(self, path: Path) -> str:
        rel = path.relative_to(self.target_dir).as_posix()
        without_ext = rel[:-4] if rel.endswith(".tsx") else rel
        return f"@/{without_ext.replace('src/', '', 1)}"

    def _write_file(self, rel_path: str, content: str) -> None:
        full_path = self.target_dir / rel_path
        try:
            full_path.parent.mkdir(parents=True, exist_ok=True)
            mode = "modified" if full_path.exists() else "written"
            full_path.write_text(content, encoding="utf-8")
            if mode == "written":
                self.result.files_written.append(rel_path)
            else:
                self.result.files_modified.append(rel_path)
        except Exception as exc:
            self.result.errors.append({"file": rel_path, "reason": str(exc)})

    def _write_storybook_config(self) -> None:
        main_ts = f"""import type {{ StorybookConfig }} from "@storybook/nextjs";

const config: StorybookConfig = {{
  stories: ["../{self.config.stories_dir}/**/*.stories.@(js|jsx|ts|tsx)"],
  addons: [
    "@storybook/addon-essentials",
    "@storybook/addon-interactions",
  ],
  framework: {{
    name: "{self.config.framework}",
    options: {{}},
  }},
  typescript: {{
    check: false,
    reactDocgen: "react-docgen-typescript",
  }},
}};

export default config;
"""
        self._write_file(".storybook/main.ts", main_ts)

    def _write_preview_config(self) -> None:
        preview_ts = """import type { Preview } from "@storybook/react";

const preview: Preview = {
  parameters: {
    actions: { argTypesRegex: "^on[A-Z].*" },
    controls: {
      matchers: {
        color: /(background|color)$/i,
        date: /Date$/,
      },
    },
  },
};

export default preview;
"""
        self._write_file(".storybook/preview.ts", preview_ts)

    def _write_story(self, component: dict[str, Any]) -> None:
        name = component["name"]
        import_path = component["import_path"]
        story_name = f"{name}Default"
        content = f"""import type {{ Meta, StoryObj }} from "@storybook/react";
import {name} from "{import_path}";

const meta: Meta<typeof {name}> = {{
  title: "UI/{name}",
  component: {name},
  parameters: {{
    layout: "centered",
  }},
  tags: ["autodocs"],
}};

export default meta;
type Story = StoryObj<typeof meta>;

export const {story_name}: Story = {{
  args: {{}},
}};
"""
        rel_path = f"{self.config.stories_dir}/{name}.stories.tsx"
        self._write_file(rel_path, content)
        self.result.stories.append({"name": name, "story_path": rel_path})

    def _update_package_json(self) -> None:
        package_path = self.target_dir / "package.json"
        if not package_path.exists():
            self.result.errors.append({"file": "package.json", "reason": "missing package.json; cannot update storybook scripts"})
            return
        try:
            data = json.loads(package_path.read_text(encoding="utf-8"))
        except Exception as exc:
            self.result.errors.append({"file": "package.json", "reason": f"cannot parse package.json: {exc}"})
            return

        scripts = data.setdefault("scripts", {})
        scripts.setdefault("storybook", "storybook dev -p 6006")
        scripts.setdefault("build-storybook", "storybook build")

        dev_deps = data.setdefault("devDependencies", {})
        dev_deps.setdefault("@storybook/nextjs", "^8.0.0")
        dev_deps.setdefault("@storybook/react", "^8.0.0")
        dev_deps.setdefault("@storybook/addon-essentials", "^8.0.0")
        dev_deps.setdefault("@storybook/addon-interactions", "^8.0.0")
        dev_deps.setdefault("storybook", "^8.0.0")

        package_path.write_text(_stable_json(data), encoding="utf-8")
        if "package.json" not in self.result.files_modified:
            self.result.files_modified.append("package.json")
