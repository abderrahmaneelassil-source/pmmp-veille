"""Garde-fous : ces tests échouent si quelqu'un assouplit les règles de collecte."""
import importlib
import re
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src" / "pmmp_collector"


def settings():
    import pmmp_collector.settings as s
    return importlib.reload(s)


def test_one_request_at_a_time():
    s = settings()
    assert s.CONCURRENT_REQUESTS == 1
    assert s.CONCURRENT_REQUESTS_PER_DOMAIN == 1


def test_delay_and_autothrottle():
    s = settings()
    assert s.DOWNLOAD_DELAY >= 1.0
    assert s.DOWNLOAD_DELAY_JITTER == 0
    assert s.AUTOTHROTTLE_ENABLED is True
    assert s.AUTOTHROTTLE_TARGET_CONCURRENCY <= 1.0


def test_no_aggressive_retry_and_robots():
    s = settings()
    assert s.RETRY_ENABLED is False
    assert s.ROBOTSTXT_OBEY is True


def test_declared_user_agent_and_no_proxy():
    s = settings()
    assert s.USER_AGENT.startswith("TACHFIR") and "contact" in s.USER_AGENT
    mws = s.DOWNLOADER_MIDDLEWARES
    assert mws["scrapy.downloadermiddlewares.httpproxy.HttpProxyMiddleware"] is None
    assert "pmmp_collector.middlewares.CircuitBreakerMiddleware" in mws
    assert "pmmp_collector.middlewares.TimeWindowMiddleware" in mws
    assert "pmmp_collector.middlewares.DeclaredUserAgentMiddleware" in mws


FORBIDDEN = re.compile(
    r"playwright|selenium|puppeteer|undetected|fake.?useragent|user_agents|rotating|proxy_pool|"
    r"2captcha|anticaptcha|capsolver|cloudscraper|curl_cffi|impersonate",
    re.I,
)


def test_no_circumvention_code():
    offenders = [
        f"{p.name}: {m.group(0)}"
        for p in SRC.rglob("*.py")
        for m in FORBIDDEN.finditer(p.read_text(encoding="utf-8"))
    ]
    assert offenders == []
