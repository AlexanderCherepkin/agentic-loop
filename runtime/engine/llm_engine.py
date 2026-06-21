from __future__ import annotations

import asyncio
import json
import os
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from ..contracts.agent_spec import AgentSpec

from .circuit_breaker import CircuitBreaker, CircuitBreakerConfig


class LLMProvider(str, Enum):
    ANTHROPIC = "anthropic"
    OPENAI = "openai"
    DEEPSEEK = "deepseek"
    MOCK = "mock"


@dataclass
class LLMResponse:
    content: str
    parsed: dict[str, Any] | None = None
    model: str = ""
    tokens_used: int = 0
    latency_ms: float = 0
    finish_reason: str = ""


@dataclass
class LLMConfig:
    provider: LLMProvider = LLMProvider.ANTHROPIC
    model: str = "claude-sonnet-4-6"
    max_tokens: int = 4096
    temperature: float = 0.3
    api_key: str | None = None
    max_retries: int = 3
    mcp_enabled: bool = False


class MockLLMEngine:
    """Deterministic mock LLM engine for integration testing without API keys.

    Returns shaped JSON responses based on agent_path so the full ReAct pipeline
    can execute end-to-end.
    """

    # Mapping of agent_path suffix -> deterministic response dict
    _RESPONSES: dict[str, dict[str, Any]] = {
        "input_sanitizer.md": {"blocked": False, "sanitized": "mock sanitized input", "issues": []},
        "threat_detector.md": {"threat_level": "none", "blocked": False, "threats": []},
        "permission_checker.md": {"allowed": True, "permissions": ["read", "write"]},
        "scope_manager.md": {"scope_approved": True, "scope": "mock_scope"},
        "policy_enforcer.md": {"policy_violation": False, "policy": "mock_policy"},
        "user/request.md": {"parsed_intent": "analysis", "entities": []},
        "user/context.md": {"context_summary": "mock context", "relevant": True},
        "planning/task_decomposition.md": {"tasks": [{"id": 1, "agent": "tools_read/read_file.md", "description": "Read file"}]},
        "planning/tool_plan_selection.md": {"plan": [{"step": 1, "agent": "tools_read/read_file.md", "inputs": {"path": "."}}]},
        "execution/tool_invocation.md": {"tool_called": "read_file", "result": "mock file content", "success": True},
        "execution/safety_guardrails.md": {"safe": True, "checks": []},
        "observability/environment_result.md": {"status": "ok", "outputs": {"result": "mock observation"}},
        "observability/runtime_output.md": {"output": "mock runtime output", "status": "ok"},
        "self_correction/error_handler.md": {"error_type": "none", "recovery_action": "continue"},
        "self_correction/adjustment_planner.md": {"adjusted_plan": [{"step": 1, "agent": "tools_read/read_file.md"}]},
        "self_correction/result_validation.md": {"valid": True, "score": 0.95},
        "self_correction/recursion_or_termination.md": {"decision": "recurse", "reason": "mock"},
        "result_formatter.md": {"formatted": "mock formatted result", "status": "ok"},
        "result_presenter.md": {"presentation": "mock presentation", "status": "ok"},
        "termination_decision.md": {"decision": "recurse", "reason": "mock"},
        "mutual_check/result_validator.md": {"valid": True, "score": 0.95},
        "mutual_check/consistency_checker.md": {"consistent": True, "notes": []},
        "mutual_check/quality_assessor.md": {"quality_score": 0.92},
        "output_reviewer.md": {"approved": True, "issues": []},
        "data_leak_preventer.md": {"leak_detected": False, "sensitive": []},
        "content_checker.md": {"appropriate": True, "flags": []},
    }

    async def execute(self, spec: AgentSpec, inputs: dict[str, Any]) -> LLMResponse:
        await asyncio.sleep(0.01)  # Simulate tiny latency
        agent_path = getattr(spec, "source_path", "") or ""
        base_latency = 15.0

        # Determine mock response
        response_data: dict[str, Any] = {}
        agent_str = str(agent_path)
        for suffix, payload in self._RESPONSES.items():
            if agent_str.endswith(suffix):
                response_data = dict(payload)
                break
        else:
            response_data = {"mock": True, "agent": agent_str}

        # Special handling for termination: succeed on second invocation
        if agent_str.endswith("termination_decision.md") or agent_str.endswith("recursion_or_termination.md"):
            iteration = inputs.get("iteration", 1)
            if iteration >= 2:
                response_data = {"decision": "terminate_success", "reason": "mock completion"}

        content = json.dumps(response_data, ensure_ascii=False)
        return LLMResponse(
            content=content,
            parsed=response_data,
            model="mock-engine",
            tokens_used=len(content) // 4,
            latency_ms=base_latency + (hash(agent_path) % 30),
            finish_reason="stop",
        )

    async def raw_chat_completion(
        self, system: str, user: str, max_tokens: int | None = None, temperature: float = 0.2
    ) -> str:
        await asyncio.sleep(0.01)
        return json.dumps({"mock_raw": True, "system_len": len(system), "user_len": len(user)})


class LLMEngine:
    """LLM execution engine with circuit breaker and provider fallback.

    Fallback chain (configured automatically from env keys):
      Anthropic → OpenAI → DeepSeek
    """

    def __init__(self, config: LLMConfig | None = None):
        self.config = config or LLMConfig()
        self._resolve_api_key()
        self._breaker = CircuitBreaker(
            name=f"llm_{self.config.provider.value}",
            config=CircuitBreakerConfig(failure_threshold=3, recovery_timeout=30.0),
        )
        self._fallback_chain: list[LLMConfig] = self._build_fallback_chain()

    def _resolve_api_key(self):
        if self.config.api_key:
            return
        if self.config.provider == LLMProvider.ANTHROPIC:
            self.config.api_key = os.getenv("ANTHROPIC_API_KEY")
        elif self.config.provider == LLMProvider.OPENAI:
            self.config.api_key = os.getenv("OPENAI_API_KEY")
        elif self.config.provider == LLMProvider.DEEPSEEK:
            self.config.api_key = os.getenv("DEEPSEEK_API_KEY")

    def _build_fallback_chain(self) -> list[LLMConfig]:
        """Build ordered list of fallback providers based on available API keys."""
        chain: list[LLMConfig] = []
        candidates = [
            (LLMProvider.ANTHROPIC, "claude-sonnet-4-6"),
            (LLMProvider.OPENAI, "gpt-4o"),
            (LLMProvider.DEEPSEEK, "deepseek-chat"),
        ]
        for prov, model in candidates:
            key = os.getenv(f"{prov.value.upper()}_API_KEY")
            if key and prov != self.config.provider:
                chain.append(LLMConfig(provider=prov, model=model, api_key=key))
        return chain

    async def execute(self, spec: AgentSpec, inputs: dict[str, Any]) -> LLMResponse:
        if self.config.provider == LLMProvider.MOCK:
            return await MockLLMEngine().execute(spec, inputs)

        system_prompt = spec.to_system_prompt()
        user_message = spec.to_input_message(inputs)

        # Primary provider with circuit breaker
        try:
            return await self._breaker.call(self._execute_with_retries, system_prompt, user_message)
        except Exception:
            pass

        # Fallback providers
        for fallback in self._fallback_chain:
            try:
                fb_engine = LLMEngine(config=fallback)
                return await fb_engine._execute_with_retries(system_prompt, user_message)
            except Exception:
                continue

        raise RuntimeError("All LLM providers failed (circuit breaker open or API errors)")

    async def _execute_with_retries(self, system_prompt: str, user_message: str) -> LLMResponse:
        for attempt in range(1, self.config.max_retries + 1):
            try:
                return await self._call_api(system_prompt, user_message)
            except Exception as e:
                if attempt == self.config.max_retries:
                    raise
                await asyncio.sleep(2 ** attempt * 0.5)
        raise RuntimeError("Unreachable")

    async def _call_api(self, system_prompt: str, user_message: str) -> LLMResponse:
        t0 = time.perf_counter()

        if self.config.provider == LLMProvider.ANTHROPIC:
            result = await self._call_anthropic(system_prompt, user_message)
        elif self.config.provider == LLMProvider.OPENAI:
            result = await self._call_openai(system_prompt, user_message)
        elif self.config.provider == LLMProvider.DEEPSEEK:
            result = await self._call_openai(system_prompt, user_message, base_url="https://api.deepseek.com/v1")
        else:
            raise ValueError(f"Unknown provider: {self.config.provider}")

        result.latency_ms = (time.perf_counter() - t0) * 1000
        result.parsed = self._extract_json(result.content)
        return result

    async def _call_anthropic(self, system_prompt: str, user_message: str) -> LLMResponse:
        import anthropic  # type: ignore

        client = anthropic.AsyncAnthropic(api_key=self.config.api_key)
        response = await client.messages.create(
            model=self.config.model,
            max_tokens=self.config.max_tokens,
            temperature=self.config.temperature,
            system=system_prompt,
            messages=[{"role": "user", "content": user_message}],
        )
        content = response.content[0].text if isinstance(response.content, list) else str(response.content)
        return LLMResponse(
            content=content,
            model=response.model,
            tokens_used=response.usage.input_tokens + response.usage.output_tokens if hasattr(response, "usage") else 0,
            finish_reason=getattr(response, "stop_reason", "stop"),
        )

    async def _call_openai(self, system_prompt: str, user_message: str, base_url: str | None = None) -> LLMResponse:
        import openai  # type: ignore

        client = openai.AsyncOpenAI(api_key=self.config.api_key, base_url=base_url or None)
        response = await client.chat.completions.create(
            model=self.config.model,
            max_tokens=self.config.max_tokens,
            temperature=self.config.temperature,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
        )
        choice = response.choices[0]
        return LLMResponse(
            content=choice.message.content or "",
            model=response.model,
            tokens_used=response.usage.total_tokens if hasattr(response, "usage") else 0,
            finish_reason=choice.finish_reason or "stop",
        )

    async def raw_chat_completion(
        self, system: str, user: str, max_tokens: int | None = None, temperature: float = 0.2
    ) -> str:
        """Direct API call without AgentSpec wrapping. Returns raw text."""
        saved_max = self.config.max_tokens
        saved_temp = self.config.temperature
        try:
            self.config.max_tokens = max_tokens or saved_max
            self.config.temperature = temperature
            response = await self._call_api(system, user)
            return response.content
        finally:
            self.config.max_tokens = saved_max
            self.config.temperature = saved_temp

    def _extract_json(self, text: str) -> dict[str, Any] | None:
        text = text.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            lines = lines[1:] if lines[0].startswith("```") else lines
            if lines and lines[-1].startswith("```"):
                lines = lines[:-1]
            text = "\n".join(lines)
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            if "{" in text and "}" in text:
                try:
                    start = text.index("{")
                    end = text.rindex("}") + 1
                    return json.loads(text[start:end])
                except (json.JSONDecodeError, ValueError):
                    pass
            return {"raw_output": text}
