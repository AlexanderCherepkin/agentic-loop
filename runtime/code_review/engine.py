"""CodeReviewer engine."""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from pydantic import BaseModel, Field

from ..engine.llm_engine import LLMEngine
from .config import CodeReviewConfig
from .diff_engine import Patch, PatchApplier

logger = logging.getLogger(__name__)


class CodeIssue(BaseModel):
    """One code review issue."""

    file: str = Field(..., description="File path")
    severity: str = Field(..., description="critical | major | minor | nit")
    line: int | None = Field(None, description="Line number")
    title: str = Field(..., description="Issue title")
    description: str = Field(..., description="Issue description")
    suggestion: str = Field(..., description="How to fix")


class ReviewResult(BaseModel):
    """Result of a code review."""

    overall_score: float = Field(..., ge=0.0, le=10.0)
    summary: str = Field(...)
    issues: list[CodeIssue] = Field(default_factory=list)
    linter_issues: list[CodeIssue] = Field(default_factory=list)
    tools_run: list[str] = Field(default_factory=list)
    suggestions: list[str] = Field(default_factory=list)
    corrected_codebase: dict[str, str] | None = None
    patches: list[Patch] = Field(default_factory=list)
    diff_mode: bool = False
    applied: int = 0
    failed: int = 0


class CodeReviewer:
    """Reviews a generated codebase against a brief and manifest."""

    DEFAULT_PROMPT = """\
Ты — строгий Senior Code Reviewer. Тебе даны:
1. Текст ТЗ (brief).
2. Архитектурный манифест (manifest).
3. Сгенерированный стартовый codebase (codebase) — словарь {filename: content}.

Проведи code review. Ищи:
- баги и логические ошибки;
- проблемы безопасности (SQL-инъекции, XSS, утечка секретов);
- нарушения best practices и стиля;
- отсутствие обработки ошибок;
- проблемы производительности;
- несоответствие ТЗ и манифеста.

Верни строго JSON:
{
  "overall_score": 8.0,
  "summary": "Краткое резюме ревью.",
  "issues": [
    {
      "file": "main.py",
      "severity": "major",
      "line": 42,
      "title": "...",
      "description": "...",
      "suggestion": "..."
    }
  ],
  "suggestions": ["..."]
}
"""

    def __init__(
        self,
        llm: LLMEngine,
        config: CodeReviewConfig | None = None,
    ) -> None:
        self.llm = llm
        self.config = config or CodeReviewConfig()
        self._applier = PatchApplier()

    async def review(
        self,
        brief: str,
        manifest: str,
        codebase: dict[str, str],
    ) -> ReviewResult:
        """Run a code review and return structured findings."""
        user_prompt = self._build_prompt(brief, manifest, codebase)
        raw = await self.llm.raw_chat_completion(
            system=self.DEFAULT_PROMPT,
            user=user_prompt,
            temperature=0.2,
        )
        parsed = _extract_json(raw)

        issues: list[CodeIssue] = []
        for item in parsed.get("issues", []):
            try:
                issues.append(CodeIssue(**item))
            except Exception:
                logger.warning("Skipping malformed code issue: %s", item)

        return ReviewResult(
            overall_score=float(parsed.get("overall_score", 0.0)),
            summary=str(parsed.get("summary", "")),
            issues=issues,
            suggestions=[str(s) for s in parsed.get("suggestions", [])],
        )

    async def review_and_fix(
        self,
        brief: str,
        manifest: str,
        codebase: dict[str, str],
    ) -> ReviewResult:
        """Review and return either corrected files or patches."""
        result = await self.review(brief, manifest, codebase)
        if self.config.diff_mode:
            # Ask LLM to produce patches instead of full files.
            patch_prompt = (
                "На основе замечаний выше сгенерируй набор хирургических патчей. "
                "Каждый патч — JSON-объект {\"file\", \"old\", \"new\"}. "
                "Заменяй только точно найденные фрагменты. Верни JSON массив патчей."
            )
            raw = await self.llm.raw_chat_completion(
                system=patch_prompt,
                user=json.dumps(result.model_dump(), ensure_ascii=False, indent=2),
                temperature=0.2,
            )
            patches_raw = _extract_json(raw)
            patches = [Patch(**p) for p in patches_raw if isinstance(patches_raw, list)]
            corrected, statuses = self._applier.apply(patches, codebase)
            applied = sum(1 for s in statuses if s.applied)
            failed = len(statuses) - applied
            result.patches = patches
            result.diff_mode = True
            result.applied = applied
            result.failed = failed
            result.corrected_codebase = corrected if applied > 0 else None
        else:
            # Ask LLM to return full corrected codebase.
            fix_prompt = (
                "Исправь codebase из предыдущего ревью. Верни JSON словарь "
                "{filename: content} с полным исправленным содержимым файлов."
            )
            raw = await self.llm.raw_chat_completion(
                system=fix_prompt,
                user=json.dumps(result.model_dump(), ensure_ascii=False, indent=2),
                temperature=0.2,
            )
            corrected = _extract_json(raw)
            if isinstance(corrected, dict):
                result.corrected_codebase = {str(k): str(v) for k, v in corrected.items()}
        return result

    def _build_prompt(
        self,
        brief: str,
        manifest: str,
        codebase: dict[str, str],
    ) -> str:
        return (
            f"ТЗ:\n{brief}\n\n"
            f"Архитектурный манифест:\n{manifest}\n\n"
            f"Codebase (JSON):\n{json.dumps(codebase, ensure_ascii=False, indent=2)}"
        )


def _extract_json(text: str) -> dict[str, Any]:
    """Extract the first JSON object from an LLM response."""
    match = re.search(r"```json\s*(\{.*?\})\s*```", text, re.DOTALL)
    if match:
        candidate = match.group(1)
    else:
        start = text.find("{")
        end = text.rfind("}")
        if start == -1 or end == -1 or end <= start:
            return {"raw_output": text}
        candidate = text[start : end + 1]
    try:
        return json.loads(candidate)
    except json.JSONDecodeError:
        return {"raw_output": text}
