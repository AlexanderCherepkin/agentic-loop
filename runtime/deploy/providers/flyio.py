from __future__ import annotations

import os
from typing import Any

import httpx

from .base import DeployProvider, ProviderDeployResult


class FlyioDeployer(DeployProvider):
    """Deploy a container image to Fly.io via the Machines API."""

    BASE_URL = "https://api.machines.dev/v1"
    name = "flyio"

    def __init__(self, api_token: str | None = None, org_slug: str | None = None) -> None:
        self.api_token = api_token or os.environ.get("DEPLOY_FLY_API_TOKEN")
        self.org_slug = org_slug or os.environ.get("DEPLOY_FLY_ORG_SLUG")

    def is_configured(self) -> bool:
        return bool(self.api_token)

    def deploy(
        self,
        image_tag: str,
        project: dict[str, Any],
        config: dict[str, Any] | None = None,
    ) -> ProviderDeployResult:
        if not self.is_configured():
            return ProviderDeployResult(
                provider=self.name,
                error="DEPLOY_FLY_API_TOKEN is not set",
            )

        cfg = config or {}
        project_id = project.get("project_id", "")
        app_name = cfg.get("app_name", project_id)
        region = cfg.get("region", "iad")
        port = int(self._detect_port(project))
        logs: list[str] = []

        if not self.org_slug:
            return ProviderDeployResult(
                provider=self.name,
                error="DEPLOY_FLY_ORG_SLUG is not set",
            )

        try:
            headers = {
                "Authorization": f"Bearer {self.api_token}",
                "Content-Type": "application/json",
            }

            with httpx.Client(timeout=60) as client:
                app_resp = client.post(
                    f"{self.BASE_URL}/apps",
                    headers=headers,
                    json={
                        "app_name": app_name,
                        "org_slug": self.org_slug,
                    },
                )
                if app_resp.status_code not in (200, 201, 409):
                    app_resp.raise_for_status()
                app_data = app_resp.json()
                app_id = app_data.get("id") or app_name
                logs.append(f"Fly app created/used: {app_id}")

                machine_resp = client.post(
                    f"{self.BASE_URL}/apps/{app_id}/machines",
                    headers=headers,
                    json={
                        "region": region,
                        "config": {
                            "image": image_tag,
                            "env": {"PORT": str(port)},
                            "services": [
                                {
                                    "protocol": "tcp",
                                    "internal_port": port,
                                    "ports": [{"port": 443, "handlers": ["tls", "http"]}],
                                }
                            ],
                        },
                    },
                )
                machine_resp.raise_for_status()
                machine_data = machine_resp.json()
                machine_id = machine_data.get("id")
                logs.append(f"Fly machine created: {machine_id}")

            return ProviderDeployResult(
                provider=self.name,
                service_id=app_id,
                service_url=f"https://{app_name}.fly.dev",
                status="deploying",
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
