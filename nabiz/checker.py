"""Tek bir siteyi kontrol eder: HTTP durumu, yanıt süresi, anahtar kelime ve SSL bitiş tarihi."""
from __future__ import annotations

import socket
import ssl
import time
from datetime import datetime, timezone
from urllib.parse import urlparse

import httpx

from .db import Check, Monitor

USER_AGENT = "Nabiz/1.0 (+https://github.com/ilkertokat/nabiz)"


def ssl_days_left(host: str, port: int = 443, timeout: float = 5.0) -> int:
    """Sertifikanın bitmesine kalan gün sayısı (negatifse süresi dolmuş)."""
    ctx = ssl.create_default_context()
    with socket.create_connection((host, port), timeout=timeout) as sock:
        with ctx.wrap_socket(sock, server_hostname=host) as tls:
            cert = tls.getpeercert()
    expires = datetime.strptime(cert["notAfter"], "%b %d %H:%M:%S %Y %Z").replace(tzinfo=timezone.utc)
    return (expires - datetime.now(timezone.utc)).days


def check(monitor: Monitor, client: httpx.Client | None = None,
          ssl_probe=ssl_days_left) -> Check:
    """Monitörü bir kez kontrol eder ve sonucu döndürür; hiçbir zaman istisna fırlatmaz."""
    own_client = client is None
    client = client or httpx.Client(follow_redirects=True, headers={"User-Agent": USER_AGENT})
    started = time.perf_counter()
    result = Check(monitor_id=monitor.id, checked_at=time.time(), up=False)
    try:
        resp = client.get(monitor.url, timeout=monitor.timeout_sec)
        result.response_ms = round((time.perf_counter() - started) * 1000, 1)
        result.status_code = resp.status_code
        if resp.status_code >= 400:
            result.error = f"HTTP {resp.status_code}"
        elif monitor.keyword and monitor.keyword not in resp.text:
            result.error = f"Anahtar kelime bulunamadı: {monitor.keyword!r}"
        else:
            result.up = True
    except httpx.TimeoutException:
        result.error = f"Zaman aşımı ({monitor.timeout_sec:g} sn)"
    except httpx.HTTPError as exc:
        result.error = f"Bağlantı hatası: {type(exc).__name__}"
    finally:
        if own_client:
            client.close()

    parsed = urlparse(monitor.url)
    if parsed.scheme == "https" and parsed.hostname:
        try:
            result.ssl_days = ssl_probe(parsed.hostname, parsed.port or 443)
            if result.ssl_days < 0:
                result.up = False
                result.error = result.error or "SSL sertifikasının süresi dolmuş"
        except (OSError, ssl.SSLError, ValueError, KeyError):
            pass  # SSL bilgisi alınamazsa sitenin durumu yine de geçerli
    return result
