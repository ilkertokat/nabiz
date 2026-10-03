import time

from nabiz.db import Check


def test_add_and_list_monitors(db):
    db.add_monitor("B", "https://b.test")
    db.add_monitor("A", "https://a.test", interval_sec=30, keyword="ok")
    names = [m.name for m in db.list_monitors()]
    assert names == ["A", "B"]
    a = db.list_monitors()[0]
    assert a.interval_sec == 30 and a.keyword == "ok" and not a.paused


def test_update_ignores_unknown_fields(db):
    m = db.add_monitor("A", "https://a.test")
    m2 = db.update_monitor(m.id, paused=True, name="A2", id=999, created_at=1)
    assert m2.paused and m2.name == "A2" and m2.id == m.id


def test_delete_cascades_checks(db):
    m = db.add_monitor("A", "https://a.test")
    db.add_check(Check(m.id, time.time(), True, 200, 50))
    assert db.delete_monitor(m.id)
    assert db.last_check(m.id) is None
    assert not db.delete_monitor(m.id)


def test_uptime_percentage(db):
    m = db.add_monitor("A", "https://a.test")
    now = time.time()
    for i, up in enumerate([True, True, True, False]):
        db.add_check(Check(m.id, now - i, up))
    assert db.uptime(m.id, now - 100) == 75.0
    assert db.uptime(m.id, now + 100) is None


def test_purge_old_checks(db):
    m = db.add_monitor("A", "https://a.test")
    now = time.time()
    db.add_check(Check(m.id, now - 40 * 86400, True))
    db.add_check(Check(m.id, now, True))
    assert db.purge_older_than(now - 30 * 86400) == 1
    assert len(db.checks_since(m.id, 0)) == 1
