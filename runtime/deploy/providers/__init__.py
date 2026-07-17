from __future__ import annotations

from .base import DeployProvider, ProviderDeployResult
from .flyio import FlyioDeployer
from .railway import RailwayDeployer
from .render import RenderDeployer

__all__ = [
    "DeployProvider",
    "ProviderDeployResult",
    "DeployProviderFactory",
    "RenderDeployer",
    "RailwayDeployer",
    "FlyioDeployer",
]


class DeployProviderFactory:
    """Factory that returns configured image deploy providers by name."""

    PROVIDERS: dict[str, type[DeployProvider]] = {
        "render": RenderDeployer,
        "railway": RailwayDeployer,
        "flyio": FlyioDeployer,
    }

    @classmethod
    def get(cls, provider: str) -> DeployProvider:
        name = provider.lower()
        if name not in cls.PROVIDERS:
            raise ValueError(f"Unknown image deploy provider: {provider}")
        return cls.PROVIDERS[name]()

    @classmethod
    def list(cls) -> dict[str, bool]:
        return {name: provider().is_configured() for name, provider in cls.PROVIDERS.items()}
