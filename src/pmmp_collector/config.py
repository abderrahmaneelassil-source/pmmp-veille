"""Lecture et validation de la configuration (variables d'environnement / .env).

Toutes les valeurs viennent de l'environnement. Les règles de collecte ont des
planchers codés en dur : une valeur trop agressive dans le .env est refusée au
démarrage au lieu d'être appliquée.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass
from datetime import datetime, time
from pathlib import Path
from zoneinfo import ZoneInfo

from dotenv import find_dotenv, load_dotenv

# Charge le .env du répertoire courant (ou d'un parent) sans écraser l'environnement réel.
load_dotenv(find_dotenv(usecwd=True), override=False)

# Planchers non négociables (consignes du chef de projet).
MIN_DOWNLOAD_DELAY = 1.0
MAX_CB_CONSECUTIVE = 10


class ConfigError(RuntimeError):
    """Configuration invalide ou contraire aux règles de collecte."""


def _env(name: str, default: str | None = None) -> str:
    value = os.environ.get(name, default)
    if value is None or value.strip() == "":
        raise ConfigError(f"Variable d'environnement obligatoire manquante : {name}")
    return value.strip()


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name, str(default)).strip()
    try:
        return int(raw)
    except ValueError as exc:
        raise ConfigError(f"{name} doit être un entier (reçu {raw!r})") from exc


def _env_float(name: str, default: float) -> float:
    raw = os.environ.get(name, str(default)).strip()
    try:
        return float(raw)
    except ValueError as exc:
        raise ConfigError(f"{name} doit être un nombre (reçu {raw!r})") from exc


def _env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name, "true" if default else "false").strip().lower()
    return raw in {"1", "true", "yes", "oui", "on"}


_WINDOW_RE = re.compile(r"^\s*(\d{1,2}):(\d{2})\s*-\s*(\d{1,2}):(\d{2})\s*$")


def parse_window(spec: str) -> tuple[time, time]:
    """'23:00-06:00' -> (time(23, 0), time(6, 0))."""
    m = _WINDOW_RE.match(spec)
    if not m:
        raise ConfigError(f"Fenêtre horaire invalide : {spec!r} (attendu HH:MM-HH:MM)")
    h1, m1, h2, m2 = (int(g) for g in m.groups())
    try:
        start, end = time(h1, m1), time(h2, m2)
    except ValueError as exc:
        raise ConfigError(f"Fenêtre horaire invalide : {spec!r}") from exc
    if start == end:
        raise ConfigError("La fenêtre horaire ne peut pas avoir un début égal à la fin")
    return start, end


def is_within_window(now: datetime, start: time, end: time) -> bool:
    """Vrai si l'heure locale de `now` est dans [start, end[. Gère le passage de minuit."""
    t = now.timetz().replace(tzinfo=None)
    if start < end:
        return start <= t < end
    return t >= start or t < end


@dataclass(frozen=True)
class Config:
    base_url: str
    search_path: str
    database_url: str
    user_agent: str
    download_delay: float
    window_start: time
    window_end: time
    window_spec: str
    tz: ZoneInfo
    cb_max_consecutive: int
    cb_slow_seconds: float
    download_timeout: int
    mode: str
    max_pages: int
    max_items: int
    force_max_pages: int
    force_max_items: int
    download_dce: bool
    storage_dir: Path
    fixtures_dir: Path
    log_level: str

    @property
    def is_test(self) -> bool:
        return self.mode == "test"

    def now(self) -> datetime:
        return datetime.now(self.tz)

    def in_window(self, now: datetime | None = None) -> bool:
        return is_within_window(now or self.now(), self.window_start, self.window_end)


def load_config() -> Config:
    base_url = _env("PMMP_BASE_URL", "https://www.marchespublics.gov.ma/")
    if not base_url.endswith("/"):
        base_url += "/"

    user_agent = _env("PMMP_USER_AGENT", "TACHFIR-VeilleMarchesPublics/1.0 (+contact: sales@tachfir.com)")
    if user_agent.lower().startswith("scrapy") or "TACHFIR" not in user_agent:
        raise ConfigError(
            "PMMP_USER_AGENT doit identifier TACHFIR et un contact "
            "(l'UA par défaut de Scrapy ou un UA de navigateur est interdit)."
        )

    delay = _env_float("PMMP_DOWNLOAD_DELAY", 3.0)
    if delay < MIN_DOWNLOAD_DELAY:
        raise ConfigError(f"PMMP_DOWNLOAD_DELAY={delay} est sous le minimum autorisé ({MIN_DOWNLOAD_DELAY}s)")

    cb_n = _env_int("PMMP_CB_MAX_CONSECUTIVE", 3)
    if not 1 <= cb_n <= MAX_CB_CONSECUTIVE:
        raise ConfigError(f"PMMP_CB_MAX_CONSECUTIVE doit être entre 1 et {MAX_CB_CONSECUTIVE}")

    mode = _env("PMMP_MODE", "prod").lower()
    if mode not in {"prod", "test"}:
        raise ConfigError("PMMP_MODE doit valoir 'prod' ou 'test'")

    window_spec = _env("PMMP_ALLOWED_WINDOW", "23:00-06:00")
    start, end = parse_window(window_spec)

    try:
        tz = ZoneInfo(_env("PMMP_TIMEZONE", "Africa/Casablanca"))
    except Exception as exc:  # ZoneInfoNotFoundError, ValueError
        raise ConfigError(f"Fuseau horaire inconnu : {exc}") from exc

    return Config(
        base_url=base_url,
        search_path=_env("PMMP_SEARCH_PATH", "index.php?page=entreprise.EntrepriseAdvancedSearch&AllCons"),
        database_url=os.environ.get("PMMP_DATABASE_URL", "").strip(),
        user_agent=user_agent,
        download_delay=delay,
        window_start=start,
        window_end=end,
        window_spec=window_spec,
        tz=tz,
        cb_max_consecutive=cb_n,
        cb_slow_seconds=_env_float("PMMP_CB_SLOW_SECONDS", 15.0),
        download_timeout=_env_int("PMMP_DOWNLOAD_TIMEOUT", 30),
        mode=mode,
        max_pages=max(0, _env_int("PMMP_MAX_PAGES", 0)),
        max_items=max(0, _env_int("PMMP_MAX_ITEMS", 0)),
        force_max_pages=max(1, _env_int("PMMP_FORCE_MAX_PAGES", 1)),
        force_max_items=max(1, _env_int("PMMP_FORCE_MAX_ITEMS", 10)),
        download_dce=_env_bool("PMMP_DOWNLOAD_DCE", True),
        storage_dir=Path(_env("PMMP_STORAGE_DIR", "storage")).resolve(),
        fixtures_dir=Path(_env("PMMP_FIXTURES_DIR", "fixtures")).resolve(),
        log_level=_env("PMMP_LOG_LEVEL", "INFO").upper(),
    )
