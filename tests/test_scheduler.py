import time

from nabiz import scheduler as sched_mod
from nabiz.db import Check
from nabiz.scheduler import Scheduler


class FakeNotifier:
    def __init__(self):
        self.sent = []

    def notify(self, monitor, check):
        self.sent.append((monitor.name, check.up))


def test_due_respects_interval_and_pause(db):
    s = Scheduler(db, notifier=FakeNotifier())
    m = db.add_monitor("A", "https://a.test", interval_sec=60)
    now = time.time()
    assert s.due(m, now)
    db.add_check(Check(m.id, now - 10, True))
    assert not s.due(m, now)
    assert s.due(m, now + 60)
    paused = db.update_monitor(m.id, paused=True)
    assert not s.due(paused, now + 600)
    s.stop()


def test_notifies_only_on_state_change(db, monkeypatch):
    results = iter([True, True, False, False, True])
    monkeypatch.setattr(sched_mod.checker, "check",
                        lambda m, client=None: Check(m.id, time.time(), next(results)))
    n = FakeNotifier()
    s = Scheduler(db, notifier=n)
    m = db.add_monitor("A", "https://a.test")
    for _ in range(5):
        s.run_one(m)
    assert n.sent == [("A", False), ("A", True)]
    s.stop()
