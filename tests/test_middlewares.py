from types import SimpleNamespace

import pytest
from scrapy.exceptions import IgnoreRequest
from scrapy.http import HtmlResponse, Request

from pmmp_collector.config import load_config
from pmmp_collector.middlewares import (
    REASON_CIRCUIT_BREAKER,
    REASON_REFUSED_WINDOW,
    REASON_WINDOW_ENDED,
    CircuitBreakerMiddleware,
    DeclaredUserAgentMiddleware,
    TimeWindowMiddleware,
)


class FakeStats:
    def __init__(self):
        self.values = {}

    def inc_value(self, key, count=1):
        self.values[key] = self.values.get(key, 0) + count

    def set_value(self, key, value):
        self.values[key] = value


SPIDER = SimpleNamespace(force=False)


class FakeCrawler:
    def __init__(self):
        self.stats = FakeStats()
        self.closed = []
        self.engine = SimpleNamespace(close_spider_async=lambda reason: self.closed.append(reason))
        self.spider = SPIDER


def resp(status=200, latency=0.5, **meta):
    req = Request("https://www.marchespublics.gov.ma/pmmp/x", meta={"download_latency": latency, **meta})
    return req, HtmlResponse(req.url, status=status, body=b"<html></html>", request=req)


def breaker(n=3, slow=15):
    crawler = FakeCrawler()
    return crawler, CircuitBreakerMiddleware(crawler, n, slow)


def test_trips_after_n_consecutive_5xx():
    crawler, mw = breaker()
    for _ in range(2):
        mw.process_response(*resp(503), SPIDER)
    assert crawler.closed == []
    mw.process_response(*resp(500), SPIDER)
    assert crawler.closed == [REASON_CIRCUIT_BREAKER]
    with pytest.raises(IgnoreRequest):
        mw.process_request(Request("https://www.marchespublics.gov.ma/pmmp/y"), SPIDER)


def test_success_resets_counter():
    crawler, mw = breaker()
    mw.process_response(*resp(502), SPIDER)
    mw.process_response(*resp(502), SPIDER)
    mw.process_response(*resp(200), SPIDER)
    mw.process_response(*resp(502), SPIDER)
    mw.process_response(*resp(502), SPIDER)
    assert crawler.closed == []


def test_timeouts_and_slow_responses_count():
    crawler, mw = breaker()
    req = Request("https://www.marchespublics.gov.ma/pmmp/x")
    mw.process_exception(req, TimeoutError("timeout"), SPIDER)
    mw.process_response(*resp(200, latency=40), SPIDER)
    mw.process_exception(req, ConnectionError("reset"), SPIDER)
    assert crawler.closed == [REASON_CIRCUIT_BREAKER]
    assert "timeout" in crawler.stats.values["pmmp/circuit_breaker/reason"]


def test_large_dce_is_not_counted_as_slow():
    crawler, mw = breaker(n=1)
    mw.process_response(*resp(200, latency=120, dce_download=True), SPIDER)
    assert crawler.closed == []


@pytest.mark.parametrize("status", [403, 429])
def test_refusal_statuses_stop_immediately(status):
    crawler, mw = breaker()
    with pytest.raises(IgnoreRequest):
        mw.process_response(*resp(status), SPIDER)
    assert crawler.closed == [REASON_CIRCUIT_BREAKER]


def test_user_agent_is_forced():
    mw = DeclaredUserAgentMiddleware("TACHFIR-VeilleMarchesPublics/1.0 (+contact: sales@tachfir.com)")
    req = Request("https://x", headers={"User-Agent": "Mozilla/5.0"})
    mw.process_request(req, SPIDER)
    assert req.headers["User-Agent"].startswith(b"TACHFIR")


def _window_mw(inside: bool):
    cfg = load_config()
    fake_cfg = SimpleNamespace(in_window=lambda: inside, window_spec=cfg.window_spec, tz=cfg.tz)
    crawler = FakeCrawler()
    return crawler, TimeWindowMiddleware(crawler, fake_cfg)


def test_refuses_to_start_outside_window():
    crawler, mw = _window_mw(inside=False)
    with pytest.raises(IgnoreRequest):
        mw.process_request(Request("https://x"), SPIDER)
    assert crawler.closed == [REASON_REFUSED_WINDOW]


def test_stops_when_window_ends_mid_run():
    crawler, mw = _window_mw(inside=True)
    mw.process_request(Request("https://x"), SPIDER)
    mw.cfg.in_window = lambda: False
    with pytest.raises(IgnoreRequest):
        mw.process_request(Request("https://x/2"), SPIDER)
    assert crawler.closed == [REASON_WINDOW_ENDED]


def test_force_bypasses_window_only():
    crawler, mw = _window_mw(inside=False)
    assert mw.process_request(Request("https://x"), SimpleNamespace(force=True)) is None
    assert crawler.closed == []
