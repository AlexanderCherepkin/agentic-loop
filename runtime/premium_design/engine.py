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

        # Precompute helper dicts once.
        colors_section = tokens.get("colors", {})
        fonts_section = tokens.get("fonts", {})
        font_family_section = tokens.get("fontFamily", {})
        spacing_section = tokens.get("spacing", {})
        motion_section = tokens.get("motion", {})
        components_section = tokens.get("components", {})

        for rule in self.config.anti_slop_rules:
            check_id = rule["id"]
            name = rule["name"]
            status = "pass"
            reason = "OK"

            allowed_if = rule.get("allowed_if", [])
            allowed_present = any(a.lower() in lower_text for a in allowed_if)

            if check_id == "fonts":
                font_families: list[str] = []
                if isinstance(fonts_section, dict):
                    for role_cfg in fonts_section.values():
                        if isinstance(role_cfg, dict) and role_cfg.get("family"):
                            font_families.append(str(role_cfg["family"]).strip())
                for key in ("display_font", "body_font", "accent_font", "mono_font"):
                    if key in tokens and isinstance(tokens[key], str):
                        font_families.append(tokens[key].strip())
                if isinstance(font_family_section, dict):
                    for role_token in font_family_section.values():
                        if isinstance(role_token, dict):
                            stack = role_token.get("$value", "")
                            if isinstance(stack, str):
                                # In DTCG fontFamily tokens the first family is the primary choice.
                                first_family = stack.split(",")[0].strip().strip("'\"")
                                font_families.append(first_family)

                forbidden_found: list[str] = []
                forbidden_lower_to_original = {f.lower(): f for f in self.config.forbidden_fonts}
                for family in font_families:
                    family_lower = family.lower()
                    for forbidden_lower, forbidden_original in forbidden_lower_to_original.items():
                        if family_lower == forbidden_lower or re.search(
                            rf"(?<![a-z0-9\-]){re.escape(forbidden_lower)}(?![a-z0-9\-])",
                            family_lower,
                        ):
                            forbidden_found.append(forbidden_original)
                forbidden_found = list(dict.fromkeys(forbidden_found))
                if forbidden_found:
                    status = "fail"
                    reason = f"Forbidden/default fonts found: {', '.join(forbidden_found[:5])}"
                    self.result.refinement_actions.append(
                        f"Replace forbidden/default fonts ({', '.join(forbidden_found[:5])}) with allowed alternatives from premium-design config."
                    )

            elif check_id == "card_shadows":
                patterns = rule.get("forbidden_patterns", [])
                normalized_text = combined_text.replace(",", ", ").replace("  ", " ")
                matches = [p for p in patterns if re.search(p, normalized_text, re.IGNORECASE)]
                if matches:
                    status = "fail"
                    reason = f"Decorative/generic shadows detected: {matches[:3]}"
                    self.result.refinement_actions.append("Use distinct elevation shadows; generic 8px/card shadows are banned.")

            elif check_id == "centered_buttons":
                forbidden = [p for p in rule.get("forbidden_phrases", []) if p.lower() in lower_text]
                if forbidden and not allowed_present:
                    status = "fail"
                    reason = f"Centered button language without hierarchy rationale: {forbidden[:3]}"
                    self.result.refinement_actions.append("Add hierarchy/asymmetry rationale for centered CTAs or align them within the grid.")

            elif check_id == "gradient_blobs":
                forbidden_phrases = rule.get("forbidden_phrases", [])
                forbidden_patterns = rule.get("forbidden_patterns", [])
                phrase_hits = [p for p in forbidden_phrases if p.lower() in lower_text]
                pattern_hits = [
                    p for p in forbidden_patterns
                    if re.search(p, combined_text, re.IGNORECASE)
                ]
                if (phrase_hits or pattern_hits) and not allowed_present:
                    status = "fail"
                    reason = f"Meaningless gradient blobs: {phrase_hits[:3] + pattern_hits[:3]}"
                    self.result.refinement_actions.append("Remove decorative gradient blobs or justify them as functional (data viz, depth, brand gradient).")

            elif check_id == "uniform_padding":
                scale = spacing_section.get("scale", []) if isinstance(spacing_section, dict) else []
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

            elif check_id == "generic_3col_cards":
                forbidden_phrases = rule.get("forbidden_phrases", [])
                card_mentions = [p for p in forbidden_phrases[:5] if p.lower() in lower_text]
                padding_mentions = [p for p in forbidden_phrases[5:8] if p.lower() in lower_text]
                icon_mentions = [p for p in forbidden_phrases[8:] if p.lower() in lower_text]
                if card_mentions and (padding_mentions or icon_mentions) and not allowed_present:
                    status = "fail"
                    reason = f"Generic 3 equal cards with icon top: {card_mentions[:2]}"
                    self.result.refinement_actions.append("Break 3-card symmetry: vary card sizes, use a bento grid, or remove icon-as-decoration pattern.")

            elif check_id == "single_hero_section":
                forbidden_phrases = rule.get("forbidden_phrases", [])
                trigger_phrases = rule.get("trigger_phrases", [])
                hero_present = any(p.lower() in lower_text for p in forbidden_phrases)
                button_present = any(p.lower() in lower_text for p in trigger_phrases)
                if hero_present and button_present and not allowed_present:
                    status = "fail"
                    reason = "Single centered hero section with one button detected"
                    self.result.refinement_actions.append("Add asymmetry, split layout, or off-center headline; single centered hero + one button is banned unless justified.")

            elif check_id == "gray_on_white":
                flat_gray_values = [v.lower() for v in rule.get("flat_gray_values", [])]
                text_re = rule.get("forbidden_combo", {}).get("text", "")
                bg_re = rule.get("forbidden_combo", {}).get("bg", "")

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

                def _collect_under_key(obj: Any, key_filter: str) -> list[str]:
                    out: list[str] = []
                    if isinstance(obj, dict):
                        for k, v in obj.items():
                            if key_filter in k.lower():
                                out.extend(_collect_strings(v))
                            else:
                                out.extend(_collect_under_key(v, key_filter))
                    return out

                text_colors = _collect_under_key(colors_section, "text")
                bg_colors = _collect_under_key(colors_section, "background") + _collect_under_key(colors_section, "bg")
                gray_text = any(re.search(text_re, str(c), re.IGNORECASE) for c in text_colors)
                flat_gray_text = any(str(c).lower() in flat_gray_values for c in text_colors)
                pure_white_bg = any(re.search(bg_re, str(c), re.IGNORECASE) for c in bg_colors)
                if (gray_text or flat_gray_text) and pure_white_bg:
                    status = "fail"
                    reason = "Flat gray text on pure white background detected"
                    self.result.refinement_actions.append("Shift body text to warm/cool off-white palette or invert contrast; avoid flat mid-gray on #fff.")

            elif check_id == "layout_animations":
                allowed = set(motion_section.get("allowed_properties", [])) if isinstance(motion_section, dict) else set()
                forbidden = set(rule.get("forbidden_properties", []))
                if forbidden.intersection(allowed):
                    status = "fail"
                    reason = "Layout properties (width/height/top/left/margin/padding) listed as animatable"
                    self.result.refinement_actions.append("Restrict motion tokens to transform, opacity, filter, clip-path only.")

            elif check_id == "hover_banality":
                hover_text = json.dumps(components_section.get("button", {})).lower() if isinstance(components_section, dict) else ""
                if "opacity" in hover_text and not any(x in hover_text for x in ("transform", "translate", "scale", "color shift", "underline")):
                    status = "fail"
                    reason = "Hover relies only on opacity change"
                    self.result.refinement_actions.append("Add transform, color shift, or underline logic to button hover concept.")

            elif check_id == "mass_fade_in":
                forbidden = [p for p in rule.get("forbidden_phrases", []) if p.lower() in lower_text]
                if forbidden and not allowed_present:
                    status = "fail"
                    reason = f"Mass fade-in scroll trigger without stagger/transform: {forbidden[:3]}"
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
