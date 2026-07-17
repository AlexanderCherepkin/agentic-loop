from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .config import DEFAULT_ANTI_SLOP_RULES, PremiumDesignConfig


@dataclass
class AntiSlopCheck:
    id: str
    name: str
    status: str  # "pass" or "fail"
    reason: str


@dataclass
class PremiumDesignResult:
    design_md_path: str = ""
    tokens_path: str = ""
    status: str = "pending"  # pending | pass | fail | error
    anti_slop_checks: list[AntiSlopCheck] = field(default_factory=list)
    refinement_actions: list[str] = field(default_factory=list)
    errors: list[dict[str, Any]] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


class PremiumDesignEngine:
    def __init__(self, target_dir: Path | str, config: PremiumDesignConfig | None = None):
        self.target_dir = Path(target_dir).resolve()
        self.config = config or PremiumDesignConfig()
        self.config.target_dir = self.target_dir
        self.result = PremiumDesignResult()

    def write_artifacts(
        self,
        design_md_content: str,
        tokens: dict[str, Any],
    ) -> PremiumDesignResult:
        validation_errors = self.config.validate()
        if validation_errors:
            for err in validation_errors:
                self.result.errors.append({"file": "", "reason": err})
            self.result.status = "error"
            return self.result

        design_path = self.target_dir / self.config.design_md_name
        tokens_path = self.target_dir / self.config.tokens_name

        try:
            design_path.parent.mkdir(parents=True, exist_ok=True)
            design_path.write_text(design_md_content, encoding="utf-8")
            self.result.design_md_path = str(design_path.relative_to(self.target_dir))
        except Exception as exc:
            self.result.errors.append({"file": str(design_path), "reason": str(exc)})
            self.result.status = "error"
            return self.result

        try:
            tokens_path.parent.mkdir(parents=True, exist_ok=True)
            tokens_path.write_text(_stable_json(tokens), encoding="utf-8")
            self.result.tokens_path = str(tokens_path.relative_to(self.target_dir))
        except Exception as exc:
            self.result.errors.append({"file": str(tokens_path), "reason": str(exc)})
            self.result.status = "error"
            return self.result

        self.result = self._run_anti_slop(str(design_path), str(tokens_path))
        return self.result

    def validate_existing(self, design_md_path: Path | str, tokens_path: Path | str) -> PremiumDesignResult:
        self.result = self._run_anti_slop(str(design_md_path), str(tokens_path))
        return self.result

    def _run_anti_slop(self, design_md_path: str, tokens_path: str) -> PremiumDesignResult:
        self.result.design_md_path = design_md_path
        self.result.tokens_path = tokens_path

        try:
            design_text = Path(design_md_path).read_text(encoding="utf-8")
        except Exception as exc:
            self.result.errors.append({"file": design_md_path, "reason": str(exc)})
            self.result.status = "error"
            return self.result

        try:
            tokens = json.loads(Path(tokens_path).read_text(encoding="utf-8"))
        except Exception as exc:
            self.result.errors.append({"file": tokens_path, "reason": str(exc)})
            self.result.status = "error"
            return self.result

        combined_text = f"{design_text}\n{json.dumps(tokens, ensure_ascii=False)}"
        lower_text = combined_text.lower()

        checks: list[AntiSlopCheck] = []
        any_fail = False

        for rule in self.config.anti_slop_rules:
            check_id = rule["id"]
            name = rule["name"]
            status = "pass"
            reason = "OK"

            if check_id == "fonts":
                # Check font families only, not fallback stacks or prose.
                font_families: list[str] = []
                fonts_section = tokens.get("fonts", {})
                if isinstance(fonts_section, dict):
                    for role_cfg in fonts_section.values():
                        if isinstance(role_cfg, dict) and role_cfg.get("family"):
                            font_families.append(str(role_cfg["family"]).strip())
                # Also inspect explicit fontFamily keys in design tokens if present.
                for key in ("display_font", "body_font", "accent_font", "mono_font"):
                    if key in tokens and isinstance(tokens[key], str):
                        font_families.append(tokens[key].strip())

                forbidden_found = []
                for family in font_families:
                    family_lower = family.lower()
                    for forbidden in self.config.forbidden_fonts:
                        # Match exact font name or whole-word token; avoid matching substrings inside longer names.
                        if family_lower == forbidden.lower() or re.search(
                            rf"(?<![a-z0-9\-]){re.escape(forbidden.lower())}(?![a-z0-9\-])",
                            family_lower,
                        ):
                            forbidden_found.append(forbidden)
                forbidden_found = list(dict.fromkeys(forbidden_found))  # preserve order, dedupe
                if forbidden_found:
                    status = "fail"
                    reason = f"Forbidden/default fonts found: {', '.join(forbidden_found[:5])}"
                    self.result.refinement_actions.append(
                        f"Replace forbidden/default fonts ({', '.join(forbidden_found[:5])}) with allowed alternatives from premium-design config."
                    )

            elif check_id == "card_shadows":
                patterns = rule.get("forbidden_patterns", [])
                # Normalize JSON escaping (rgba(0,0,0 -> rgba(0, 0, 0) and allow spaces.
                normalized_text = combined_text.replace(",", ", ").replace("  ", " ")
                matches = [p for p in patterns if re.search(p, normalized_text, re.IGNORECASE)]
                if matches:
                    status = "fail"
                    reason = f"Decorative card shadows detected: {matches}"
                    self.result.refinement_actions.append("Remove decorative box-shadows from card concepts; use elevation only for focus/interaction states.")

            elif check_id == "centered_buttons":
                forbidden = [p for p in rule.get("forbidden_phrases", []) if p.lower() in lower_text]
                if forbidden:
                    allowed = rule.get("allowed_if", [])
                    if not any(a.lower() in lower_text for a in allowed):
                        status = "fail"
                        reason = f"Centered button language without hierarchy rationale: {forbidden}"
                        self.result.refinement_actions.append("Add hierarchy/asymmetry rationale for centered CTAs or align them within the grid.")

            elif check_id == "gradient_blobs":
                forbidden = [p for p in rule.get("forbidden_phrases", []) if p.lower() in lower_text]
                if forbidden:
                    status = "fail"
                    reason = f"Meaningless gradient blobs: {forbidden}"
                    self.result.refinement_actions.append("Remove decorative gradient blobs or give them functional meaning (data viz, depth).")

            elif check_id == "uniform_padding":
                spacing = tokens.get("spacing", {})
                scale = spacing.get("scale", [])
                if len(set(str(x) for x in scale)) < rule.get("min_distinct_levels", 3):
                    status = "fail"
                    reason = "Spacing scale has too few distinct rhythmic levels"
                    self.result.refinement_actions.append("Introduce ≥3 distinct spacing levels with intentional rhythm, not uniform 8px steps.")

            elif check_id == "generic_3col":
                if "3 column" in lower_text or "three column" in lower_text or "3-col" in lower_text:
                    required = rule.get("required_if_mentioned", [])
                    if not any(r.lower() in lower_text for r in required):
                        status = "fail"
                        reason = "Generic 3-column layout without asymmetry/disruption rule"
                        self.result.refinement_actions.append("Add asymmetric grid rule or intentional disruption to 3-column layout concept.")

            elif check_id == "gray_on_white":
                text_re = rule.get("forbidden_combo", {}).get("text", "")
                bg_re = rule.get("forbidden_combo", {}).get("bg", "")
                colors = tokens.get("colors", {})

                def _collect_strings(obj: Any) -> list[str]:
                    out: list[str] = []
                    if isinstance(obj, str):
                        out.append(obj)
                    elif isinstance(obj, dict):
                        for v in obj.values():
                            out.extend(_collect_strings(v))
                    elif isinstance(obj, list):
                        for item in obj:
                            out.extend(_collect_strings(item))
                    return out

                text_colors = [s for s in _collect_strings(colors) if "text" in str(colors).lower()]
                # More precise: collect values nested under keys containing 'text'.
                def _collect_under_key(obj: Any, key_filter: str) -> list[str]:
                    out: list[str] = []
                    if isinstance(obj, dict):
                        for k, v in obj.items():
                            if key_filter in k.lower():
                                out.extend(_collect_strings(v))
                            else:
                                out.extend(_collect_under_key(v, key_filter))
                    return out

                text_colors = _collect_under_key(colors, "text")
                bg_colors = _collect_under_key(colors, "background") + _collect_under_key(colors, "bg")
                gray_text = any(re.search(text_re, str(c), re.IGNORECASE) for c in text_colors)
                pure_white_bg = any(re.search(bg_re, str(c), re.IGNORECASE) for c in bg_colors)
                if gray_text and pure_white_bg:
                    status = "fail"
                    reason = "Flat gray text on pure white background detected"
                    self.result.refinement_actions.append("Shift body text to warm/cool off-white palette or invert contrast; avoid flat mid-gray on #fff.")

            elif check_id == "layout_animations":
                motion = tokens.get("motion", {})
                allowed = set(motion.get("allowed_properties", []))
                forbidden = set(rule.get("forbidden_properties", []))
                if forbidden.intersection(allowed):
                    status = "fail"
                    reason = "Layout properties (width/height/top/left) listed as animatable"
                    self.result.refinement_actions.append("Restrict motion tokens to transform, opacity, filter, clip-path only.")

            elif check_id == "hover_banality":
                components = tokens.get("components", {})
                hover_text = json.dumps(components.get("button", {})).lower()
                if "opacity" in hover_text and not any(x in hover_text for x in ("transform", "translate", "scale", "color shift", "underline")):
                    status = "fail"
                    reason = "Hover relies only on opacity change"
                    self.result.refinement_actions.append("Add transform, color shift, or underline logic to button hover concept.")

            elif check_id == "mass_fade_in":
                forbidden = [p for p in rule.get("forbidden_phrases", []) if p.lower() in lower_text]
                if forbidden:
                    allowed = rule.get("allowed_if", [])
                    if not any(a.lower() in lower_text for a in allowed):
                        status = "fail"
                        reason = f"Mass fade-in scroll trigger without stagger/transform: {forbidden}"
                        self.result.refinement_actions.append("Replace blanket fade-in with staggered transform-based animations with easing.")

            checks.append(AntiSlopCheck(id=check_id, name=name, status=status, reason=reason))
            if status == "fail":
                any_fail = True

        self.result.anti_slop_checks = checks
        self.result.status = "fail" if any_fail else "pass"

        # Update tokens file with verdict
        if self.result.status == "pass":
            tokens["anti_slop"] = tokens.get("anti_slop", {})
            tokens["anti_slop"]["verdict"] = "pass"
            tokens["anti_slop"]["checks"] = [{"id": c.id, "name": c.name, "status": c.status} for c in checks]
            try:
                Path(tokens_path).write_text(_stable_json(tokens), encoding="utf-8")
            except Exception as exc:
                self.result.errors.append({"file": tokens_path, "reason": f"Could not update anti_slop verdict: {exc}"})

        return self.result


def _stable_json(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, indent=2, sort_keys=True)
