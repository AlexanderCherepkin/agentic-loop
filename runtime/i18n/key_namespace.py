from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any


_STOP_WORDS = {"the", "a", "an", "and", "or", "of", "for", "in", "on", "at", "to", "with"}


def normalize_namespace(value: str) -> str:
    """Sanitize any string into a snake_case namespace segment."""
    value = value.strip().lower()
    value = re.sub(r"[^a-z0-9]+", "_", value)
    value = re.sub(r"_+", "_", value)
    return value.strip("_") or "default"


def _slug_words(text: str, max_words: int = 5) -> list[str]:
    words = re.findall(r"[a-z0-9]+", text.lower())
    return [w for w in words if w not in _STOP_WORDS][:max_words]


@dataclass
class I18nKey:
    key: str
    source_text: str
    namespace: str
    section: str
    context: str = ""
    figma_node_id: str | None = None


@dataclass
class KeyNamespace:
    namespace: str
    keys: list[I18nKey] = field(default_factory=list)
    duplicates: list[dict[str, Any]] = field(default_factory=list)
    skipped: list[dict[str, Any]] = field(default_factory=list)

    def add_text(
        self,
        text: str,
        section: str = "ui",
        context: str = "",
        figma_node_id: str | None = None,
        collision_counter: dict[str, int] | None = None,
    ) -> I18nKey | None:
        collision_counter = collision_counter or {}
        normalized = re.sub(r"\s+", " ", text.strip())
        if not normalized or self._should_skip(normalized):
            self.skipped.append({"text": text, "reason": "non-translatable"})
            return None

        words = _slug_words(normalized)
        if not words:
            self.skipped.append({"text": text, "reason": "no-usable-words"})
            return None

        base_key = "_".join(words)
        safe_section = normalize_namespace(section)
        full_key = f"{safe_section}.{base_key}" if safe_section else base_key

        counter = collision_counter.setdefault(full_key, 0)
        seen_texts = {k.source_text for k in self.keys if k.key.startswith(full_key)}
        if normalized in seen_texts:
            # Record alias for duplicate text
            for existing in self.keys:
                if existing.source_text == normalized:
                    self.duplicates.append(
                        {"text": normalized, "canonical_key": existing.key, "alias": full_key}
                    )
                    return existing

        while any(k.key == full_key for k in self.keys):
            counter += 1
            full_key = f"{safe_section}.{base_key}_{counter}" if safe_section else f"{base_key}_{counter}"

        collision_counter[full_key] = counter

        key_obj = I18nKey(
            key=full_key,
            source_text=normalized,
            namespace=self.namespace,
            section=safe_section,
            context=context,
            figma_node_id=figma_node_id,
        )
        self.keys.append(key_obj)
        return key_obj

    def _should_skip(self, text: str) -> bool:
        if len(text) > 200:
            return False  # still allow, but warn
        if re.fullmatch(r"https?://\S+", text):
            return True
        if re.fullmatch(r"[^\d]*@.*\..*", text):
            return True
        if re.fullmatch(r"[\d\s\-+.,%$€¥£₽]*", text):
            return True
        if text.strip().startswith(("{", "[", "<!--")):
            return True
        return False

    def to_flat_dict(self) -> dict[str, str]:
        result: dict[str, str] = {}
        for key in self.keys:
            parts = key.key.split(".")
            target = result
            for part in parts[:-1]:
                if part not in target or not isinstance(target[part], dict):
                    target[part] = {}
                target = target[part]
            target[parts[-1]] = key.source_text
        return result

    def to_nested_dict(self) -> dict[str, Any]:
        nested: dict[str, Any] = {}
        for key in self.keys:
            parts = key.key.split(".")
            target = nested
            for part in parts[:-1]:
                target = target.setdefault(part, {})
            target[parts[-1]] = key.source_text
        return nested
