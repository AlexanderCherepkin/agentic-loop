from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class CmsSourceId(Enum):
    local_markdown = "local_markdown"
    notion = "notion"
    contentful = "contentful"
    strapi = "strapi"
    prisma = "prisma"
    airtable = "airtable"
    google_sheets = "google_sheets"
    cms_api = "cms_api"


@dataclass
class CmsSource:
    source_id: CmsSourceId | str
    enabled: bool = True
    connection: dict[str, Any] = field(default_factory=dict)
    entity_types: list[str] = field(default_factory=list)
    mapping: dict[str, str] = field(default_factory=dict)
    cache_ttl_seconds: int = 60
    fallback_to_static: bool = True

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "CmsSource":
        raw_id = data.get("source_id", data.get("provider", "local_markdown"))
        try:
            source_id = CmsSourceId(raw_id)
        except ValueError:
            source_id = raw_id
        return cls(
            source_id=source_id,
            enabled=data.get("enabled", True),
            connection=data.get("connection", {}),
            entity_types=data.get("entity_types", []),
            mapping=data.get("mapping", {}),
            cache_ttl_seconds=data.get("cache_ttl_seconds", 60),
            fallback_to_static=data.get("fallback_to_static", True),
        )

    def validate(self) -> list[str]:
        errors: list[str] = []
        if isinstance(self.source_id, str) and self.source_id not in {m.value for m in CmsSourceId}:
            errors.append(f"unsupported cms source: {self.source_id}")
        if self.cache_ttl_seconds < 0:
            errors.append("cache_ttl_seconds must be >= 0")
        return errors
