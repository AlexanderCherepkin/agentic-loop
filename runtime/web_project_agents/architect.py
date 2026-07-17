"""ProjectArchitect runtime adapter."""

from __future__ import annotations

import json
import logging
from typing import Any

from ..engine.llm_engine import LLMEngine
from .config import ProjectArchitectConfig
from .prompts import PromptManifest

logger = logging.getLogger(__name__)


class ProjectArchitect:
    """Produces an architecture manifest from a classification result."""

    DEFAULT_PROMPT = """\
Ты — Агент-Архитектор. На основе JSON-классификации проекта разработай системный дизайн.

Опиши:
1. Выбор стека (фреймворки, БД, очереди, инфраструктура).
2. Структуру сервисов / модулей и их ответственность.
3. API / endpoints (названия, назначение, методы, payload).
4. Схему данных (основные сущности и связи).
5. Потоки аутентификации и авторизации.
6. Ключевые интеграции (платежи, почта, аналитика и т.д.).
7. План масштабирования и отказоустойчивости.
8. Деплой-стратегию.

Формат: Markdown с чёткими заголовками. Не пиши готовый production-код — только архитектурный манифест.
"""

    def __init__(
        self,
        llm: LLMEngine,
        config: ProjectArchitectConfig | None = None,
        manifest: PromptManifest | None = None,
    ) -> None:
        self.llm = llm
        self.config = config or ProjectArchitectConfig()
        self.manifest = manifest or PromptManifest()
        self._system_prompt = self.manifest.get_system_prompt("architect", self.config.prompt_version) or self.DEFAULT_PROMPT

    async def design(
        self,
        classification: dict[str, Any],
        language: str | None = None,
    ) -> str | tuple[str, str]:
        """Create an architecture manifest from a classification dict.

        If ``config.include_adr`` is True, returns ``(manifest, adr)``.
        """
        user_prompt = json.dumps(classification, ensure_ascii=False, indent=2)
        if language:
            user_prompt += (
                f"\n\nЦелевой язык программирования: {language}. "
                "Выбирай стек и пиши манифест под этот язык."
            )

        logger.info(
            "Designing architecture for base=%s",
            classification.get("project_type", {}).get("base_category"),
        )
        manifest = await self.llm.raw_chat_completion(
            system=self._system_prompt,
            user=user_prompt,
            temperature=0.2,
        )
        logger.info("Architecture manifest received (%d chars)", len(manifest))

        if not self.config.include_adr:
            return manifest

        adr_prompt = (
            "На основе только что созданного манифеста напиши краткий Architecture Decision Record (ADR). "
            "Объясни, почему был выбран именно этот стек, база данных, фреймворки и ключевые архитектурные решения. "
            "Укажи trade-offs и альтернативы, которые рассматривались. "
            "Формат: Markdown с заголовками ## Context, ## Decision, ## Consequences, ## Alternatives considered."
        )
        adr_user_prompt = (
            f"Классификация:\n{json.dumps(classification, ensure_ascii=False, indent=2)}\n\n"
            f"Манифест:\n{manifest}"
        )
        try:
            adr = await self.llm.raw_chat_completion(
                system=adr_prompt,
                user=adr_user_prompt,
                temperature=0.2,
            )
            logger.info("ADR received (%d chars)", len(adr))
        except Exception:
            logger.exception("ADR generation failed")
            adr = ""
        return manifest, adr
