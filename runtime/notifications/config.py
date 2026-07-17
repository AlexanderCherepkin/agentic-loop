from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any


@dataclass
class NotificationsConfig:
    channels: list[str] = field(default_factory=list)
    emails: list[str] = field(default_factory=list)
    telegram_chat_ids: list[str] = field(default_factory=list)
    telegram_bot_token: str | None = field(
        default_factory=lambda: os.environ.get("TELEGRAM_BOT_TOKEN")
    )
    slack_webhook_url: str | None = field(
        default_factory=lambda: os.environ.get("SLACK_WEBHOOK_URL")
    )
    smtp_host: str | None = field(default_factory=lambda: os.environ.get("SMTP_HOST"))
    smtp_port: int = field(default_factory=lambda: int(os.environ.get("SMTP_PORT", "587")))
    smtp_user: str | None = field(default_factory=lambda: os.environ.get("SMTP_USER"))
    smtp_password: str | None = field(default_factory=lambda: os.environ.get("SMTP_PASSWORD"))
    notification_from_email: str | None = field(
        default_factory=lambda: os.environ.get("NOTIFICATION_FROM_EMAIL")
    )
    smtp_use_tls: bool = field(
        default_factory=lambda: os.environ.get("SMTP_USE_TLS", "true").lower()
        not in ("false", "0", "off", "no")
    )

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "NotificationsConfig":
        return cls(
            channels=list(data.get("channels") or []),
            emails=list(data.get("emails") or []),
            telegram_chat_ids=list(data.get("telegram_chat_ids") or []),
            telegram_bot_token=data.get("telegram_bot_token"),
            slack_webhook_url=data.get("slack_webhook_url"),
            smtp_host=data.get("smtp_host"),
            smtp_port=int(data.get("smtp_port", 587)),
            smtp_user=data.get("smtp_user"),
            smtp_password=data.get("smtp_password"),
            notification_from_email=data.get("notification_from_email"),
            smtp_use_tls=bool(data.get("smtp_use_tls", True)),
        )
