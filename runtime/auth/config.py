from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class AuthProvider:
    provider_id: str
    enabled: bool = True
    publishable_key: str | None = None
    domain: str | None = None
    client_id: str | None = None
    client_secret: str | None = None
    redirect_uri: str | None = None
    allowed_public_paths: list[str] = field(default_factory=lambda: ["/", "/sign-in", "/api/webhook"])
    protected_paths: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AuthProvider":
        return cls(
            provider_id=data.get("provider_id", data.get("provider", "")),
            enabled=data.get("enabled", True),
            publishable_key=data.get("publishable_key"),
            domain=data.get("domain"),
            client_id=data.get("client_id"),
            client_secret=data.get("client_secret"),
            redirect_uri=data.get("redirect_uri"),
            allowed_public_paths=data.get("allowed_public_paths", ["/", "/sign-in", "/api/webhook"]),
            protected_paths=data.get("protected_paths", []),
        )

    def validate(self) -> list[str]:
        errors: list[str] = []
        if self.provider_id not in {"clerk", "auth0"}:
            errors.append(f"unsupported auth provider: {self.provider_id}")
        return errors
