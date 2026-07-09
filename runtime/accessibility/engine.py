from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .config import AccessibilityConfig, CheckType, WcagLevel


@dataclass
class AccessibilityIssue:
    file: str
    line: int
    check: str
    severity: str
    message: str
    suggestion: str


@dataclass
class AccessibilityReport:
    issues: list[AccessibilityIssue] = field(default_factory=list)
    passed: bool = False
    score: float = 0.0
    passed_checks: list[str] = field(default_factory=list)
    failed_checks: list[str] = field(default_factory=list)
    files_audited: list[str] = field(default_factory=list)
    duration_seconds: float = 0.0


# Standard Tailwind 3.x palette approximation for common colors.
_TAILWIND_SHADES: dict[str, dict[int, str]] = {
    "slate": {
        50: "#f8fafc", 100: "#f1f5f9", 200: "#e2e8f0", 300: "#cbd5e1",
        400: "#94a3b8", 500: "#64748b", 600: "#475569", 700: "#334155",
        800: "#1e293b", 900: "#0f172a", 950: "#020617",
    },
    "gray": {
        50: "#f9fafb", 100: "#f3f4f6", 200: "#e5e7eb", 300: "#d1d5db",
        400: "#9ca3af", 500: "#6b7280", 600: "#4b5563", 700: "#374151",
        800: "#1f2937", 900: "#111827", 950: "#030712",
    },
    "zinc": {
        50: "#fafafa", 100: "#f4f4f5", 200: "#e4e4e7", 300: "#d4d4d8",
        400: "#a1a1aa", 500: "#71717a", 600: "#52525b", 700: "#3f3f46",
        800: "#27272a", 900: "#18181b", 950: "#09090b",
    },
    "neutral": {
        50: "#fafafa", 100: "#f5f5f5", 200: "#e5e5e5", 300: "#d4d4d4",
        400: "#a3a3a3", 500: "#737373", 600: "#525252", 700: "#404040",
        800: "#262626", 900: "#171717", 950: "#0a0a0a",
    },
    "stone": {
        50: "#fafaf9", 100: "#f5f5f4", 200: "#e7e5e4", 300: "#d6d3d1",
        400: "#a8a29e", 500: "#78716c", 600: "#57534e", 700: "#44403c",
        800: "#292524", 900: "#1c1917", 950: "#0c0a09",
    },
    "red": {
        50: "#fef2f2", 100: "#fee2e2", 200: "#fecaca", 300: "#fca5a5",
        400: "#f87171", 500: "#ef4444", 600: "#dc2626", 700: "#b91c1c",
        800: "#991b1b", 900: "#7f1d1d", 950: "#450a0a",
    },
    "orange": {
        50: "#fff7ed", 100: "#ffedd5", 200: "#fed7aa", 300: "#fdba74",
        400: "#fb923c", 500: "#f97316", 600: "#ea580c", 700: "#c2410c",
        800: "#9a3412", 900: "#7c2d12", 950: "#431407",
    },
    "amber": {
        50: "#fffbeb", 100: "#fef3c7", 200: "#fde68a", 300: "#fcd34d",
        400: "#fbbf24", 500: "#f59e0b", 600: "#d97706", 700: "#b45309",
        800: "#92400e", 900: "#78350f", 950: "#451a03",
    },
    "yellow": {
        50: "#fefce8", 100: "#fef9c3", 200: "#fef08a", 300: "#fde047",
        400: "#facc15", 500: "#eab308", 600: "#ca8a04", 700: "#a16207",
        800: "#854d0e", 900: "#713f12", 950: "#422006",
    },
    "lime": {
        50: "#f7fee7", 100: "#ecfccb", 200: "#d9f99d", 300: "#bef264",
        400: "#a3e635", 500: "#84cc16", 600: "#65a30d", 700: "#4d7c0f",
        800: "#3f6212", 900: "#365314", 950: "#1a2e05",
    },
    "green": {
        50: "#f0fdf4", 100: "#dcfce7", 200: "#bbf7d0", 300: "#86efac",
        400: "#4ade80", 500: "#22c55e", 600: "#16a34a", 700: "#15803d",
        800: "#166534", 900: "#14532d", 950: "#052e16",
    },
    "emerald": {
        50: "#ecfdf5", 100: "#d1fae5", 200: "#a7f3d0", 300: "#6ee7b7",
        400: "#34d399", 500: "#10b981", 600: "#059669", 700: "#047857",
        800: "#065f46", 900: "#064e3b", 950: "#022c22",
    },
    "teal": {
        50: "#f0fdfa", 100: "#ccfbf1", 200: "#99f6e4", 300: "#5eead4",
        400: "#2dd4bf", 500: "#14b8a6", 600: "#0d9488", 700: "#0f766e",
        800: "#115e59", 900: "#134e4a", 950: "#042f2e",
    },
    "cyan": {
        50: "#ecfeff", 100: "#cffafe", 200: "#a5f3fc", 300: "#67e8f9",
        400: "#22d3ee", 500: "#06b6d4", 600: "#0891b2", 700: "#0e7490",
        800: "#155e75", 900: "#164e63", 950: "#083344",
    },
    "sky": {
        50: "#f0f9ff", 100: "#e0f2fe", 200: "#bae6fd", 300: "#7dd3fc",
        400: "#38bdf8", 500: "#0ea5e9", 600: "#0284c7", 700: "#0369a1",
        800: "#075985", 900: "#0c4a6e", 950: "#082f49",
    },
    "blue": {
        50: "#eff6ff", 100: "#dbeafe", 200: "#bfdbfe", 300: "#93c5fd",
        400: "#60a5fa", 500: "#3b82f6", 600: "#2563eb", 700: "#1d4ed8",
        800: "#1e40af", 900: "#1e3a8a", 950: "#172554",
    },
    "indigo": {
        50: "#eef2ff", 100: "#e0e7ff", 200: "#c7d2fe", 300: "#a5b4fc",
        400: "#818cf8", 500: "#6366f1", 600: "#4f46e5", 700: "#4338ca",
        800: "#3730a3", 900: "#312e81", 950: "#1e1b4b",
    },
    "violet": {
        50: "#f5f3ff", 100: "#ede9fe", 200: "#ddd6fe", 300: "#c4b5fd",
        400: "#a78bfa", 500: "#8b5cf6", 600: "#7c3aed", 700: "#6d28d9",
        800: "#5b21b6", 900: "#4c1d95", 950: "#2e1065",
    },
    "purple": {
        50: "#faf5ff", 100: "#f3e8ff", 200: "#e9d5ff", 300: "#d8b4fe",
        400: "#c084fc", 500: "#a855f7", 600: "#9333ea", 700: "#7e22ce",
        800: "#6b21a8", 900: "#581c87", 950: "#3b0764",
    },
    "fuchsia": {
        50: "#fdf4ff", 100: "#fae8ff", 200: "#f5d0fe", 300: "#f0abfc",
        400: "#e879f9", 500: "#d946ef", 600: "#c026d3", 700: "#a21caf",
        800: "#86198f", 900: "#701a75", 950: "#4a044e",
    },
    "pink": {
        50: "#fdf2f8", 100: "#fce7f3", 200: "#fbcfe8", 300: "#f9a8d4",
        400: "#f472b6", 500: "#ec4899", 600: "#db2777", 700: "#be185d",
        800: "#9d174d", 900: "#831843", 950: "#500724",
    },
    "rose": {
        50: "#fff1f2", 100: "#ffe4e6", 200: "#fecdd3", 300: "#fda4af",
        400: "#fb7185", 500: "#f43f5e", 600: "#e11d48", 700: "#be123c",
        800: "#9f1239", 900: "#881337", 950: "#4c0519",
    },
}

_ARIA_ROLES: set[str] = {
    "alert", "alertdialog", "application", "article", "banner", "blockquote", "button",
    "caption", "cell", "checkbox", "code", "columnheader", "combobox", "command",
    "complementary", "composite", "contentinfo", "definition", "dialog", "directory",
    "document", "feed", "figure", "form", "grid", "gridcell", "group", "heading", "img",
    "input", "landmark", "link", "list", "listbox", "listitem", "log", "main", "marquee",
    "math", "menu", "menubar", "menuitem", "menuitemcheckbox", "menuitemradio", "navigation",
    "none", "note", "option", "presentation", "progressbar", "radio", "radiogroup", "range",
    "region", "roletype", "row", "rowgroup", "rowheader", "scrollbar", "search", "searchbox",
    "section", "sectionhead", "select", "separator", "slider", "spinbutton", "status",
    "strong", "structure", "subscript", "superscript", "switch", "tab", "table", "tablist",
    "tabpanel", "term", "textbox", "time", "timer", "toolbar", "tooltip", "tree", "treegrid",
    "treeitem", "widget", "window",
}

_ARIA_REQUIRED_ATTRS: dict[str, list[str]] = {
    "checkbox": ["aria-checked"],
    "combobox": ["aria-expanded"],
    "menuitemcheckbox": ["aria-checked"],
    "menuitemradio": ["aria-checked"],
    "progressbar": ["aria-valuenow", "aria-valuemin", "aria-valuemax"],
    "radio": ["aria-checked"],
    "scrollbar": ["aria-valuenow", "aria-valuemin", "aria-valuemax"],
    "slider": ["aria-valuenow", "aria-valuemin", "aria-valuemax"],
    "spinbutton": ["aria-valuenow", "aria-valuemin", "aria-valuemax"],
    "switch": ["aria-checked"],
    "tab": ["aria-selected"],
    "treeitem": ["aria-selected", "aria-expanded"],
}

# Valid aria-* attributes per ARIA 1.2 (common set).
_ARIA_GLOBAL_ATTRS: set[str] = {
    "aria-atomic", "aria-autocomplete", "aria-busy", "aria-checked", "aria-colcount",
    "aria-colindex", "aria-colspan", "aria-controls", "aria-current", "aria-describedby",
    "aria-details", "aria-disabled", "aria-dropeffect", "aria-errormessage", "aria-expanded",
    "aria-flowto", "aria-grabbed", "aria-haspopup", "aria-hidden", "aria-invalid", "aria-keyshortcuts",
    "aria-label", "aria-labelledby", "aria-level", "aria-live", "aria-modal", "aria-multiline",
    "aria-multiselectable", "aria-orientation", "aria-owns", "aria-placeholder", "aria-posinset",
    "aria-pressed", "aria-readonly", "aria-relevant", "aria-required", "aria-roledescription",
    "aria-rowcount", "aria-rowindex", "aria-rowspan", "aria-selected", "aria-setsize",
    "aria-sort", "aria-valuemax", "aria-valuemin", "aria-valuenow", "aria-valuetext",
}

_ROLE_REQUIREMENTS = _ARIA_REQUIRED_ATTRS


class AccessibilityEngine:
    def __init__(self, target_dir: Path | str, config: AccessibilityConfig | None = None):
        self.target_dir = Path(target_dir).resolve()
        self.config = config or AccessibilityConfig()
        self.config.target_dir = self.target_dir
        self.palette: dict[str, str] = {}
        self.css_vars: dict[str, str] = {}
        self._ids: dict[str, list[tuple[str, int]]] = {}
        self._id_refs: list[tuple[str, int, str]] = []

    def run(self) -> AccessibilityReport:
        start = time.perf_counter()
        report = AccessibilityReport()

        validation_errors = self.config.validate()
        if validation_errors:
            for err in validation_errors:
                report.issues.append(
                    AccessibilityIssue(
                        file="",
                        line=0,
                        check="config",
                        severity="error",
                        message=err,
                        suggestion="Fix AccessibilityConfig before running the engine",
                    )
                )
            report.passed = False
            report.duration_seconds = round(time.perf_counter() - start, 3)
            return report

        self._load_palette()
        files = self._discover_files()
        report.files_audited = [str(f.relative_to(self.target_dir)) for f in files]

        # First pass: collect all ids and aria-describedby/labelledby references.
        for file_path in files:
            self._collect_ids(file_path)

        # Second pass: audit.
        for file_path in files:
            self._audit_file(file_path, report)

        self._report_duplicate_ids(report)
        self._report_missing_id_refs(report)

        report.score = self._compute_score(report)
        report.passed = report.score >= 1.0 and not any(
            i.severity == "error" for i in report.issues
        )
        report.duration_seconds = round(time.perf_counter() - start, 3)
        return report

    def _discover_files(self) -> list[Path]:
        extensions = (".tsx", ".jsx", ".ts", ".js")
        candidates: list[Path] = []
        for ext in extensions:
            candidates.extend(self.target_dir.rglob(f"*{ext}"))
        files = [p for p in candidates if self.config.file_matches(p)]
        # Remove node_modules-like paths defensively even if globs missed them.
        files = [
            p
            for p in files
            if "node_modules" not in p.parts
            and ".next" not in p.parts
            and "coverage" not in p.parts
            and "dist" not in p.parts
        ]
        files = sorted(set(files))[: self.config.max_files]
        return files

    def _load_palette(self) -> None:
        for family, shades in _TAILWIND_SHADES.items():
            for shade, hex_value in shades.items():
                self.palette[f"{family}-{shade}"] = hex_value
        self.palette["white"] = "#ffffff"
        self.palette["black"] = "#000000"
        self.palette["transparent"] = "#00000000"
        self.palette["current"] = ""
        self.palette["inherit"] = ""

        for ext in (".ts", ".js", ".mjs"):
            config_path = self.target_dir / f"tailwind.config{ext}"
            if config_path.exists():
                self._parse_tailwind_config(config_path)
                break

        css_path = self.target_dir / "app" / "globals.css"
        if not css_path.exists():
            css_path = self.target_dir / "src" / "app" / "globals.css"
        if css_path.exists():
            self._parse_globals_css(css_path)

    def _parse_tailwind_config(self, path: Path) -> None:
        try:
            text = path.read_text(encoding="utf-8")
            self._extract_json_like_colors(text)
        except Exception:
            pass

    def _extract_json_like_colors(self, text: str) -> None:
        match = re.search(r'["\']colors["\']\s*:\s*\{([^}]+)\}', text, re.DOTALL)
        if not match:
            match = re.search(r'colors\s*:\s*\{', text)
            if not match:
                return
            start = match.end()
            depth = 1
            pos = start
            while pos < len(text) and depth > 0:
                if text[pos] == "{":
                    depth += 1
                elif text[pos] == "}":
                    depth -= 1
                pos += 1
            block = text[start:pos]
        else:
            block = match.group(1)

        for line in block.splitlines():
            kv = re.match(
                r"\s*['\"]?([A-Za-z0-9_\-]+)['\"]?\s*:\s*['\"]?(#[0-9a-fA-F]{3,8}|\w+-\d+|\w+)['\"]?",
                line,
            )
            if kv:
                key, value = kv.group(1), kv.group(2)
                resolved = self._resolve_color(value)
                if resolved:
                    self.palette[key] = resolved

    def _parse_globals_css(self, path: Path) -> None:
        try:
            text = path.read_text(encoding="utf-8")
            for match in re.finditer(r"--([\w\-]+)\s*:\s*([^;]+)", text):
                var_name = f"--{match.group(1)}"
                self.css_vars[var_name] = match.group(2).strip()
        except Exception:
            pass

    def _resolve_color(self, value: str) -> str | None:
        value = value.strip().strip('"').strip("'")
        if not value or value in ("current", "inherit", "transparent"):
            return None
        if re.match(r"^#[0-9a-fA-F]{3,8}$", value):
            return value
        if value in self.palette:
            resolved = self.palette[value]
            if resolved and resolved not in ("current", "inherit", "transparent", ""):
                return resolved
        if re.match(r"^\w+-\d+$", value):
            return self.palette.get(value)
        if value.startswith("var("):
            var_name = value[4:].rstrip(")").strip()
            resolved = self.css_vars.get(var_name)
            if resolved:
                return self._resolve_color(resolved)
            return None
        if value.startswith("rgb(") or value.startswith("rgba("):
            return _rgb_to_hex(value)
        if value.startswith("hsl(") or value.startswith("hsla("):
            return _hsl_to_hex(value)
        # Known CSS named colors (minimal set)
        named = {
            "white": "#ffffff",
            "black": "#000000",
            "red": "#ff0000",
            "green": "#008000",
            "blue": "#0000ff",
            "yellow": "#ffff00",
        }
        if value.lower() in named:
            return named[value.lower()]
        return None

    def _collect_ids(self, path: Path) -> None:
        try:
            text = path.read_text(encoding="utf-8")
            rel_path = str(path.relative_to(self.target_dir))
        except Exception:
            return
        for match in re.finditer(
            r'\bid\s*=\s*(?:["\']([^"\']+)["\']|\{\s*["\']([^"\']+)["\']\s*\})',
            text,
        ):
            id_value = match.group(1) or match.group(2)
            line_no = text.count("\n", 0, match.start()) + 1
            self._ids.setdefault(id_value, []).append((rel_path, line_no))

        for match in re.finditer(
            r'\baria-(describedby|labelledby)\s*=\s*(?:["\']([^"\']+)["\']|\{\s*["\']([^"\']+)["\']\s*\})',
            text,
        ):
            ref_id = match.group(2) or match.group(3)
            line_no = text.count("\n", 0, match.start()) + 1
            self._id_refs.append((rel_path, line_no, ref_id))

    def _audit_file(self, path: Path, report: AccessibilityReport) -> None:
        try:
            text = path.read_text(encoding="utf-8")
            rel_path = str(path.relative_to(self.target_dir))
        except Exception:
            return

        lines = text.splitlines()
        enabled = set(self.config.checks)

        for idx, raw_line in enumerate(lines, start=1):
            line = raw_line.strip()
            if not line:
                continue

            if CheckType.CONTRAST.value in enabled:
                self._check_contrast(line, rel_path, idx, report)
            if CheckType.FOCUS_VISIBLE.value in enabled:
                self._check_focus_visible(line, rel_path, idx, report)
            if CheckType.FOCUS_ORDER.value in enabled:
                self._check_focus_order(line, rel_path, idx, report)
            if CheckType.ARIA.value in enabled:
                self._check_aria(line, rel_path, idx, report)
            if CheckType.KEYBOARD_TRAP.value in enabled:
                self._check_keyboard_trap(line, rel_path, idx, text, report)
            if CheckType.ALT_TEXT.value in enabled:
                self._check_alt_text(line, rel_path, idx, report)
            if CheckType.FORM_LABEL.value in enabled:
                self._check_form_label(line, rel_path, idx, report)

        if CheckType.HEADING_HIERARCHY.value in enabled:
            self._check_heading_hierarchy(text, rel_path, report)

    def _check_contrast(self, line: str, file: str, line_no: int, report: AccessibilityReport) -> None:
        # Tailwind className pair
        class_match = re.search(r'className\s*=\s*["\']([^"\']+)["\']', line)
        if class_match:
            classes = class_match.group(1).split()
            text_color = None
            bg_colors: list[str] = []
            is_large = any(c in classes for c in ("text-lg", "text-xl", "text-2xl", "text-3xl", "text-4xl", "text-5xl", "text-6xl"))
            for cls in classes:
                if cls.startswith("text-"):
                    candidate = cls[5:]
                    resolved = self._resolve_color(candidate)
                    if resolved:
                        text_color = resolved
                elif cls.startswith("bg-"):
                    candidate = cls[3:]
                    resolved = self._resolve_color(candidate)
                    if resolved:
                        bg_colors.append(resolved)
                elif cls.startswith("from-"):
                    candidate = cls[5:]
                    resolved = self._resolve_color(candidate)
                    if resolved:
                        bg_colors.append(resolved)
                elif cls.startswith("to-"):
                    candidate = cls[3:]
                    resolved = self._resolve_color(candidate)
                    if resolved:
                        bg_colors.append(resolved)

            if text_color and bg_colors:
                threshold = self.config.contrast_threshold_large if is_large else self.config.contrast_threshold_normal
                worst = min(contrast_ratio(text_color, bg) for bg in bg_colors)
                if worst < threshold:
                    report.issues.append(
                        AccessibilityIssue(
                            file=file,
                            line=line_no,
                            check=CheckType.CONTRAST.value,
                            severity="warning",
                            message=f"Contrast ratio {worst:.2f}:1 below {threshold}:1 for text {text_color} on background",
                            suggestion="Increase foreground/background color contrast to meet WCAG 2.1 AA",
                        )
                    )

        # Inline style pair
        style_match = re.search(r'style\s*=\s*\{\{([^}]+)\}\}', line)
        if style_match:
            style_block = style_match.group(1)
            fg = self._extract_style_color(style_block, r'color\s*:\s*["\']?([^,\}]+)')
            bg = self._extract_style_color(style_block, r'background(?:Color)?\s*:\s*["\']?([^,\}]+)')
            if fg and bg:
                threshold = self.config.contrast_threshold_normal
                ratio = contrast_ratio(fg, bg)
                if ratio < threshold:
                    report.issues.append(
                        AccessibilityIssue(
                            file=file,
                            line=line_no,
                            check=CheckType.CONTRAST.value,
                            severity="warning",
                            message=f"Inline style contrast ratio {ratio:.2f}:1 below {threshold}:1",
                            suggestion="Increase color contrast in inline styles",
                        )
                    )

    def _extract_style_color(self, style_block: str, pattern: str) -> str | None:
        match = re.search(pattern, style_block)
        if not match:
            return None
        value = match.group(1).strip().strip('"').strip("'")
        return self._resolve_color(value)

    def _check_focus_visible(self, line: str, file: str, line_no: int, report: AccessibilityReport) -> None:
        if not re.search(r'<(button|a|input|select|textarea)\b', line):
            return
        class_match = re.search(r'className\s*=\s*["\']([^"\']+)["\']', line)
        cls = class_match.group(1) if class_match else ""
        has_focus = (
            "focus-visible:" in cls
            or "focus-visible" in cls
            or "focus:" in cls
            or re.search(r'\bfocus:outline-\w+', cls)
            or re.search(r'\bfocus:ring-\w+', cls)
        )
        if not has_focus:
            report.issues.append(
                AccessibilityIssue(
                    file=file,
                    line=line_no,
                    check=CheckType.FOCUS_VISIBLE.value,
                    severity="warning",
                    message="Interactive element missing visible focus indicator",
                    suggestion="Add focus-visible: or focus:outline-/focus:ring- Tailwind classes",
                )
            )

    def _check_focus_order(self, line: str, file: str, line_no: int, report: AccessibilityReport) -> None:
        for match in re.finditer(r'tabIndex\s*=\s*\{?\s*(\d+)\s*\}?', line):
            value = int(match.group(1))
            if value > 0:
                report.issues.append(
                    AccessibilityIssue(
                        file=file,
                        line=line_no,
                        check=CheckType.FOCUS_ORDER.value,
                        severity="warning",
                        message=f"Positive tabIndex ({value}) disrupts natural focus order",
                        suggestion="Remove tabIndex or use tabIndex={{0}} for custom focusable widgets",
                    )
                )
        for match in re.finditer(r'tabindex\s*=\s*["\'](\d+)["\']', line):
            value = int(match.group(1))
            if value > 0:
                report.issues.append(
                    AccessibilityIssue(
                        file=file,
                        line=line_no,
                        check=CheckType.FOCUS_ORDER.value,
                        severity="warning",
                        message=f"Positive tabindex ({value}) disrupts natural focus order",
                        suggestion="Remove tabindex or use tabindex=\"0\" for custom focusable widgets",
                    )
                )

    def _check_aria(self, line: str, file: str, line_no: int, report: AccessibilityReport) -> None:
        # Invalid role names
        for match in re.finditer(r'role\s*=\s*(?:["\']([^"\']+)["\']|\{\s*["\']([^"\']+)["\']\s*\})', line):
            role = (match.group(1) or match.group(2)).strip()
            if role not in _ARIA_ROLES:
                report.issues.append(
                    AccessibilityIssue(
                        file=file,
                        line=line_no,
                        check=CheckType.ARIA.value,
                        severity="warning",
                        message=f"Invalid ARIA role: {role}",
                        suggestion="Use a valid ARIA role or remove the role attribute",
                    )
                )
            else:
                required = _ROLE_REQUIREMENTS.get(role, [])
                missing = [attr for attr in required if attr not in line]
                for attr in missing:
                    report.issues.append(
                        AccessibilityIssue(
                            file=file,
                            line=line_no,
                            check=CheckType.ARIA.value,
                            severity="warning",
                            message=f"Role {role} requires {attr}",
                            suggestion=f"Add {attr} to the element with role={role}",
                        )
                    )

        # Unknown aria-* attributes
        for match in re.finditer(r'\b(aria-[a-zA-Z-]+)\s*=', line):
            attr = match.group(1).lower()
            if attr not in _ARIA_GLOBAL_ATTRS:
                report.issues.append(
                    AccessibilityIssue(
                        file=file,
                        line=line_no,
                        check=CheckType.ARIA.value,
                        severity="warning",
                        message=f"Unknown aria-* attribute: {attr}",
                        suggestion="Use a valid ARIA attribute name",
                    )
                )

        # Accessible name for icon-only buttons/links
        for tag in ("button", "a"):
            if re.search(rf'<{tag}\b', line):
                has_label = bool(
                    re.search(r'aria-label\s*=', line)
                    or re.search(r'aria-labelledby\s*=', line)
                    or re.search(r'title\s*=', line)
                )
                has_visible_text = bool(re.search(rf'>{1,3}\w', line))  # crude visible text heuristic
                has_icon = bool(re.search(r'<svg\b|<\w+[^>]*icon', line))
                is_self_closing = line.endswith("/>")
                if not has_label and (is_self_closing or has_icon or not has_visible_text):
                    report.issues.append(
                        AccessibilityIssue(
                            file=file,
                            line=line_no,
                            check=CheckType.ARIA.value,
                            severity="warning",
                            message=f"<{tag}> may lack an accessible name",
                            suggestion="Add aria-label, aria-labelledby, or visible text describing the control purpose",
                        )
                    )

    def _check_keyboard_trap(self, line: str, file: str, line_no: int, text: str, report: AccessibilityReport) -> None:
        # Custom interactive div missing keyboard activation.
        if "<div" in line and "onClick=" in line:
            has_role = bool(re.search(r'role\s*=\s*["\'](button|link)["\']', line))
            has_tabindex = bool(re.search(r'tabIndex\s*=\s*\{?\s*0\s*\}?', line)) or bool(
                re.search(r'tabindex\s*=\s*["\']0["\']', line)
            )
            has_keydown = bool(re.search(r'onKeyDown\s*=|onKeyUp\s*=|onKeyPress\s*=', line))
            if has_role and has_tabindex and not has_keydown:
                report.issues.append(
                    AccessibilityIssue(
                        file=file,
                        line=line_no,
                        check=CheckType.KEYBOARD_TRAP.value,
                        severity="warning",
                        message="Custom interactive div is focusable but has no keyboard activation handler",
                        suggestion="Add onKeyDown handling Enter/Space, or use a native <button> element",
                    )
                )

        # Keyboard event handlers that never handle Tab or Escape at file level.
        if re.search(r'onKeyDown\s*=|onKeyUp\s*=', line):
            if "Tab" not in line and "Escape" not in line:
                report.issues.append(
                    AccessibilityIssue(
                        file=file,
                        line=line_no,
                        check=CheckType.KEYBOARD_TRAP.value,
                        severity="info",
                        message="onKeyDown/onKeyUp handler without Tab or Escape handling — verify no keyboard trap",
                        suggestion="Ensure users can Tab away and press Escape to exit custom widgets",
                    )
                )

        # addEventListener('keydown' ... without Tab/Escape handling anywhere in the file.
        if re.search(r'addEventListener\s*\(\s*["\']keydown["\']', line):
            if "Tab" not in text and "Escape" not in text:
                report.issues.append(
                    AccessibilityIssue(
                        file=file,
                        line=line_no,
                        check=CheckType.KEYBOARD_TRAP.value,
                        severity="warning",
                        message="Global keydown listener lacks Tab/Escape handling — potential keyboard trap",
                        suggestion="Handle Tab and Escape, or remove the global listener",
                    )
                )

    def _check_alt_text(self, line: str, file: str, line_no: int, report: AccessibilityReport) -> None:
        if not re.search(r'<img\b|<Image\b', line):
            return
        has_alt = bool(re.search(r'\salt\s*=\s*["\']', line)) or bool(re.search(r'\salt\s*=\s*\{', line))
        has_aria_label = bool(re.search(r'aria-label\s*=', line))
        aria_hidden = bool(re.search(r'aria-hidden\s*=\s*["\']true["\']', line))
        role_presentation = bool(re.search(r'role\s*=\s*["\'](presentation|none)["\']', line))
        if not has_alt and not has_aria_label and not aria_hidden and not role_presentation:
            report.issues.append(
                AccessibilityIssue(
                    file=file,
                    line=line_no,
                    check=CheckType.ALT_TEXT.value,
                    severity="warning",
                    message="Image missing alt text or accessible label",
                    suggestion="Add descriptive alt text, aria-label, or mark aria-hidden='true' for decorative images",
                )
            )

    def _check_form_label(self, line: str, file: str, line_no: int, report: AccessibilityReport) -> None:
        if re.search(r'<(input|select|textarea)\b', line):
            has_id = bool(re.search(r'\sid\s*=\s*["\']', line))
            has_aria = bool(re.search(r'aria-label\s*=|aria-labelledby\s*=', line))
            has_placeholder = bool(re.search(r'placeholder\s*=\s*["\'][^"\']+["\']', line))
            if not (has_id or has_aria or has_placeholder):
                report.issues.append(
                    AccessibilityIssue(
                        file=file,
                        line=line_no,
                        check=CheckType.FORM_LABEL.value,
                        severity="warning",
                        message="Form control lacks id, aria-label, or placeholder",
                        suggestion="Add id paired with a <label htmlFor> or use aria-label",
                    )
                )

    def _check_heading_hierarchy(self, text: str, file: str, report: AccessibilityReport) -> None:
        headings: list[tuple[int, int]] = []
        for idx, line in enumerate(text.splitlines(), start=1):
            for match in re.finditer(r'<(h[1-6])\b', line):
                level = int(match.group(1)[1])
                headings.append((level, idx))
        prev = 0
        for level, line_no in headings:
            if prev and level > prev + 1:
                report.issues.append(
                    AccessibilityIssue(
                        file=file,
                        line=line_no,
                        check=CheckType.HEADING_HIERARCHY.value,
                        severity="warning",
                        message=f"Heading skipped from h{prev} to h{level}",
                        suggestion=f"Insert h{prev + 1} before h{level} or restructure headings",
                    )
                )
            prev = level

    def _report_duplicate_ids(self, report: AccessibilityReport) -> None:
        for id_value, occurrences in self._ids.items():
            if len(occurrences) <= 1:
                continue
            for file, line_no in occurrences:
                report.issues.append(
                    AccessibilityIssue(
                        file=file,
                        line=line_no,
                        check=CheckType.ARIA.value,
                        severity="warning",
                        message=f"Duplicate id: {id_value}",
                        suggestion="Ensure ids are unique across the page",
                    )
                )

    def _report_missing_id_refs(self, report: AccessibilityReport) -> None:
        for file, line_no, ref_id in self._id_refs:
            if ref_id not in self._ids:
                report.issues.append(
                    AccessibilityIssue(
                        file=file,
                        line=line_no,
                        check=CheckType.ARIA.value,
                        severity="warning",
                        message=f"aria-describedby/labelledby references missing id: {ref_id}",
                        suggestion="Add the referenced id to an element, or correct the attribute value",
                    )
                )

    def _compute_score(self, report: AccessibilityReport) -> float:
        checks_run = set(self.config.checks)
        failed = {i.check for i in report.issues if i.check != "config"}
        passed = checks_run - failed
        report.passed_checks = sorted(passed)
        report.failed_checks = sorted(failed)
        if not checks_run:
            return 0.0
        return round(len(passed) / len(checks_run), 2)


def hex_to_luminance(hex_color: str) -> float:
    hex_color = hex_color.lstrip("#")
    if len(hex_color) == 3:
        hex_color = "".join(c * 2 for c in hex_color)
    if len(hex_color) == 4:
        hex_color = "".join(c * 2 for c in hex_color)
    if len(hex_color) not in (6, 8):
        return 0.0
    r = int(hex_color[0:2], 16) / 255
    g = int(hex_color[2:4], 16) / 255
    b = int(hex_color[4:6], 16) / 255
    r = r / 12.92 if r <= 0.03928 else ((r + 0.055) / 1.055) ** 2.4
    g = g / 12.92 if g <= 0.03928 else ((g + 0.055) / 1.055) ** 2.4
    b = b / 12.92 if b <= 0.03928 else ((b + 0.055) / 1.055) ** 2.4
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast_ratio(a: str, b: str) -> float:
    lum_a = hex_to_luminance(a)
    lum_b = hex_to_luminance(b)
    lighter = max(lum_a, lum_b)
    darker = min(lum_a, lum_b)
    if lighter == darker == 0:
        return 1.0
    return round((lighter + 0.05) / (darker + 0.05), 2)


def _rgb_to_hex(value: str) -> str | None:
    match = re.match(r'rgba?\s*\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)(?:\s*,\s*[\d.]+)?\s*\)', value)
    if not match:
        return None
    r, g, b = (int(x) for x in match.groups())
    return f"#{r:02x}{g:02x}{b:02x}"


def _hsl_to_hex(value: str) -> str | None:
    match = re.match(r'hsla?\s*\(\s*(\d+)\s*,\s*(\d+)%\s*,\s*(\d+)%(?:\s*,\s*[\d.]+)?\s*\)', value)
    if not match:
        return None
    h, s, l = int(match.group(1)), int(match.group(2)) / 100, int(match.group(3)) / 100
    return _hsl_to_rgb_hex(h, s, l)


def _hsl_to_rgb_hex(h: int, s: float, l: float) -> str:
    c = (1 - abs(2 * l - 1)) * s
    x = c * (1 - abs((h / 60) % 2 - 1))
    m = l - c / 2
    if h < 60:
        r1, g1, b1 = c, x, 0
    elif h < 120:
        r1, g1, b1 = x, c, 0
    elif h < 180:
        r1, g1, b1 = 0, c, x
    elif h < 240:
        r1, g1, b1 = 0, x, c
    elif h < 300:
        r1, g1, b1 = x, 0, c
    else:
        r1, g1, b1 = c, 0, x
    r = int((r1 + m) * 255)
    g = int((g1 + m) * 255)
    b = int((b1 + m) * 255)
    return f"#{r:02x}{g:02x}{b:02x}"
