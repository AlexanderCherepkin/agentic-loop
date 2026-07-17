"""ProjectDeveloper runtime adapter."""

from __future__ import annotations

import json
import logging
from typing import Any

from ..engine.llm_engine import LLMEngine
from .config import ProjectDeveloperConfig
from .prompts import PromptManifest

logger = logging.getLogger(__name__)


class ProjectDeveloper:
    """Generates a starter codebase from an architecture manifest."""

    DEFAULT_PROMPT = """\
Ты — Агент-Разработчик. Тебе дан архитектурный манифест. Сгенерируй стартовый codebase в виде JSON:

{
  "README.md": "# Project Name\\n...",
  "src/main.py": "...",
  "requirements.txt": "..."
}

Правила:
- Каждый ключ — относительный путь файла.
- Значение — полное содержимое файла.
- Код должен компилироваться / запускаться без ручных правок.
- Используй только популярные библиотеки, которые можно установить через pip/npm/cargo/go mod.
- Не включай секреты, пароли или API-ключи — используй переменные окружения.
- Добавь Dockerfile / docker-compose.yml, если это уместно для стека.
- Не пиши тесты, если не просили — сосредоточься на MVP.
"""

    def __init__(
        self,
        llm: LLMEngine,
        config: ProjectDeveloperConfig | None = None,
        manifest: PromptManifest | None = None,
    ) -> None:
        self.llm = llm
        self.config = config or ProjectDeveloperConfig()
        self.manifest = manifest or PromptManifest()
        self._system_prompt = self.manifest.get_system_prompt("developer", self.config.prompt_version) or self.DEFAULT_PROMPT

    async def develop(
        self,
        manifest: str,
        language: str | None = None,
    ) -> dict[str, str]:
        """Generate a starter codebase from an architecture manifest."""
        user_prompt = manifest
        if language:
            user_prompt += (
                f"\n\nГенерируй код на языке программирования: {language}. "
                "Соблюдай идиомы и экосистему этого языка."
            )

        logger.info("Generating starter codebase from manifest (%d chars)", len(manifest))
        raw = await self.llm.raw_chat_completion(
            system=self._system_prompt,
            user=user_prompt,
            temperature=0.2,
        )
        result = _extract_json(raw)
        if not isinstance(result, dict):
            raise ValueError(f"Expected JSON object with files, got {type(result)}")
        logger.info("Generated %d files", len(result))
        return {str(k): str(v) for k, v in result.items()}


def _extract_json(text: str) -> Any:
    """Extract the first JSON object or array from an LLM response."""
    import re

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
