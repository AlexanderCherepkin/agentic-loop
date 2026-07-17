from __future__ import annotations

from pathlib import Path
from typing import Any

from .base import MCPServer, MCPToolResult
from runtime.cost_tracking import CostTrackingConfig, CostTrackingEngine


class CostTrackingMCPServer(MCPServer):
    """MCP server for LLM cost estimation and budget tracking."""

    def __init__(self, workspace_root: str = "."):
        super().__init__(name="cost_tracking", version="1.0.0")
        self.workspace = Path(workspace_root).resolve()
        self._register_all()

    def _schema(self, props: dict[str, str]) -> dict[str, Any]:
        required = [k for k in props if not k.endswith("?")]
        properties: dict[str, Any] = {}
        for k, v in props.items():
            name = k[:-1] if k.endswith("?") else k
            properties[name] = {"type": v}
        return {
            "type": "object",
            "properties": properties,
            "required": required,
        }

    def _register_all(self):
        self.register(
            "estimate_cost",
            "Estimate cost of an LLM call from model/input/output text",
            self._schema({"model": "string", "input": "string", "output?": "string", "agent?": "string"}),
            self.estimate_cost,
        )
        self.register(
            "get_report",
            "Return cost usage report for a scope",
            self._schema({"scope?": "string", "window_seconds?": "integer"}),
            self.get_report,
        )
        self.register(
            "check_budget",
            "Check whether a scope is within its configured budget",
            self._schema({"scope?": "string"}),
            self.check_budget,
        )
        self.register(
            "set_budget",
            "Set a budget limit for a scope",
            self._schema({"scope": "string", "limit": "number", "currency?": "string"}),
            self.set_budget,
        )

    async def estimate_cost(
        self,
        model: str,
        input: str,
        output: str = "",
        agent: str = "agent",
    ) -> dict[str, Any]:
        try:
            engine = CostTrackingEngine(CostTrackingConfig(enabled=True))
            estimate = engine.estimate(model=model, input_text=input, output_text=output, agent=agent)
            return {
                "status": "success",
                "model": estimate.model,
                "input_tokens": estimate.input_tokens,
                "output_tokens": estimate.output_tokens,
                "total_cost": estimate.total_cost,
                "currency": estimate.currency,
            }
        except Exception as exc:
            return {"status": "error", "detail": str(exc)}

    async def get_report(self, scope: str | None = None, window_seconds: int | None = None) -> dict[str, Any]:
        try:
            engine = CostTrackingEngine(CostTrackingConfig(enabled=True))
            report = engine.get_report(scope=scope, window_seconds=window_seconds)
            return {"status": "success", "report": report}
        except Exception as exc:
            return {"status": "error", "detail": str(exc)}

    async def check_budget(self, scope: str = "default") -> dict[str, Any]:
        try:
            engine = CostTrackingEngine(CostTrackingConfig(enabled=True))
            return {"status": "success", "budget": engine.check_budget(scope)}
        except Exception as exc:
            return {"status": "error", "detail": str(exc)}

    async def set_budget(
        self,
        scope: str,
        limit: float,
        currency: str = "USD",
    ) -> dict[str, Any]:
        try:
            engine = CostTrackingEngine(CostTrackingConfig(enabled=True))
            engine.set_budget(scope, limit, currency)
            return {"status": "success", "scope": scope, "limit": limit, "currency": currency}
        except Exception as exc:
            return {"status": "error", "detail": str(exc)}
