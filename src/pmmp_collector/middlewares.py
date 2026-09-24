"""Middlewares de téléchargement qui appliquent les règles de collecte.

- DeclaredUserAgentMiddleware : impose l'UA TACHFIR déclaré sur chaque requête.
- TimeWindowMiddleware        : refuse toute requête hors de la fenêtre horaire
                                autorisée (sauf run lancé avec --force).
- CircuitBreakerMiddleware    : arrête le run après N erreurs/lenteurs consécutives,
                                ou immédiatement si le site refuse/limite (403/429).
"""
from __future__ import annotations

import logging

from scrapy import signals
from scrapy.exceptions import IgnoreRequest
from scrapy.utils.defer import deferred_from_coro

from pmmp_collector.config import ConfigError, load_config

logger = logging.getLogger(__name__)

REASON_CIRCUIT_BREAKER = "circuit_breaker"
REASON_REFUSED_WINDOW = "refus_hors_fenetre"
REASON_WINDOW_ENDED = "fin_fenetre_horaire"

# Statuts qui signifient que le site nous demande d'arrêter : arrêt immédiat.
STOP_NOW_STATUSES = {403, 429}


def close_spider(crawler, reason: str) -> None:
    deferred_from_coro(crawler.engine.close_spider_async(reason=reason))


class DeclaredUserAgentMiddleware:
    def __init__(self, user_agent: str):
        if not user_agent or user_agent.lower().startswith("scrapy") or "TACHFIR" not in user_agent:
            raise ConfigError("User-Agent non conforme : il doit identifier TACHFIR et un contact")
        self.user_agent = user_agent

    @classmethod
    def from_crawler(cls, crawler):
        return cls(crawler.settings.get("USER_AGENT"))

    def process_request(self, request, spider=None):
        request.headers["User-Agent"] = self.user_agent
        return None


class TimeWindowMiddleware:
    """Vérifie la fenêtre horaire avant chaque requête.

    Première requête hors fenêtre -> le run est refusé.
    Fenêtre dépassée en cours de run -> arrêt propre (run partiel).
    """

    def __init__(self, crawler, cfg):
        self.crawler = crawler
        self.cfg = cfg
        self.requests_seen = 0
        self.closing = False

    @classmethod
    def from_crawler(cls, crawler):
        return cls(crawler, load_config())

    def process_request(self, request, spider=None):
        spider = spider or self.crawler.spider
        if getattr(spider, "force", False):
            self.requests_seen += 1
            return None
        if self.closing:
            raise IgnoreRequest("run en cours d'arrêt (fenêtre horaire)")
        if not self.cfg.in_window():
            self.closing = True
            reason = REASON_REFUSED_WINDOW if self.requests_seen == 0 else REASON_WINDOW_ENDED
            logger.error(
                "Hors de la fenêtre horaire autorisée (%s, %s) : arrêt du run (%s). "
                "Utiliser --force uniquement pour un test manuel limité.",
                self.cfg.window_spec, self.cfg.tz.key, reason,
            )
            close_spider(self.crawler, reason)
            raise IgnoreRequest(reason)
        self.requests_seen += 1
        return None


class CircuitBreakerMiddleware:
    def __init__(self, crawler, max_consecutive: int, slow_seconds: float):
        self.crawler = crawler
        self.max_consecutive = max_consecutive
        self.slow_seconds = slow_seconds
        self.consecutive = 0
        self.tripped = False
        self.last_problems: list[str] = []

    @classmethod
    def from_crawler(cls, crawler):
        cfg = load_config()
        mw = cls(crawler, cfg.cb_max_consecutive, cfg.cb_slow_seconds)
        crawler.signals.connect(mw.spider_opened, signal=signals.spider_opened)
        return mw

    def spider_opened(self):
        logger.info(
            "Circuit breaker actif : arrêt après %d erreurs/lenteurs consécutives (lent > %.0fs), "
            "arrêt immédiat sur HTTP %s",
            self.max_consecutive, self.slow_seconds, sorted(STOP_NOW_STATUSES),
        )

    def process_request(self, request, spider=None):
        if self.tripped:
            raise IgnoreRequest("circuit breaker déclenché")
        return None

    def process_response(self, request, response, spider=None):
        if self.tripped:
            raise IgnoreRequest("circuit breaker déclenché")
        latency = request.meta.get("download_latency")
        if response.status in STOP_NOW_STATUSES:
            self._trip(f"HTTP {response.status} sur {request.url} : le site refuse ou limite nos requêtes")
            raise IgnoreRequest(f"HTTP {response.status}")
        if response.status >= 500:
            self._failure(f"HTTP {response.status} sur {request.url}")
        elif (
            latency is not None
            and latency > self.slow_seconds
            and not request.meta.get("dce_download")  # un gros DCE est lent par nature
        ):
            self._failure(f"réponse lente ({latency:.1f}s > {self.slow_seconds:.0f}s) sur {request.url}")
        else:
            self.consecutive = 0
            self.last_problems.clear()
        return response

    def process_exception(self, request, exception, spider=None):
        if isinstance(exception, IgnoreRequest):
            return None
        self._failure(f"{type(exception).__name__} sur {request.url} : {exception}")
        return None

    def _failure(self, problem: str) -> None:
        self.consecutive += 1
        self.last_problems.append(problem)
        self.crawler.stats.inc_value("pmmp/circuit_breaker/failures")
        logger.warning("Problème %d/%d : %s", self.consecutive, self.max_consecutive, problem)
        if self.consecutive >= self.max_consecutive:
            self._trip(f"{self.consecutive} problèmes consécutifs : " + " | ".join(self.last_problems))

    def _trip(self, reason: str) -> None:
        if self.tripped:
            return
        self.tripped = True
        self.crawler.stats.set_value("pmmp/circuit_breaker/reason", reason)
        logger.critical("CIRCUIT BREAKER DÉCLENCHÉ — arrêt immédiat du run, aucune nouvelle tentative. Raison : %s", reason)
        close_spider(self.crawler, REASON_CIRCUIT_BREAKER)
