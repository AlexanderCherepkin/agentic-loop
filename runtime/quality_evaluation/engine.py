"""QualityEvaluator engine."""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from pydantic import BaseModel, Field

from ..engine.llm_engine import LLMEngine
from .config import QualityEvaluationConfig

logger = logging.getLogger(__name__)


class QualityEvaluationResult(BaseModel):
    """Result of a quality evaluation."""

    overall_score: float = Field(..., ge=0.0, le=10.0)
    criteria: dict[str, float] = Field(default_factory=dict)
    feedback: str = ""
    needs_refinement: bool = False


class QualityEvaluator:
    """Evaluates a manifest and codebase against a checklist via LLM."""

    DEFAULT_PROMPT = """\
Ты — Агент-Оценщик качества. Тебе даны:
1. Текст ТЗ (brief).
2. Архитектурный манифест (manifest).
3. Сгенерированный стартовый codebase (codebase).

Оцени результат по шкале 1–10 по критериям:
- соответствие ТЗ (relevance)
- полнота архитектуры (completeness)
- качество и чистота кода (code_quality)
- корректность структуры файлов (structure)

Верни строго JSON:
{
  "overall_score": 8.5,
  "criteria": {
    "relevance": 9,
    "completeness": 8,
    "code_quality": 7,
    "structure": 8
  },
  "feedback": "Краткое обоснование и что улучшить."
}
"""

    def __init__(
        self,
        llm: LLMEngine,
        config: QualityEvaluationConfig | None = None,
    ) -> None:
        self.llm = llm
        self.config = config or QualityEvaluationConfig()

    async def evaluate(
        self,
        brief: str,
        manifest: str,
        codebase: dict[str, str],
    ) -> QualityEvaluationResult:
        """Evaluate a generated result and decide if refinement is needed."""
        user_prompt = (
            f"ТЗ:\n{brief}\n\n"
            f"Манифест:\n{manifest}\n\n"
            f"Codebase:\n{json.dumps(codebase, ensure_ascii=False, indent=2)}"
        )
        raw = await self.llm.raw_chat_completion(
            system=self.DEFAULT_PROMPT,
            user=user_prompt,
            temperature=0.2,
        )
        parsed = _extract_json(raw)

        overall_score = float(parsed.get("overall_score", 0.0))
        criteria = {
            k: float(v)
            for k, v in (parsed.get("criteria") or {}).items()
            if k in self.config.criteria
        }
        for c in self.config.criteria:
            criteria.setdefault(c, 0.0)

        return QualityEvaluationResult(
            overall_score=overall_score,
            criteria=criteria,
            feedback=str(parsed.get("feedback", "")),
            needs_refinement=overall_score < self.config.min_score,
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
