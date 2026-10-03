"""Durum değişince bildirim gönderir (Telegram ve/veya genel webhook).

Yalnızca durum DEĞİŞTİĞİNDE (çalışıyor → çöktü ya da tersi) bildirim atılır;
böylece her kontrolde aynı uyarı tekrar tekrar gelmez.
"""
from __future__ import annotations

import logging
import os

import httpx

from .db import Check, Monitor

log = logging.getLogger(__name__)


class Notifier:
    def __init__(self, telegram_token: str | None = None, telegram_chat: str | None = None,
                 webhook_url: str | None = None, client: httpx.Client | None = None) -> None:
        self.telegram_token = telegram_token or os.getenv("NABIZ_TELEGRAM_TOKEN")
        self.telegram_chat = telegram_chat or os.getenv("NABIZ_TELEGRAM_CHAT")
        self.webhook_url = webhook_url or os.getenv("NABIZ_WEBHOOK_URL")
        self.client = client or httpx.Client(timeout=10)

    @property
    def enabled(self) -> bool:
        return bool((self.telegram_token and self.telegram_chat) or self.webhook_url)

    @staticmethod
    def message(monitor: Monitor, check: Check) -> str:
        if check.up:
            return f"✅ {monitor.name} yeniden çalışıyor ({check.response_ms:.0f} ms) — {monitor.url}"
        return f"🔴 {monitor.name} erişilemiyor: {check.error} — {monitor.url}"

    def notify(self, monitor: Monitor, check: Check) -> None:
        if not self.enabled:
            return
        text = self.message(monitor, check)
        try:
            if self.telegram_token and self.telegram_chat:
                self.client.post(
                    f"https://api.telegram.org/bot{self.telegram_token}/sendMessage",
                    json={"chat_id": self.telegram_chat, "text": text},
                )
            if self.webhook_url:
                self.client.post(self.webhook_url, json={
                    "monitor": monitor.to_dict(), "check": check.to_dict(), "text": text,
                })
        except httpx.HTTPError as exc:  # bildirim hatası izlemeyi durdurmamalı
            log.warning("Bildirim gönderilemedi: %s", exc)
