"""ProjectClassifier runtime adapter."""

from __future__ import annotations

import json
import logging
import re
import sqlite3
import time
from pathlib import Path
from typing import Any

from ..engine.llm_engine import LLMEngine
from .config import ProjectClassifierConfig
from .prompts import PromptManifest

logger = logging.getLogger(__name__)


class ClassificationCache:
    """Minimal SQLite-backed cache for classification results."""

    def __init__(self, db_path: str, ttl_seconds: int = 86400) -> None:
        self.db_path = db_path
        self.ttl_seconds = ttl_seconds
        self._ensure_table()

    def _ensure_table(self) -> None:
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS classifications (
                    key TEXT PRIMARY KEY,
                    result TEXT NOT NULL,
                    created_at REAL NOT NULL
                )
                """
            )

    def _key(self, text: str, language: str | None) -> str:
        normalized = re.sub(r"\s+", " ", text.strip().lower())
        return f"{language or 'auto'}:{normalized[:512]}"

    def get(self, text: str, language: str | None = None) -> dict[str, Any] | None:
        key = self._key(text, language)
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT result, created_at FROM classifications WHERE key = ?", (key,)
            ).fetchone()
        if row is None:
            return None
        result, created_at = row
        if time.time() - created_at > self.ttl_seconds:
            return None
        try:
            return json.loads(result)
        except json.JSONDecodeError:
            return None

    def set(self, text: str, result: dict[str, Any], language: str | None = None) -> None:
        key = self._key(text, language)
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "INSERT OR REPLACE INTO classifications (key, result, created_at) VALUES (?, ?, ?)",
                (key, json.dumps(result, ensure_ascii=False), time.time()),
            )


class ProjectClassifier:
    """Classifies a technical brief into project categories and modules."""

    DEFAULT_PROMPT = """\
Ты — Агент-Аналитик. Проанализируй техническое задание (ТЗ) и классифицируй веб-проект.

ШАГ 1: ПОИСК ТРИГГЕРОВ
Найди слова-маркеры. Веса:
- Вес 3 (уникальный функционал): корзина, стоп-уроки, Wasm, стриминг, курсы, бронь.
- Вес 2 (важный функционал): личный кабинет, парсинг, админка, CRM, биллинг.
- Вес 1 (базовый функционал): форма связи, оплата, новости, регистрация.

ШАГ 2: ПОДСЧЁТ БАЛЛОВ
Сгруппируй по категориям: Лендинг, Посадочная страница, Корпоративный сайт, E-commerce, Информационный портал, Портфолио, Блог, Форум, Социальная сеть, CMS, Веб-сервис, SaaS, LMS, Booking, Dashboard/UI, Headless CMS, WebAssembly.
Определи base_category (максимум баллов). Если другая категория набрала >50% от base — она становится MODULE_CATEGORY.

ШАГ 3: ФОРМАТ
Запрещено писать код или проектировать базу данных. Верни строго JSON:
{
  "project_type": {"base_category": "...", "modules": ["..."]},
  "confidence_scores": {"LMS": 15, "E-commerce": 9},
  "detected_triggers": [{"word": "...", "weight": 3, "category": "..."}],
  "architectural_summary": "..."
}
"""

    def __init__(
        self,
        llm: LLMEngine,
        config: ProjectClassifierConfig | None = None,
        manifest: PromptManifest | None = None,
    ) -> None:
        self.llm = llm
        self.config = config or ProjectClassifierConfig()
        self.manifest = manifest or PromptManifest()
        self._system_prompt = self.manifest.get_system_prompt("classifier", self.config.prompt_version) or self.DEFAULT_PROMPT
        self._cache: ClassificationCache | None = None
        if self.config.use_cache:
            self._cache = ClassificationCache(
                db_path=self.config.cache_db_path,
                ttl_seconds=self.config.cache_ttl_seconds,
            )

    async def classify(
        self,
        brief: str,
        language: str | None = None,
    ) -> dict[str, Any]:
        """Classify a raw technical brief.

        Returns a structured classification JSON dict.
        """
        text = brief.strip()
        if not text:
            raise ValueError("Brief cannot be empty.")

        if self._cache is not None:
            cached = self._cache.get(text, language=language)
            if cached is not None:
                return cached

        user_prompt = text
        if language:
            user_prompt += f"\n\nПредпочитаемый язык программирования: {language}."

        logger.info("Classifying brief (%d chars)", len(text))
        raw = await self.llm.raw_chat_completion(
            system=self._system_prompt,
            user=user_prompt,
            temperature=0.2,
        )
        result = _extract_json(raw)
        logger.info(
            "Classification complete: base=%s modules=%s",
            result.get("project_type", {}).get("base_category"),
            result.get("project_type", {}).get("modules"),
        )

        if self._cache is not None:
            self._cache.set(text, result, language=language)
        return result


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
