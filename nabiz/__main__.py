"""Komut satırı: `python -m nabiz` paneli ve zamanlayıcıyı birlikte başlatır."""
from __future__ import annotations

import argparse
import logging

from .app import create_app
from .db import Database
from .scheduler import Scheduler


def main() -> None:
    p = argparse.ArgumentParser(prog="nabiz", description="Site izleme ve SSL takip paneli")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8080)
    p.add_argument("--db", default="nabiz.db", help="SQLite dosyası")
    p.add_argument("--no-scheduler", action="store_true", help="Yalnız paneli çalıştır")
    args = p.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    db = Database(args.db)
    if not args.no_scheduler:
        Scheduler(db).start()
    create_app(db).run(host=args.host, port=args.port)


if __name__ == "__main__":
    main()
