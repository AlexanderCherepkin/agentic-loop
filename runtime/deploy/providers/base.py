from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ProviderDeployResult:
    provider: str = ""
    service_id: str | None = None
    service_url: str | None = None
    status: str = ""
    error: str | None = None
    logs: list[str] = field(default_factory=list)


class DeployProvider(ABC):
    @property
    @abstractmethod
    def name(self) -> str:
        ...

    @abstractmethod
    def is_configured(self) -> bool:
        ...

    @abstractmethod
    def deploy(
        self,
        image_tag: str,
        project: dict[str, Any],
        config: dict[str, Any] | None = None,
    ) -> ProviderDeployResult:
        ...
