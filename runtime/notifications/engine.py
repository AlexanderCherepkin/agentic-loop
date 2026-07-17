from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from .channels import (
    BaseNotifier,
    EmailNotifier,
    NotificationChannel,
    NotificationMessage,
    NotificationResult,
    SlackNotifier,
    TelegramNotifier,
)
from .config import NotificationsConfig

logger = logging.getLogger(__name__)


@dataclass
class NotificationPayload:
    project_id: str
    status: str
    brief: str = ""
    message: str = ""
    review_score: float | None = None
    security_risk: str | None = None
    tests_count: int | None = None
    ci_files_count: int | None = None
    has_openapi: bool = False
    url: str | None = None
    error: str | None = None


@dataclass
class DispatchResult:
    results: list[NotificationResult] = field(default_factory=list)
    dispatched: int = 0
    failed: int = 0


class NotificationsEngine:
    """Dispatch pipeline completion notifications through configured channels."""

    def __init__(self, config: NotificationsConfig | None = None):
        self.config = config or NotificationsConfig()
        self._notifiers: dict[NotificationChannel, BaseNotifier] = {
            NotificationChannel.EMAIL: EmailNotifier(
                host=self.config.smtp_host or "",
                port=self.config.smtp_port,
                user=self.config.smtp_user,
                password=self.config.smtp_password,
                from_addr=self.config.notification_from_email or self.config.smtp_user,
                use_tls=self.config.smtp_use_tls,
            ),
            NotificationChannel.TELEGRAM: TelegramNotifier(
                bot_token=self.config.telegram_bot_token or ""
            ),
            NotificationChannel.SLACK: SlackNotifier(
                webhook_url=self.config.slack_webhook_url or ""
            ),
        }

    def _build_message(self, payload: NotificationPayload) -> NotificationMessage:
        status_emoji = {
            "completed": "✅",
            "failed": "❌",
            "security_failed": "🛡️",
            "code_pending": "⏸️",
            "architecture_pending": "⏸️",
        }.get(payload.status, "ℹ️")

        subject = f"{status_emoji} Pipeline {payload.project_id}: {payload.status}"
        lines = [
            f"Project: `{payload.project_id}`",
            f"Status: {payload.status}",
        ]
        if payload.brief:
            lines.append(
                f"Brief: {payload.brief[:200]}{'...' if len(payload.brief) > 200 else ''}"
            )
        if payload.review_score is not None:
            lines.append(f"Review score: {payload.review_score}")
        if payload.security_risk:
            lines.append(f"Security risk: {payload.security_risk}")
        if payload.tests_count is not None:
            lines.append(f"Tests files: {payload.tests_count}")
        if payload.url:
            lines.append(f"URL: {payload.url}")
        if payload.error:
            lines.append(f"Error: {payload.error}")
        if payload.message:
            lines.append(f"\n{payload.message}")

        return NotificationMessage(subject=subject, body_text="\n".join(lines))

    async def dispatch(self, payload: NotificationPayload) -> DispatchResult:
        result = DispatchResult()
        if not self.config.channels:
            logger.debug("Notifications disabled: no channels configured")
            return result

        message = self._build_message(payload)
        for channel_str in self.config.channels:
            try:
                channel = NotificationChannel(channel_str)
            except ValueError:
                logger.warning("Unknown notification channel: %s", channel_str)
                continue

            recipients = self._recipients_for(channel)
            if not recipients:
                logger.warning("Channel %s enabled but no recipients configured", channel.value)
                continue

            notifier = self._notifiers[channel]
            for recipient in recipients:
                notification = await notifier.send(recipient, message)
                result.results.append(notification)
                if notification.ok:
                    result.dispatched += 1
                else:
                    result.failed += 1

        return result

    def _recipients_for(self, channel: NotificationChannel) -> list[str]:
        if channel == NotificationChannel.EMAIL:
            return list(self.config.emails)
        if channel == NotificationChannel.TELEGRAM:
            return list(self.config.telegram_chat_ids)
        if channel == NotificationChannel.SLACK:
            return ["webhook"]
        return []
