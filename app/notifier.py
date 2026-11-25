from __future__ import annotations

import logging

import requests

logger = logging.getLogger(__name__)


class TelegramNotifier:
    def __init__(self, token: str, chat_id: str):
        self.token = token.strip()
        self.chat_id = chat_id.strip()
        self.enabled = bool(self.token and self.chat_id)
        self.url = f"https://api.telegram.org/bot{self.token}/sendMessage" if self.enabled else ""

    def send(self, text: str) -> None:
        if not self.enabled:
            return
        try:
            response = requests.post(
                self.url,
                json={"chat_id": self.chat_id, "text": text},
                timeout=5,
            )
            response.raise_for_status()
        except Exception as exc:
            logger.error("텔레그램 알림 실패: %s", exc)
