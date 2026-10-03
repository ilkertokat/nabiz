import time

from nabiz.app import create_app
from nabiz.db import Check


def test_create_and_list(client):
    r = client.post("/api/monitors", json={"name": "Site", "url": "https://site.test", "interval_sec": 30})
    assert r.status_code == 201
    body = r.get_json()
    assert body["status"] == "unknown" and body["interval_sec"] == 30
    assert len(client.get("/api/monitors").get_json()) == 1


def test_validation(client):
    assert client.post("/api/monitors", json={"name": "", "url": "https://x.test"}).status_code == 400
    assert client.post("/api/monitors", json={"name": "x", "url": "ftp://x.test"}).status_code == 400
    assert client.post("/api/monitors", json={"name": "x", "url": "https://x.test", "interval_sec": 1}).status_code == 400


def test_duplicate_url_conflict(client):
    client.post("/api/monitors", json={"name": "a", "url": "https://x.test"})
    assert client.post("/api/monitors", json={"name": "b", "url": "https://x.test"}).status_code == 409


def test_summary_reflects_checks(client, db):
    m = db.add_monitor("Site", "https://site.test")
    now = time.time()
    db.add_check(Check(m.id, now - 120, True, 200, 100.0, 60))
    db.add_check(Check(m.id, now - 60, False, 500, 80.0, 10, "HTTP 500"))
    one = client.get(f"/api/monitors/{m.id}").get_json()
    assert one["status"] == "down"
    assert one["uptime_24h"] == 50.0
    assert one["avg_response_ms"] == 90.0
    assert len(one["history"]) == 2
    s = client.get("/api/summary").get_json()
    assert s == {"total": 1, "up": 0, "down": 1, "ssl_warnings": 1}


def test_pause_and_delete(client, db):
    m = db.add_monitor("Site", "https://site.test")
    assert client.patch(f"/api/monitors/{m.id}", json={"paused": True}).get_json()["status"] == "paused"
    assert client.delete(f"/api/monitors/{m.id}").status_code == 204
    assert client.get(f"/api/monitors/{m.id}").status_code == 404


def test_token_protects_writes(db):
    app = create_app(db, token="gizli")
    c = app.test_client()
    assert c.post("/api/monitors", json={"name": "a", "url": "https://a.test"}).status_code == 401
    r = c.post("/api/monitors", json={"name": "a", "url": "https://a.test"},
               headers={"Authorization": "Bearer gizli"})
    assert r.status_code == 201
    assert c.get("/api/monitors").status_code == 200  # okuma serbest


def test_pages_served(client):
    assert client.get("/").status_code == 200
    assert client.get("/status").status_code == 200
    assert client.get("/health").get_json() == {"ok": True}


def test_patch_validates_interval(client, db):
    m = db.add_monitor("Site", "https://site.test")
    assert client.patch(f"/api/monitors/{m.id}", json={"interval_sec": 1}).status_code == 400
    assert client.patch(f"/api/monitors/{m.id}", json={"interval_sec": "abc"}).status_code == 400
    assert client.patch(f"/api/monitors/{m.id}", json={"interval_sec": 120}).get_json()["interval_sec"] == 120
