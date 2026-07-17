from __future__ import annotations

import os
from typing import Any

import httpx

from .base import DeployProvider, ProviderDeployResult


class RailwayDeployer(DeployProvider):
    """Deploy a container image to Railway via GraphQL."""

    GRAPHQL_URL = "https://backboard.railway.app/graphql/v2"
    name = "railway"

    def __init__(self, api_key: str | None = None) -> None:
        self.api_key = api_key or os.environ.get("DEPLOY_RAILWAY_API_KEY")

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
                error="DEPLOY_RAILWAY_API_KEY is not set",
            )

        cfg = config or {}
        project_id = project.get("project_id", "")
        service_name = cfg.get("service_name", project_id)
        logs: list[str] = []

        try:
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            }

            project_resp = self._graphql(
                headers,
                "mutation projectCreate { projectCreate { id name } }",
            )
            railway_project_id = project_resp["data"]["projectCreate"]["id"]
            logs.append(f"Railway project created: {railway_project_id}")

            service_mutation = (
                f'mutation serviceCreate {{ serviceCreate(input: {{ '
                f'projectId: "{railway_project_id}", name: "{service_name}" }}) {{ id __typename }} }}'
            )
            service_resp = self._graphql(headers, service_mutation)
            service_id = service_resp["data"]["serviceCreate"]["id"]
            logs.append(f"Railway service created: {service_id}")

            deploy_mutation = (
                f'mutation serviceInstanceDeploy {{ serviceInstanceDeploy('
                f'input: {{ serviceId: "{service_id}", image: "{image_tag}" }}) {{ id status }} }}'
            )
            deploy_resp = self._graphql(headers, deploy_mutation)
            deployment_id = deploy_resp["data"]["serviceInstanceDeploy"]["id"]
            logs.append(f"Railway deployment started: {deployment_id}")

            return ProviderDeployResult(
                provider=self.name,
                service_id=service_id,
                service_url=f"https://{service_id}.up.railway.app",
                status="deploying",
                logs=logs,
            )
        except Exception as exc:
            return ProviderDeployResult(
                provider=self.name,
                error=str(exc),
                logs=logs,
            )

    def _graphql(self, headers: dict[str, str], query: str) -> dict[str, Any]:
        with httpx.Client(timeout=60) as client:
            resp = client.post(
                self.GRAPHQL_URL,
                headers=headers,
                json={"query": query},
            )
            resp.raise_for_status()
            data = resp.json()

        if data.get("errors"):
            raise RuntimeError(data["errors"])
        return data
