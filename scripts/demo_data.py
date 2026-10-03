"""Ekran görüntüsü ve deneme için sahte geçmişi olan bir demo veritabanı üretir.

    python scripts/demo_data.py demo.db && python -m nabiz --db demo.db --no-scheduler
"""
import random
import sys
import time

from nabiz.db import Check, Database

SITES = [
    ("Kurumsal Site", "https://kurumsal.example.com", 0.995, 180, 210),
    ("E-ticaret Mağazası", "https://magaza.example.com", 0.985, 420, 61),
    ("Rezervasyon API", "https://api.example.com/health", 1.0, 95, 12),
    ("Blog", "https://blog.example.com", 0.97, 260, 145),
    ("Dijital Menü", "https://menu.example.com", 0.999, 140, 88),
]


def main(path: str) -> None:
    random.seed(4)
    db = Database(path)
    now = time.time()
    for name, url, reliability, base_ms, ssl_days in SITES:
        m = db.add_monitor(name, url, interval_sec=300)
        t = now - 7 * 86400
        while t < now:
            up = random.random() < reliability
            if name == "E-ticaret Mağazası" and now - t < 900:
                up = False  # panelde canlı bir kesinti görünsün
            ms = round(random.gauss(base_ms, base_ms * 0.18), 1) if up else None
            db.add_check(Check(m.id, t, up, 200 if up else 503, ms, ssl_days,
                               None if up else "HTTP 503"))
            t += 300
    print(f"Demo veritabanı hazır: {path}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "demo.db")
