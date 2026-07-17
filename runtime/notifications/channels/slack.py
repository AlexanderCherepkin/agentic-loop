from __future__ import annotations

import logging

import httpx

from .base import BaseNotifier, NotificationChannel, NotificationMessage, NotificationResult

logger = logging.getLogger(__name__)


class SlackNotifier(BaseNotifier):
    channel = NotificationChannel.SLACK

    def __init__(self, webhook_url: str) -> None:
        self.webhook_url = webhook_url

    async def send(self, to: str, message: NotificationMessage) -> NotificationResult:
        if not self.webhook_url:
            return NotificationResult(
                channel=self.channel.value, ok=False, detail="SLACK_WEBHOOK_URL is not set"
            )

        payload = {
            "text": message.subject,
            "blocks": [
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"*{message.subject}*\n\n{message.body_text}",
                    },
                }
            ],
        }
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.post(self.webhook_url, json=payload)
                resp.raise_for_status()
            logger.info("Slack webhook notification sent")
            return NotificationResult(channel=self.channel.value, ok=True)
        except Exception as exc:
            logger.exception("Slack notification failed")
            return NotificationResult(channel=self.channel.value, ok=False, detail=str(exc))
