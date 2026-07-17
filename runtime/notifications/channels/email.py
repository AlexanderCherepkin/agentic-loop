from __future__ import annotations

import logging

import httpx

from .base import BaseNotifier, NotificationChannel, NotificationMessage, NotificationResult

logger = logging.getLogger(__name__)


class EmailNotifier(BaseNotifier):
    channel = NotificationChannel.EMAIL

    def __init__(
        self,
        host: str,
        port: int,
        user: str | None,
        password: str | None,
        from_addr: str | None,
        use_tls: bool = True,
    ) -> None:
        self.host = host
        self.port = port
        self.user = user
        self.password = password
        self.from_addr = from_addr
        self.use_tls = use_tls

    async def send(self, to: str, message: NotificationMessage) -> NotificationResult:
        try:
            import aiosmtplib
        except ImportError as exc:
            logger.warning("aiosmtplib is not installed; email notifications are unavailable")
            return NotificationResult(
                channel=self.channel.value, ok=False, detail=f"aiosmtplib not installed: {exc}"
            )

        if not self.host or not self.from_addr:
            return NotificationResult(
                channel=self.channel.value,
                ok=False,
                detail="SMTP host or from_addr is not configured",
            )

        try:
            await aiosmtplib.send(
                message.body_text,
                sender=self.from_addr,
                recipients=[to],
                subject=message.subject,
                hostname=self.host,
                port=self.port,
                username=self.user,
                password=self.password,
                use_tls=self.use_tls,
                start_tls=not self.use_tls and self.port == 587,
            )
            logger.info("Email sent to %s", to)
            return NotificationResult(channel=self.channel.value, ok=True)
        except Exception as exc:
            logger.exception("Email notification failed")
            return NotificationResult(channel=self.channel.value, ok=False, detail=str(exc))
