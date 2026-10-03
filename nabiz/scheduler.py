"""Arka planda her monitörü kendi aralığında kontrol eden zamanlayıcı."""
from __future__ import annotations

import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor

import httpx

from . import checker
from .db import Database, Monitor
from .notifier import Notifier

log = logging.getLogger(__name__)
RETENTION_DAYS = 30


class Scheduler:
    def __init__(self, db: Database, notifier: Notifier | None = None,
                 workers: int = 8, tick: float = 1.0) -> None:
        self.db = db
        self.notifier = notifier or Notifier()
        self.tick = tick
        self._pool = ThreadPoolExecutor(max_workers=workers, thread_name_prefix="nabiz")
        self._client = httpx.Client(follow_redirects=True, headers={"User-Agent": checker.USER_AGENT})
        self._running: set[int] = set()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._last_purge = 0.0

    def due(self, monitor: Monitor, now: float) -> bool:
        """Monitörün kontrol zamanı geldi mi?"""
        if monitor.paused or monitor.id in self._running:
            return False
        last = self.db.last_check(monitor.id)
        return last is None or now - last.checked_at >= monitor.interval_sec

    def run_one(self, monitor: Monitor) -> None:
        try:
            previous = self.db.last_check(monitor.id)
            result = checker.check(monitor, client=self._client)
            self.db.add_check(result)
            if previous is not None and previous.up != result.up:
                self.notifier.notify(monitor, result)
        except Exception:  # pragma: no cover - zamanlayıcı asla çökmemeli
            log.exception("Kontrol başarısız: %s", monitor.url)
        finally:
            self._running.discard(monitor.id)

    def loop_once(self, now: float | None = None) -> int:
        now = now or time.time()
        started = 0
        for m in self.db.list_monitors():
            if self.due(m, now):
                self._running.add(m.id)
                self._pool.submit(self.run_one, m)
                started += 1
        if now - self._last_purge > 3600:
            self.db.purge_older_than(now - RETENTION_DAYS * 86400)
            self._last_purge = now
        return started

    def start(self) -> None:
        def _run():
            while not self._stop.is_set():
                self.loop_once()
                self._stop.wait(self.tick)
        self._thread = threading.Thread(target=_run, name="nabiz-scheduler", daemon=True)
        self._thread.start()
        log.info("Zamanlayıcı başladı")

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=5)
        self._pool.shutdown(wait=False)
        self._client.close()
