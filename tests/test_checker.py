import httpx

from nabiz import checker
from nabiz.db import Monitor


def make_monitor(url="http://ornek.test", keyword=None):
    return Monitor(id=1, name="Örnek", url=url, interval_sec=60, keyword=keyword,
                   timeout_sec=5, paused=False, created_at=0)


def client_with(handler):
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_up_when_200():
    c = client_with(lambda req: httpx.Response(200, text="merhaba"))
    r = checker.check(make_monitor(), client=c)
    assert r.up and r.status_code == 200 and r.error is None
    assert r.response_ms is not None and r.response_ms >= 0


def test_down_on_server_error():
    c = client_with(lambda req: httpx.Response(503))
    r = checker.check(make_monitor(), client=c)
    assert not r.up and r.error == "HTTP 503"


def test_keyword_missing_marks_down():
    c = client_with(lambda req: httpx.Response(200, text="bakım modu"))
    r = checker.check(make_monitor(keyword="Sepete ekle"), client=c)
    assert not r.up and "Anahtar kelime" in r.error


def test_keyword_present_is_up():
    c = client_with(lambda req: httpx.Response(200, text="... Sepete ekle ..."))
    assert checker.check(make_monitor(keyword="Sepete ekle"), client=c).up


def test_timeout_is_reported():
    def boom(req):
        raise httpx.ReadTimeout("yavaş", request=req)
    r = checker.check(make_monitor(), client=client_with(boom))
    assert not r.up and "Zaman aşımı" in r.error


def test_connection_error_is_reported():
    def boom(req):
        raise httpx.ConnectError("dns", request=req)
    r = checker.check(make_monitor(), client=client_with(boom))
    assert not r.up and "Bağlantı hatası" in r.error


def test_ssl_days_recorded_for_https():
    c = client_with(lambda req: httpx.Response(200))
    r = checker.check(make_monitor("https://ornek.test"), client=c, ssl_probe=lambda h, p: 42)
    assert r.up and r.ssl_days == 42


def test_expired_certificate_marks_down():
    c = client_with(lambda req: httpx.Response(200))
    r = checker.check(make_monitor("https://ornek.test"), client=c, ssl_probe=lambda h, p: -3)
    assert not r.up and "SSL" in r.error


def test_ssl_probe_failure_does_not_break_check():
    def probe(h, p):
        raise OSError("bağlanamadı")
    c = client_with(lambda req: httpx.Response(200))
    r = checker.check(make_monitor("https://ornek.test"), client=c, ssl_probe=probe)
    assert r.up and r.ssl_days is None
