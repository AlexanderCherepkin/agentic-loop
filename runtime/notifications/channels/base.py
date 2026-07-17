from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum


class NotificationChannel(str, Enum):
    EMAIL = "email"
    TELEGRAM = "telegram"
    SLACK = "slack"


@dataclass
class NotificationMessage:
    subject: str
    body_text: str
    body_html: str | None = None


@dataclass
class NotificationResult:
    channel: str
    ok: bool
    detail: str | None = None


class BaseNotifier(ABC):
    channel: NotificationChannel

    @abstractmethod
    async def send(self, to: str, message: NotificationMessage) -> NotificationResult:
        ...
