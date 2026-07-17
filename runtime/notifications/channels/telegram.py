from __future__ import annotations

import logging

import httpx

from .base import BaseNotifier, NotificationChannel, NotificationMessage, NotificationResult

logger = logging.getLogger(__name__)


class TelegramNotifier(BaseNotifier):
    channel = NotificationChannel.TELEGRAM

    def __init__(self, bot_token: str) -> None:
        self.bot_token = bot_token

    async def send(self, to: str, message: NotificationMessage) -> NotificationResult:
        if not self.bot_token:
            return NotificationResult(
                channel=self.channel.value, ok=False, detail="TELEGRAM_BOT_TOKEN is not set"
            )

        url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
        payload = {
            "chat_id": to,
            "text": f"*{message.subject}*\n\n{message.body_text}",
            "parse_mode": "Markdown",
        }
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.post(url, json=payload)
                resp.raise_for_status()
            logger.info("Telegram message sent to chat %s", to)
            return NotificationResult(channel=self.channel.value, ok=True)
        except Exception as exc:
            logger.exception("Telegram notification failed")
            return NotificationResult(channel=self.channel.value, ok=False, detail=str(exc))
