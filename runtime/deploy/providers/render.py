from __future__ import annotations

import os
from typing import Any

import httpx

from .base import DeployProvider, ProviderDeployResult


class RenderDeployer(DeployProvider):
    """Deploy a container image to Render as a web service."""

    BASE_URL = "https://api.render.com/v1"
    name = "render"

    def __init__(self, api_key: str | None = None) -> None:
        self.api_key = api_key or os.environ.get("DEPLOY_RENDER_API_KEY")

    def is_configured(self) -> bool:
        return bool(self.api_key)

    def deploy(
        self,
        image_tag: str,
        project: dict[str, Any],
        config: dict[str, Any] | None = None,
    ) -> ProviderDeployResult:
        if not self.is_configured():
            return ProviderDeployResult(
                provider=self.name,
                error="DEPLOY_RENDER_API_KEY is not set",
            )

        cfg = config or {}
        project_id = project.get("project_id", "")
        service_name = cfg.get("service_name", project_id)
        region = cfg.get("region", "oregon")
        owner_id = cfg.get("owner_id")
        plan = cfg.get("plan", "free")
        port = self._detect_port(project)

        if not owner_id:
            return ProviderDeployResult(
                provider=self.name,
                error="owner_id is required for Render deployment",
            )

        logs: list[str] = []
        try:
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Accept": "application/json",
            }
            payload = {
                "type": "web_service",
                "name": service_name,
                "ownerId": owner_id,
                "image": {"imageUrl": image_tag},
                "region": region,
                "envVars": [{"key": "PORT", "value": port}],
                "plan": plan,
            }

            with httpx.Client(timeout=60) as client:
                resp = client.post(
                    f"{self.BASE_URL}/services",
                    headers=headers,
                    json=payload,
                )
                resp.raise_for_status()
                data = resp.json()

            service_id = data.get("id") or data.get("service", {}).get("id")
            service_url = data.get("url") or data.get("service", {}).get("url")
            logs.append(f"Render service created: {service_id}")

            return ProviderDeployResult(
                provider=self.name,
                service_id=service_id,
                service_url=service_url,
                status="created",
                logs=logs,
            )
        except Exception as exc:
            return ProviderDeployResult(
                provider=self.name,
                error=str(exc),
                logs=logs,
            )

    @staticmethod
    def _detect_port(project: dict[str, Any]) -> str:
        language = project.get("language", "python")
        return {"typescript": "3000", "go": "8080", "rust": "8080"}.get(language, "8000")
