"""SQLite veri katmanı.

Tek dosyalık bir veritabanı yeterli: izlenen siteler (monitors) ve her kontrolün
sonucu (checks). Bağlantılar iş parçacığı başına açılır; yazmalar kısa sürer.
"""
from __future__ import annotations

import sqlite3
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass, asdict
from typing import Iterator

SCHEMA = """
CREATE TABLE IF NOT EXISTS monitors (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    name         TEXT    NOT NULL,
    url          TEXT    NOT NULL UNIQUE,
    interval_sec INTEGER NOT NULL DEFAULT 60,
    keyword      TEXT,
    timeout_sec  REAL    NOT NULL DEFAULT 10,
    paused       INTEGER NOT NULL DEFAULT 0,
    created_at   REAL    NOT NULL
);
CREATE TABLE IF NOT EXISTS checks (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    monitor_id   INTEGER NOT NULL REFERENCES monitors(id) ON DELETE CASCADE,
    checked_at   REAL    NOT NULL,
    up           INTEGER NOT NULL,
    status_code  INTEGER,
    response_ms  REAL,
    ssl_days     INTEGER,
    error        TEXT
);
CREATE INDEX IF NOT EXISTS idx_checks_monitor_time ON checks(monitor_id, checked_at);
"""


@dataclass
class Monitor:
    id: int
    name: str
    url: str
    interval_sec: int
    keyword: str | None
    timeout_sec: float
    paused: bool
    created_at: float

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Check:
    monitor_id: int
    checked_at: float
    up: bool
    status_code: int | None = None
    response_ms: float | None = None
    ssl_days: int | None = None
    error: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)


class Database:
    def __init__(self, path: str = "nabiz.db") -> None:
        self.path = path
        self._local = threading.local()
        self._lock = threading.Lock()
        with self.conn() as c:
            c.executescript(SCHEMA)

    # --- bağlantı -----------------------------------------------------------
    def _connection(self) -> sqlite3.Connection:
        conn = getattr(self._local, "conn", None)
        if conn is None:
            conn = sqlite3.connect(self.path, check_same_thread=False)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA foreign_keys = ON")
            conn.execute("PRAGMA journal_mode = WAL")
            self._local.conn = conn
        return conn

    @contextmanager
    def conn(self) -> Iterator[sqlite3.Connection]:
        c = self._connection()
        with self._lock:
            try:
                yield c
                c.commit()
            except Exception:
                c.rollback()
                raise

    # --- monitörler ---------------------------------------------------------
    def add_monitor(self, name: str, url: str, interval_sec: int = 60,
                    keyword: str | None = None, timeout_sec: float = 10) -> Monitor:
        with self.conn() as c:
            cur = c.execute(
                "INSERT INTO monitors(name, url, interval_sec, keyword, timeout_sec, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (name, url, interval_sec, keyword, timeout_sec, time.time()),
            )
            mid = cur.lastrowid
        return self.get_monitor(mid)  # type: ignore[return-value]

    def get_monitor(self, monitor_id: int) -> Monitor | None:
        with self.conn() as c:
            row = c.execute("SELECT * FROM monitors WHERE id = ?", (monitor_id,)).fetchone()
        return _monitor(row) if row else None

    def list_monitors(self) -> list[Monitor]:
        with self.conn() as c:
            rows = c.execute("SELECT * FROM monitors ORDER BY name").fetchall()
        return [_monitor(r) for r in rows]

    def update_monitor(self, monitor_id: int, **fields) -> Monitor | None:
        allowed = {"name", "url", "interval_sec", "keyword", "timeout_sec", "paused"}
        fields = {k: v for k, v in fields.items() if k in allowed}
        if fields:
            sets = ", ".join(f"{k} = ?" for k in fields)
            with self.conn() as c:
                c.execute(f"UPDATE monitors SET {sets} WHERE id = ?", (*fields.values(), monitor_id))
        return self.get_monitor(monitor_id)

    def delete_monitor(self, monitor_id: int) -> bool:
        with self.conn() as c:
            cur = c.execute("DELETE FROM monitors WHERE id = ?", (monitor_id,))
        return cur.rowcount > 0

    # --- kontroller ---------------------------------------------------------
    def add_check(self, check: Check) -> None:
        with self.conn() as c:
            c.execute(
                "INSERT INTO checks(monitor_id, checked_at, up, status_code, response_ms, ssl_days, error) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (check.monitor_id, check.checked_at, int(check.up), check.status_code,
                 check.response_ms, check.ssl_days, check.error),
            )

    def last_check(self, monitor_id: int) -> Check | None:
        with self.conn() as c:
            row = c.execute(
                "SELECT * FROM checks WHERE monitor_id = ? ORDER BY checked_at DESC LIMIT 1",
                (monitor_id,),
            ).fetchone()
        return _check(row) if row else None

    def checks_since(self, monitor_id: int, since: float) -> list[Check]:
        with self.conn() as c:
            rows = c.execute(
                "SELECT * FROM checks WHERE monitor_id = ? AND checked_at >= ? ORDER BY checked_at",
                (monitor_id, since),
            ).fetchall()
        return [_check(r) for r in rows]

    def uptime(self, monitor_id: int, since: float) -> float | None:
        """Belirtilen andan beri başarılı kontrollerin yüzdesi (kontrol yoksa None)."""
        with self.conn() as c:
            row = c.execute(
                "SELECT COUNT(*) AS n, SUM(up) AS ok FROM checks WHERE monitor_id = ? AND checked_at >= ?",
                (monitor_id, since),
            ).fetchone()
        if not row["n"]:
            return None
        return round(100.0 * (row["ok"] or 0) / row["n"], 2)

    def purge_older_than(self, cutoff: float) -> int:
        with self.conn() as c:
            cur = c.execute("DELETE FROM checks WHERE checked_at < ?", (cutoff,))
        return cur.rowcount


def _monitor(r: sqlite3.Row) -> Monitor:
    return Monitor(id=r["id"], name=r["name"], url=r["url"], interval_sec=r["interval_sec"],
                   keyword=r["keyword"], timeout_sec=r["timeout_sec"], paused=bool(r["paused"]),
                   created_at=r["created_at"])


def _check(r: sqlite3.Row) -> Check:
    return Check(monitor_id=r["monitor_id"], checked_at=r["checked_at"], up=bool(r["up"]),
                 status_code=r["status_code"], response_ms=r["response_ms"],
                 ssl_days=r["ssl_days"], error=r["error"])
