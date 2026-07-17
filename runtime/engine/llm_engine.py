from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from ..contracts.agent_spec import AgentSpec
from ..cost_tracking import CostTrackingEngine

from .circuit_breaker import CircuitBreaker, CircuitBreakerConfig
from .headroom_client import HeadroomClient, HeadroomConfig

logger = logging.getLogger(__name__)


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
    # Fast evaluator model for /goal-style pass/fail verdicts.
    evaluator_provider: LLMProvider = LLMProvider.ANTHROPIC
    evaluator_model: str = "claude-haiku-4-5-20251001"
    use_evaluator: bool = True
    # Headroom context compression (optional; agents call explicitly).
    headroom_enabled: bool = field(default_factory=lambda: os.getenv("HEADROOM_ENABLED", "true").lower() not in ("false", "0", "off", "no"))
    headroom_threshold_tokens: int = 500


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
        "user/design_intake.md": {
            "request_type": "design_project",
            "design_descriptor": {
                "design_source": "figma_url",
                "source_value": "https://www.figma.com/design/abc123/Sample",
                "output_mode": "full_code",
                "target_stack": "react_next_tailwind",
                "target_scope": "whole_page",
                "backend_spec": None,
                "metadata": {"title": "Mock Design", "detected_language": "en", "has_assets": True, "has_components": True, "has_backend_spec": False},
            },
            "parsed_request": None,
            "confidence": 0.95,
        },
        "user/client_brief_agent.md": {
            "request_type": "client_order",
            "client_brief": {
                "business_goal": "mock goal",
                "target_audience": {"personas": [], "demographics": "", "pain_points": [], "jobs_to_be_done": []},
                "key_messages": [],
                "ctas": [],
                "references": [],
                "visual_style": {"tone": "", "color_direction": "", "typography_notes": "", "motion_level": "subtle", "accessibility_notes": ""},
                "technical_stack": {"preferred_framework": "react_next_tailwind", "hosting": "", "integrations": [], "constraints": []},
                "content": {"existing_assets": [], "needed_copy": [], "languages": [], "seo_keywords": []},
                "limits": {"budget": "", "deadline": "", "must_have": [], "must_avoid": [], "approval_process": ""},
                "design_source": "design_brief",
                "source_value": "mock brief",
                "output_mode": "both",
                "brief_confidence": 0.5,
                "missing_fields": ["business_goal"],
                "next_action": "ask_user",
                "questions": ["What is the primary business goal?", "Who is the target audience?"],
            },
            "design_descriptor": {
                "design_source": "design_brief",
                "source_value": "mock brief",
                "output_mode": "both",
                "target_stack": "react_next_tailwind",
                "target_scope": "whole_page",
                "backend_spec": None,
                "metadata": {"title": "Mock Brief", "detected_language": "en", "has_assets": False, "has_components": False, "has_backend_spec": False},
            },
        },
        "user/context.md": {"context_summary": "mock context", "relevant": True},
        "planning/task_decomposition.md": {"tasks": [{"id": 1, "agent": "tools_read/read_file.md", "description": "Read file"}]},
        "planning/tool_plan_selection.md": {"plan": [{"step": 1, "agent": "tools_read/read_file.md", "inputs": {"path": "."}}], "needs_copywriting": False},
        "planning/copywriting_agent.md": {
            "copy_package": {
                "headline": "Mock Headline",
                "sub_headline": "Mock sub-headline.",
                "hero_text": "Mock hero body.",
                "cta_primary": {"label": "Get Started", "aria_label": "Get started now", "microcopy": "No credit card required."},
                "cta_secondary": None,
                "value_propositions": ["Fast", "Reliable", "Secure"],
                "section_headlines": [],
                "alt_texts": [],
                "meta": {"title": "Mock Title", "description": "Mock meta description.", "og_title": "Mock OG Title", "og_description": "Mock OG description.", "keywords": ["mock"]},
                "tonality": {"tone": "professional", "voice": "direct", "language": "en"},
                "confidence": 0.9,
                "missing_inputs": [],
                "next_phase_hint": "planning",
            }
        },
        "planning/estimation_proposal_agent.md": {
            "proposal_package": {
                "estimate": {"min_hours": 40, "max_hours": 80, "min_price": 3200, "max_price": 6400, "currency": "USD", "hourly_rate": 80, "confidence": 0.85},
                "timeline": [
                    {"phase": "Discovery", "min_days": 1, "max_days": 2, "depends_on": [], "deliverables": ["Brief validation", "Scope confirmation"]},
                    {"phase": "Design/code", "min_days": 5, "max_days": 10, "depends_on": ["Discovery"], "deliverables": ["Figma-to-code components", "Page layout"]},
                    {"phase": "Integration/QA", "min_days": 2, "max_days": 4, "depends_on": ["Design/code"], "deliverables": ["Analytics/auth/CMS wiring", "Lighthouse 100% pass"]},
                    {"phase": "Delivery", "min_days": 1, "max_days": 2, "depends_on": ["Integration/QA"], "deliverables": ["Repository handoff", "SOW"]},
                ],
                "deliverables": ["Figma audit report", "Next.js + Tailwind code", "Component registry", "Responsive variants", "Asset registry", "Lighthouse report"],
                "assumptions": ["Client provides Figma access or design brief", "Hosting/account credentials provided by client", "Copy uses generated package unless client supplies final text"],
                "exclusions": ["Custom illustration or photography", "Ongoing hosting/SLA", "Third-party subscription costs", "Copywriting beyond generated package"],
                "risks": [{"risk": "Scope creep from undefined sections", "impact": "medium", "mitigation": "Lock sections in discovery", "cost_adjustment": "+10-20%"}],
                "options": [
                    {"name": "Base", "scope": "MVP landing page", "price": 3200, "timeline_days": 9, "notes": "Core sections only"},
                    {"name": "Recommended", "scope": "Full landing page + copy + analytics", "price": 4800, "timeline_days": 14, "notes": "Best fit for most clients"},
                    {"name": "Premium", "scope": "Full build + CMS/auth/PWA + priority", "price": 6400, "timeline_days": 18, "notes": "Includes advanced integrations"},
                ],
                "proposal_markdown": "# Statement of Work\n\n## Scope\nMock scope.\n\n## Investment\n$3,200 – $6,400 USD.\n\n## Timeline\n9–18 business days.\n\n## Next Steps\nApprove option and provide Figma access.",
                "next_phase_hint": "result",
                "missing_inputs": [],
                "confidence": 0.85,
            }
        },
        "planning/project_starter_agent.md": {
            "starter_package": {
                "template_id": "landing",
                "template_name": "Landing Page Starter",
                "stack": {"framework": "nextjs-app-router", "styling": "tailwind-css", "ui_kit": "shadcn-ui", "auth": None, "cms": None, "analytics": None, "i18n": None, "pwa": None, "hosting": "vercel"},
                "files": [
                    {"path": "package.json", "content": '{"name":"landing-starter","version":"0.1.0","private":true,"scripts":{"dev":"next dev","build":"next build","start":"next start","lint":"next lint"},"dependencies":{"next":"^14","react":"^18","react-dom":"^18","clsx":"^2","tailwind-merge":"^2"},"devDependencies":{"typescript":"^5","@types/node":"^20","@types/react":"^18","@types/react-dom":"^18","tailwindcss":"^3","postcss":"^8","autoprefixer":"^10","eslint":"^8","eslint-config-next":"^14"}}'},
                    {"path": "tailwind.config.ts", "content": "import type { Config } from 'tailwindcss'\nconst config: Config = { content: ['./app/**/*.{js,ts,jsx,tsx,mdx}', './src/components/**/*.{js,ts,jsx,tsx,mdx}'], theme: { extend: {} }, plugins: [] }\nexport default config"},
                    {"path": "app/globals.css", "content": "@tailwind base;\n@tailwind components;\n@tailwind utilities;"},
                    {"path": "app/layout.tsx", "content": "export const metadata = { title: 'Landing Starter', description: 'Generated by Agentic Loop' }\nexport default function RootLayout({ children }: { children: React.ReactNode }) { return <html lang='en'><body className='antialiased'>{children}</body></html> }"},
                    {"path": "app/page.tsx", "content": "export default function Home() { return <main className='p-8'><h1 className='text-3xl font-bold'>Welcome</h1><p className='mt-4'>Starter generated by Agentic Loop.</p></main> }"},
                    {"path": "src/lib/utils.ts", "content": "import { clsx, type ClassValue } from 'clsx'\nimport { twMerge } from 'tailwind-merge'\nexport function cn(...inputs: ClassValue[]) { return twMerge(clsx(inputs)) }"},
                ],
                "commands": ["npm install", "npm run dev"],
                "readme": "# Landing Page Starter\n\nGenerated by Agentic Loop.\n\n## Commands\n- `npm install`\n- `npm run dev`\n",
                "env_example": "# Add environment variables here\n# NEXT_PUBLIC_SITE_URL=http://localhost:3000\n",
                "next_steps": ["Run npm install", "Run npm run dev", "Connect Figma URL or replace placeholder copy"],
                "confidence": 0.9,
                "missing_inputs": [],
                "next_phase_hint": "execution",
            }
        },
        "execution/tool_invocation.md": {"tool_call": {"name": "read_file", "arguments": {"path": "README.md"}}, "result": "mock file content", "success": True},
        "execution/safety_guardrails.md": {"safe": True, "checks": []},
        "observability/environment_result.md": {"status": "ok", "outputs": {"result": "mock observation"}},
        "observability/runtime_output.md": {"output": "mock runtime output", "status": "ok"},
        "self_correction/assistance_request.md": {"request_status": "dispatched", "request_id": "mock-req", "fallback_action": "best_effort"},
        "self_correction/plan_adjustment.md": {
            "adjusted_plan": [{"step": 1, "agent": "tools_read/read_file.md"}],
            "change_summary": ["mock adjustment"],
            "risk_delta": 0.0,
            "approval_needed": False,
            "remaining_attempts": 2,
        },
        "self_correction/goal_evaluator.md": {
            "verdict": {"pass": False, "reason": "mock evaluator waiting for real evidence", "confidence": 0.5},
            "criteria_checklist": [],
        },
        "self_correction/result_validation.md": {"valid": True, "score": 0.95},
        "self_correction/regression_guard.md": {
            "regression_report": {
                "status": "passed",
                "screenshot_delta": {"diff_score_delta": 0.0, "baseline_path": None, "current_path": None, "threshold": 0.05},
                "layout_delta": {"new_overflows": 0, "new_overlaps": 0, "new_clipped_text": 0, "bbox_regressions": 0},
                "console_delta": {"new_errors": 0, "new_warnings": 0},
                "lighthouse_delta": {"score_changes": {}},
                "file_delta": {"files_added": 0, "files_removed": 0, "files_modified": 0},
                "regressions": [],
                "verdict": "pass",
                "refinement_actions": [],
            }
        },
        "self_correction/recursion_or_termination.md": {"decision": "recurse", "reason": "mock"},
        "planning/task_scoping_agent.md": {
            "scope_size": "trivial",
            "uncertainty_level": "low",
            "interview_depth": "none",
            "needs_spec": False,
            "needs_sub_agents": False,
            "rationale": "mock: simple request with a single concrete action",
            "assumptions": [],
        },
        "planning/spec_approval_gate.md": {
            "spec_status": "approved",
            "approved_spec": {
                "goal": "mock approved spec",
                "scope": ["mock scope"],
                "key_decisions": [],
                "deliverables": ["mock deliverable"],
                "success_criteria": ["mock criterion"],
                "human_zones": [],
                "assumptions": [],
                "approval_token": "mock-token-" + "0" * 52,
            },
            "questions": [],
            "next_action": "proceed",
            "response": "Mock spec approved. Proceeding.",
        },
        "control/spec_lock.md": {
            "lock_status": "open",
            "reason": "mock: spec approved or task trivial",
            "missing_requirements": None,
            "next_action": "proceed",
        },
        "planning/multi_page_planner.md": {"needs_multi_page": True, "pages": [], "routing_plan": "mock"},
        "planning/storybook_planner.md": {"needs_storybook": True, "stories_plan": "mock"},
        "planning/deploy_planner.md": {"needs_deploy": True, "deploy_plan": "mock"},
        "planning/preview_planner.md": {"needs_preview": True, "preview_plan": "mock"},
        "execution/multi_page_runtime_integrator.md": {"success": True, "files_written": []},
        "execution/storybook_runtime_integrator.md": {"success": True, "files_written": []},
        "execution/deploy_runtime_integrator.md": {"success": True, "deploy_url": "https://example.com", "dry_run": True},
        "execution/preview_runtime_integrator.md": {"success": True, "preview_url": "https://example.com/preview"},
        "observability/multi_page_audit_agent.md": {"audit_status": "passed", "findings": []},
        "observability/storybook_audit_agent.md": {"audit_status": "passed", "findings": []},
        "observability/deploy_audit_agent.md": {"audit_status": "passed", "findings": []},
        "observability/preview_audit_agent.md": {"audit_status": "passed", "findings": []},
        "self_correction/multi_page_validator.md": {"valid": True, "score": 0.95},
        "self_correction/storybook_validator.md": {"valid": True, "score": 0.95},
        "self_correction/deploy_validator.md": {"valid": True, "score": 0.95},
        "self_correction/preview_validator.md": {"valid": True, "score": 0.95},
        "result/solution.md": {"solution_payload": "mock solution", "solution_format": "markdown", "completeness_score": 0.9},
        "result/modified_files.md": {"file_manifest": [], "diff_summary": "mock diff summary", "highlights": [], "rollback_plan": []},
        "result/action_report.md": {"report_text": "mock report", "structured_report": {}, "statistics": {}, "confidence": 0.9},
        "result/summary_recommendations.md": {"recommendations": [], "next_steps": [], "preventive_measures": [], "future_enhancements": [], "risk_warnings": []},
        "mutual_check/result_validator.md": {"valid": True, "score": 0.95},
        "mutual_check/consistency_checker.md": {"consistent": True, "notes": []},
        "mutual_check/quality_assessor.md": {"quality_score": 0.92},
        "mutual_check/action_verifier.md": {"verification_status": "confirmed", "matched_rules": [], "unmatched_rules": []},
        "mutual_check/performance_monitor.md": {"health_status": "healthy", "active_alerts": []},
        "mutual_check/quota_manager.md": {"quota_decision": "granted", "allocated_resources": {}, "remaining_quota": {}},
        "mutual_check/anomaly_detector.md": {"anomaly_detected": False, "anomaly_score": 0.0, "recommended_response": "log"},
        "mutual_check/feedback_aggregator.md": {"aggregated_feedback": {}, "priority_actions": [], "trend_direction": "stable"},
        "mutual_check/compliance_checker.md": {"compliance_status": "compliant", "findings": [], "escalation_required": False},
        "mutual_check/audit_logger.md": {"status": "logged", "log_id": "mock-log", "hash": "0" * 64},


        "output_reviewer.md": {"review_status": "approved", "rejection_categories": [], "revision_notes": []},
        "data_leak_preventer.md": {"leak_detected": False, "action": "pass", "severity": "none"},
        "bias_detector.md": {"bias_detected": False, "recommendation": "pass", "overall_score": 0.1},
        "content_checker.md": {"compliance_status": "compliant", "violations": []},
        "command_guard.md": {"verdict": "allow", "risk_flags": []},
        "safety_assessor.md": {"safety_band": "green", "execution_recommendation": "proceed"},
    }

    async def execute(self, spec: AgentSpec, inputs: dict[str, Any], extra_context: str | None = None) -> LLMResponse:
        await asyncio.sleep(0.01)  # Simulate tiny latency
        agent_path = getattr(spec, "source_path", "") or ""
        base_latency = 15.0

        # Determine mock response (normalize Windows paths to forward slashes)
        response_data: dict[str, Any] = {}
        agent_str = str(agent_path).replace("\\", "/")
        for suffix, payload in self._RESPONSES.items():
            if agent_str.endswith(suffix):
                response_data = dict(payload)
                break
        else:
            response_data = {"mock": True, "agent": agent_str}

        # Special handling for termination: succeed on second invocation
        if agent_str.endswith("recursion_or_termination.md"):
            iteration = inputs.get("iteration", 1)
            if iteration >= 2:
                response_data = {"decision": "terminate_success", "reason": "mock completion"}

        # Special handling for design intake: classify design vs client-order vs general
        if agent_str.endswith("user/design_intake.md"):
            raw_request = str(inputs.get("raw_request", "")).lower()
            design_signals = ["figma", "макет", "дизайн", "design", "верстай", "сверстай", "react по макету"]
            client_signals = ["заказать", "лендинг", "landing", "saas", "саас", "бизнес", "business", "mvp", "продукт", "product", "клиент", "client"]
            if any(signal in raw_request for signal in client_signals) and not any(signal in raw_request for signal in design_signals):
                response_data = {
                    "request_type": "client_order",
                    "design_descriptor": {
                        "design_source": "design_brief",
                        "source_value": inputs.get("raw_request", ""),
                        "output_mode": "both",
                        "target_stack": "react_next_tailwind",
                        "target_scope": "whole_page",
                        "backend_spec": None,
                        "metadata": {"title": "Client Brief", "detected_language": "ru", "has_assets": False, "has_components": False, "has_backend_spec": False},
                    },
                    "parsed_request": {"intent": "client_order"},
                    "confidence": 0.85,
                }
            elif not any(signal in raw_request for signal in design_signals):
                response_data = {
                    "request_type": "general",
                    "design_descriptor": None,
                    "parsed_request": {"intent": "general"},
                    "confidence": 0.8,
                }

        # Special handling for task scoping: trivial for simple requests, large for design/client work
        if agent_str.endswith("planning/task_scoping_agent.md"):
            parsed_request = inputs.get("parsed_request") or {}
            raw_request = str(inputs.get("raw_request", "")).lower()
            client_brief = inputs.get("client_brief")
            design_descriptor = inputs.get("design_descriptor")
            if client_brief or design_descriptor:
                response_data = {
                    "scope_size": "large",
                    "uncertainty_level": "medium",
                    "interview_depth": "full",
                    "needs_spec": True,
                    "needs_sub_agents": True,
                    "rationale": "mock: design or client deliverable requires approved spec",
                    "assumptions": ["mock assumption for client/design task"],
                }
            elif any(signal in raw_request for signal in ["figma", "макет", "дизайн", "design", "верстай", "сверстай"]):
                response_data = {
                    "scope_size": "large",
                    "uncertainty_level": "medium",
                    "interview_depth": "full",
                    "needs_spec": True,
                    "needs_sub_agents": True,
                    "rationale": "mock: design-related request requires approved spec",
                    "assumptions": [],
                }
            elif any(signal in raw_request for signal in ["заказать", "лендинг", "landing", "saas", "саас", "бизнес", "business", "mvp", "продукт", "product", "клиент", "client"]):
                response_data = {
                    "scope_size": "medium",
                    "uncertainty_level": "medium",
                    "interview_depth": "short",
                    "needs_spec": True,
                    "needs_sub_agents": True,
                    "rationale": "mock: client-facing deliverable requires approved spec",
                    "assumptions": [],
                }
            elif parsed_request.get("request_type") in ("question", "debug", "test") or parsed_request.get("confidence", 0.0) < 0.7:
                response_data = {
                    "scope_size": "medium",
                    "uncertainty_level": "low",
                    "interview_depth": "short",
                    "needs_spec": False,
                    "needs_sub_agents": False,
                    "rationale": "mock: question/debug/test handled inline",
                    "assumptions": [],
                }

        # Special handling for spec lock: trivial tasks bypass the lock
        if agent_str.endswith("control/spec_lock.md"):
            task_scope = inputs.get("task_scope") or {}
            if task_scope.get("scope_size") == "trivial" or task_scope.get("needs_spec") is False:
                response_data = {
                    "lock_status": "open",
                    "reason": "mock: trivial task exempt from spec lock",
                    "missing_requirements": None,
                    "next_action": "proceed",
                }

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
        self._cost_tracker = CostTrackingEngine()

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

    def maybe_compress_messages(
        self,
        messages: list[dict[str, Any]],
        target_ratio: float | None = None,
    ) -> dict[str, Any]:
        """Explicit Headroom compression helper for callers that want to shrink
        heavy context before the LLM call.

        This is NOT applied automatically inside `execute()` or
        `raw_chat_completion()` so that safety, control, and audit flows always
        see the original text unless an upstream agent explicitly requests
        compression via `headroom_compressor.md` or the MCP `headroom_compress`
        tool. Returns a passthrough result when Headroom is unavailable or
        `headroom_enabled` is false.
        """
        client = HeadroomClient(HeadroomConfig(enabled=self.config.headroom_enabled))
        return client.compress_messages(messages, target_ratio=target_ratio)

    async def execute(self, spec: AgentSpec, inputs: dict[str, Any], extra_context: str | None = None) -> LLMResponse:
        if self.config.provider == LLMProvider.MOCK:
            response = await MockLLMEngine().execute(spec, inputs, extra_context=extra_context)
            self._track_cost(spec, "", "", response)
            return response

        system_prompt = spec.to_system_prompt()
        if extra_context:
            system_prompt = f"{extra_context}\n\n{system_prompt}"
        user_message = spec.to_input_message(inputs)

        # Primary provider with circuit breaker
        try:
            response = await self._breaker.call(self._execute_with_retries, system_prompt, user_message)
            self._track_cost(spec, system_prompt, user_message, response)
            return response
        except Exception:
            pass

        # Fallback providers
        for fallback in self._fallback_chain:
            try:
                fb_engine = LLMEngine(config=fallback)
                response = await fb_engine._execute_with_retries(system_prompt, user_message)
                self._track_cost(spec, system_prompt, user_message, response)
                return response
            except Exception:
                continue

        raise RuntimeError("All LLM providers failed (circuit breaker open or API errors)")

    def _track_cost(
        self,
        spec: AgentSpec | None,
        system_prompt: str,
        user_message: str,
        response: LLMResponse,
    ) -> None:
        try:
            agent_name = os.path.basename(getattr(spec, "source_path", "") or "raw")
            self._cost_tracker.record_llm_response(
                scope=os.getenv("COST_SCOPE", "default"),
                model=response.model or self.config.model,
                system_prompt=system_prompt,
                user_message=user_message,
                response_text=response.content,
                agent=agent_name or "raw",
            )
        except Exception:
            logger.exception("Failed to record LLM call cost")

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
            self._track_cost(None, system, user, response)
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


@dataclass
class EvaluatorResponse:
    """Strict pass/fail verdict produced by the fast /goal evaluator."""

    pass_: bool
    reason: str
    confidence: float = 0.0
    criteria_checklist: list[dict[str, Any]] = field(default_factory=list)
    raw_output: str = ""


class EvaluationEngine:
    """Lightweight evaluator using a smaller/cheaper model for strict JSON verdicts.

    Implements the Claude-Code /goal pattern: a fast critic checks whether the
    evidence produced so far satisfies the stated goal, returning only
    {"pass": bool, "reason": str, ...}. It is deliberately isolated from the
    main LLMEngine so that the expensive generator and the cheap critic can
    use different models and budgets.
    """

    DEFAULT_EVALUATOR_PROMPT = """You are a strict, fast evaluator. Your only job is to decide whether the evidence below satisfies the stated goal.

Rules:
- Respond ONLY with valid JSON.
- Do not explain, do not add commentary outside the JSON.
- Use the exact shape:
{
  "pass": true or false,
  "reason": "one-line explanation if false; 'Goal satisfied' if true",
  "confidence": 0.0 to 1.0,
  "criteria_checklist": [
    {"criterion": "...", "passed": true or false, "evidence": "..."}
  ]
}
- A criterion passes only if there is concrete evidence, not hope or assumption.
- If evidence is missing or ambiguous, mark the criterion failed and set pass=false."""

    def __init__(self, config: LLMConfig | None = None):
        base = config or LLMConfig()
        self.config = LLMConfig(
            provider=base.evaluator_provider,
            model=base.evaluator_model,
            max_tokens=1024,
            temperature=0.0,
            api_key=base.api_key,
            max_retries=2,
            mcp_enabled=False,
        )
        self._engine = LLMEngine(config=self.config)

    async def evaluate(self, goal: str, artifacts: dict[str, Any], criteria: list[str] | None = None) -> EvaluatorResponse:
        """Return a strict pass/fail verdict for the given goal and evidence."""
        user_message = json.dumps(
            {
                "goal": goal,
                "criteria": criteria or [],
                "artifacts": artifacts,
            },
            ensure_ascii=False,
            indent=2,
        )

        try:
            raw = await self._engine.raw_chat_completion(
                self.DEFAULT_EVALUATOR_PROMPT,
                user_message,
                max_tokens=1024,
                temperature=0.0,
            )
        except Exception as e:
            return EvaluatorResponse(
                pass_=False,
                reason=f"Evaluator engine failed: {e}",
                confidence=0.0,
                raw_output="",
            )

        parsed = self._engine._extract_json(raw) or {}
        if not isinstance(parsed, dict):
            parsed = {"raw_output": str(parsed)}

        verdict = parsed.get("verdict", parsed)
        if not isinstance(verdict, dict):
            verdict = {}

        pass_ = bool(verdict.get("pass", False))
        reason = str(verdict.get("reason", parsed.get("reason", "No reason provided")))
        confidence = float(verdict.get("confidence", parsed.get("confidence", 0.0)))
        checklist = verdict.get("criteria_checklist") or parsed.get("criteria_checklist") or []

        if not reason:
            reason = "Goal satisfied" if pass_ else "Evaluator did not provide a reason"

        return EvaluatorResponse(
            pass_=pass_,
            reason=reason,
            confidence=confidence,
            criteria_checklist=checklist if isinstance(checklist, list) else [],
            raw_output=raw,
        )
