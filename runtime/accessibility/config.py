from __future__ import annotations

import fnmatch
import re
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any


class CheckType(Enum):
    CONTRAST = "contrast"
    FOCUS_ORDER = "focus_order"
    ARIA = "aria"
    KEYBOARD_TRAP = "keyboard_trap"
    FOCUS_VISIBLE = "focus_visible"
    ALT_TEXT = "alt_text"
    FORM_LABEL = "form_label"
    HEADING_HIERARCHY = "heading_hierarchy"


class WcagLevel(Enum):
    WCAG21_A = "WCAG21_A"
    WCAG21_AA = "WCAG21_AA"
    WCAG21_AAA = "WCAG21_AAA"


DEFAULT_CHECKS: list[str] = [
    CheckType.CONTRAST.value,
    CheckType.FOCUS_VISIBLE.value,
    CheckType.FOCUS_ORDER.value,
    CheckType.ARIA.value,
    CheckType.KEYBOARD_TRAP.value,
    CheckType.ALT_TEXT.value,
    CheckType.FORM_LABEL.value,
    CheckType.HEADING_HIERARCHY.value,
]


@dataclass
class AccessibilityConfig:
    target_dir: Path | str = "."
    level: WcagLevel = WcagLevel.WCAG21_AA
    checks: list[str] = field(default_factory=lambda: DEFAULT_CHECKS.copy())
    contrast_threshold_normal: float = 4.5
    contrast_threshold_large: float = 3.0
    focusable_selector: str = "a, button, input, select, textarea, [tabindex]"
    include: list[str] = field(
        default_factory=lambda: [
            "src/**/*.{tsx,jsx,ts,js}",
            "app/**/*.{tsx,jsx,ts,js}",
            "components/**/*.{tsx,jsx,ts,js}",
        ]
    )
    exclude: list[str] = field(
        default_factory=lambda: ["node_modules", ".next", "out", "dist", "coverage"]
    )
    max_files: int = 500

    def __post_init__(self) -> None:
        self.target_dir = Path(self.target_dir)

    def validate(self) -> list[str]:
        errors: list[str] = []
        if not self.target_dir.exists():
            errors.append(f"target_dir does not exist: {self.target_dir}")
        if not isinstance(self.checks, list) or not self.checks:
            errors.append("checks must be a non-empty list")
        for c in self.checks:
            try:
                CheckType(c)
            except ValueError:
                errors.append(f"unknown check type: {c}")
        if not isinstance(self.level, WcagLevel):
            errors.append(f"unknown WCAG level: {self.level}")
        if self.contrast_threshold_normal <= 1.0:
            errors.append("contrast_threshold_normal must be > 1.0")
        if self.contrast_threshold_large <= 1.0:
            errors.append("contrast_threshold_large must be > 1.0")
        if not self.include:
            errors.append("include list is empty")
        if self.max_files < 1:
            errors.append("max_files must be >= 1")
        return errors

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AccessibilityConfig":
        raw_level = data.get("level", "WCAG21_AA")
        try:
            level = WcagLevel(raw_level)
        except ValueError:
            level = WcagLevel.WCAG21_AA
        checks = data.get("checks", DEFAULT_CHECKS.copy())
        if not isinstance(checks, list):
            checks = DEFAULT_CHECKS.copy()
        return cls(
            target_dir=data.get("target_dir", "."),
            level=level,
            checks=checks,
            contrast_threshold_normal=float(data.get("contrast_threshold_normal", 4.5)),
            contrast_threshold_large=float(data.get("contrast_threshold_large", 3.0)),
            focusable_selector=data.get(
                "focusable_selector", "a, button, input, select, textarea, [tabindex]"
            ),
            include=data.get(
                "include",
                [
                    "src/**/*.{tsx,jsx,ts,js}",
                    "app/**/*.{tsx,jsx,ts,js}",
                    "components/**/*.{tsx,jsx,ts,js}",
                ],
            ),
            exclude=data.get("exclude", ["node_modules", ".next", "out", "dist", "coverage"]),
            max_files=int(data.get("max_files", 500)),
        )

    def file_matches(self, path: Path) -> bool:
        rel = path.relative_to(self.target_dir).as_posix()
        for pattern in self.include:
            if _glob_match(rel, pattern):
                return not any(_glob_match(rel, exc) for exc in self.exclude)
        return False


def _glob_match(rel: str, pattern: str) -> bool:
    any_depth = False
    if pattern.startswith("**/"):
        any_depth = True
        pattern = pattern[3:]

    p_parts = pattern.split("/")
    rel_parts = rel.split("/")

    if any_depth:
        # The stripped pattern can start anywhere in the path.
        for start in range(len(rel_parts) + 1):
            if _match_parts(rel_parts[start:], p_parts):
                return True
        return False
    return _match_parts(rel_parts, p_parts)


def _match_parts(rel_parts: list[str], p_parts: list[str]) -> bool:
    if not p_parts:
        return not rel_parts
    if p_parts[0] == "**":
        # ** can swallow zero or more path segments.
        if len(p_parts) == 1:
            return True
        for k in range(len(rel_parts) + 1):
            if _match_parts(rel_parts[k:], p_parts[1:]):
                return True
        return False
    if not rel_parts:
        return False
    if not _fnmatch_with_braces(rel_parts[0], p_parts[0]):
        return False
    return _match_parts(rel_parts[1:], p_parts[1:])


def _fnmatch_with_braces(name: str, pattern: str) -> bool:
    # Expand simple brace groups and match against any option.
    if "{" not in pattern:
        return fnmatch.fnmatch(name, pattern)
    options = _expand_braces(pattern)
    return any(fnmatch.fnmatch(name, opt) for opt in options)


def _expand_braces(pattern: str) -> list[str]:
    # Simple brace expansion for the first brace group only; sufficient for file extensions.
    match = re.search(r"\{([^}]+)\}", pattern)
    if not match:
        return [pattern]
    prefix = pattern[: match.start()]
    suffix = pattern[match.end() :]
    return [f"{prefix}{opt}{suffix}" for opt in match.group(1).split(",")]
