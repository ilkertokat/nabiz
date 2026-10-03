"""Flask uygulaması: REST API + yönetim paneli + herkese açık durum sayfası."""
from __future__ import annotations

import os
import time
from functools import wraps
from urllib.parse import urlparse

from flask import Flask, abort, jsonify, request, send_from_directory

from .db import Database

DAY = 86400


def _valid_url(url: str) -> bool:
    p = urlparse(url or "")
    return p.scheme in ("http", "https") and bool(p.netloc)


def summary(db: Database, monitor, now: float | None = None) -> dict:
    """Panelde gösterilen özet: son durum, uptime yüzdeleri, son 24 saatin yanıt süreleri."""
    now = now or time.time()
    last = db.last_check(monitor.id)
    recent = db.checks_since(monitor.id, now - DAY)
    times = [c.response_ms for c in recent if c.response_ms is not None]
    return {
        **monitor.to_dict(),
        "status": "paused" if monitor.paused else ("unknown" if last is None else ("up" if last.up else "down")),
        "last_check": last.to_dict() if last else None,
        "uptime_24h": db.uptime(monitor.id, now - DAY),
        "uptime_7d": db.uptime(monitor.id, now - 7 * DAY),
        "uptime_30d": db.uptime(monitor.id, now - 30 * DAY),
        "avg_response_ms": round(sum(times) / len(times), 1) if times else None,
        "history": [{"t": c.checked_at, "up": c.up, "ms": c.response_ms} for c in recent[-90:]],
    }


def create_app(db: Database | None = None, token: str | None = None) -> Flask:
    app = Flask(__name__, static_folder="static", static_url_path="/static")
    app.config["DB"] = db or Database(os.getenv("NABIZ_DB", "nabiz.db"))
    app.config["TOKEN"] = token if token is not None else os.getenv("NABIZ_TOKEN")

    def get_db() -> Database:
        return app.config["DB"]

    def write_protected(fn):
        """Yazma işlemleri NABIZ_TOKEN tanımlıysa Bearer token ister."""
        @wraps(fn)
        def inner(*a, **kw):
            expected = app.config["TOKEN"]
            if expected and request.headers.get("Authorization") != f"Bearer {expected}":
                return jsonify(error="Yetkisiz"), 401
            return fn(*a, **kw)
        return inner

    # --- sayfalar ------------------------------------------------------------
    @app.get("/")
    def dashboard():
        return send_from_directory(app.static_folder, "index.html")

    @app.get("/status")
    def status_page():
        return send_from_directory(app.static_folder, "status.html")

    @app.get("/health")
    def health():
        return jsonify(ok=True)

    # --- API -----------------------------------------------------------------
    @app.get("/api/monitors")
    def list_monitors():
        db = get_db()
        return jsonify([summary(db, m) for m in db.list_monitors()])

    @app.post("/api/monitors")
    @write_protected
    def create_monitor():
        data = request.get_json(silent=True) or {}
        name, url = (data.get("name") or "").strip(), (data.get("url") or "").strip()
        if not name or not _valid_url(url):
            return jsonify(error="Geçerli bir ad ve http(s) adresi gerekli"), 400
        interval = int(data.get("interval_sec", 60))
        if not 10 <= interval <= 86400:
            return jsonify(error="Kontrol aralığı 10 sn ile 1 gün arasında olmalı"), 400
        db = get_db()
        if any(m.url == url for m in db.list_monitors()):
            return jsonify(error="Bu adres zaten izleniyor"), 409
        m = db.add_monitor(name, url, interval, data.get("keyword") or None,
                           float(data.get("timeout_sec", 10)))
        return jsonify(summary(db, m)), 201

    @app.get("/api/monitors/<int:mid>")
    def get_monitor(mid: int):
        db = get_db()
        m = db.get_monitor(mid) or abort(404)
        return jsonify(summary(db, m))

    @app.patch("/api/monitors/<int:mid>")
    @write_protected
    def update_monitor(mid: int):
        db = get_db()
        db.get_monitor(mid) or abort(404)
        data = request.get_json(silent=True) or {}
        if "url" in data and not _valid_url(data["url"]):
            return jsonify(error="Geçersiz adres"), 400
        m = db.update_monitor(mid, **data)
        return jsonify(summary(db, m))

    @app.delete("/api/monitors/<int:mid>")
    @write_protected
    def delete_monitor(mid: int):
        return ("", 204) if get_db().delete_monitor(mid) else abort(404)

    @app.get("/api/monitors/<int:mid>/checks")
    def monitor_checks(mid: int):
        db = get_db()
        db.get_monitor(mid) or abort(404)
        hours = min(int(request.args.get("hours", 24)), 24 * 30)
        return jsonify([c.to_dict() for c in db.checks_since(mid, time.time() - hours * 3600)])

    @app.get("/api/summary")
    def overall():
        db = get_db()
        items = [summary(db, m) for m in db.list_monitors()]
        return jsonify(
            total=len(items),
            up=sum(i["status"] == "up" for i in items),
            down=sum(i["status"] == "down" for i in items),
            ssl_warnings=sum(1 for i in items if i["last_check"] and i["last_check"]["ssl_days"] is not None
                             and i["last_check"]["ssl_days"] < 14),
        )

    @app.errorhandler(404)
    def not_found(_):
        return jsonify(error="Bulunamadı"), 404

    return app
