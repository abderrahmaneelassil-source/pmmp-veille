from datetime import datetime, time
from zoneinfo import ZoneInfo

import pytest

from pmmp_collector.config import ConfigError, is_within_window, load_config, parse_window

TZ = ZoneInfo("Africa/Casablanca")


def at(h, m=0):
    return datetime(2026, 9, 23, h, m, tzinfo=TZ)


def test_parse_window():
    assert parse_window("23:00-06:00") == (time(23, 0), time(6, 0))
    with pytest.raises(ConfigError):
        parse_window("23h-6h")
    with pytest.raises(ConfigError):
        parse_window("02:00-02:00")


@pytest.mark.parametrize("h,m,expected", [
    (23, 0, True), (23, 59, True), (0, 30, True), (5, 59, True),
    (6, 0, False), (12, 0, False), (22, 59, False),
])
def test_window_crossing_midnight(h, m, expected):
    assert is_within_window(at(h, m), time(23, 0), time(6, 0)) is expected


def test_window_same_day():
    assert is_within_window(at(13), time(12, 0), time(14, 0))
    assert not is_within_window(at(14), time(12, 0), time(14, 0))


def test_delay_floor(monkeypatch):
    monkeypatch.setenv("PMMP_DOWNLOAD_DELAY", "0.2")
    with pytest.raises(ConfigError):
        load_config()


@pytest.mark.parametrize("ua", ["Scrapy/2.11 (+https://scrapy.org)", "Mozilla/5.0 (Windows NT 10.0)"])
def test_user_agent_must_identify_tachfir(monkeypatch, ua):
    monkeypatch.setenv("PMMP_USER_AGENT", ua)
    with pytest.raises(ConfigError):
        load_config()


def test_circuit_breaker_bounds(monkeypatch):
    monkeypatch.setenv("PMMP_CB_MAX_CONSECUTIVE", "0")
    with pytest.raises(ConfigError):
        load_config()
