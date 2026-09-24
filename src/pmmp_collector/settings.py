"""Réglages Scrapy du collecteur PMMP.

Les règles de collecte ci-dessous sont des consignes du chef de projet. Elles
priment sur toute optimisation de vitesse et sont vérifiées par
tests/test_rules.py : ne pas les assouplir.
"""
from pmmp_collector.config import load_config

_cfg = load_config()

BOT_NAME = "pmmp_collector"
SPIDER_MODULES = ["pmmp_collector.spiders"]
NEWSPIDER_MODULE = "pmmp_collector.spiders"

# --- Identification ------------------------------------------------------------
# UA déclaré TACHFIR + contact, imposé sur chaque requête par DeclaredUserAgentMiddleware.
USER_AGENT = _cfg.user_agent
ROBOTSTXT_OBEY = True

# --- Règles de collecte (non négociables) -------------------------------------
# Une seule requête à la fois, sur tout le crawler comme sur le domaine.
CONCURRENT_REQUESTS = 1
CONCURRENT_REQUESTS_PER_DOMAIN = 1
# Pause entre deux requêtes. Pas de randomisation : sinon Scrapy descendrait à 0,5 x le délai.
DOWNLOAD_DELAY = _cfg.download_delay
DOWNLOAD_DELAY_JITTER = 0
# AutoThrottle ne descend jamais sous DOWNLOAD_DELAY, il ne peut que ralentir.
AUTOTHROTTLE_ENABLED = True
AUTOTHROTTLE_START_DELAY = _cfg.download_delay
AUTOTHROTTLE_MAX_DELAY = 60
AUTOTHROTTLE_TARGET_CONCURRENCY = 1.0
# Pas de nouvelle tentative automatique : en cas d'erreur, c'est le circuit breaker qui décide.
RETRY_ENABLED = False
DOWNLOAD_TIMEOUT = _cfg.download_timeout
# Session PRADO : les cookies du portail sont nécessaires pour rejouer les postbacks.
COOKIES_ENABLED = True

DEFAULT_REQUEST_HEADERS = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "fr,ar;q=0.8",
}

DOWNLOADER_MIDDLEWARES = {
    # Aucun proxy : le middleware proxy de Scrapy est désactivé.
    "scrapy.downloadermiddlewares.httpproxy.HttpProxyMiddleware": None,
    # Remplacé par notre middleware qui impose l'UA déclaré.
    "scrapy.downloadermiddlewares.useragent.UserAgentMiddleware": None,
    "pmmp_collector.middlewares.DeclaredUserAgentMiddleware": 400,
    "pmmp_collector.middlewares.TimeWindowMiddleware": 50,
    # Au plus près du téléchargeur pour voir les erreurs brutes (5xx, timeouts, latence).
    "pmmp_collector.middlewares.CircuitBreakerMiddleware": 990,
}

ITEM_PIPELINES = {
    "pmmp_collector.pipelines.ValidationPipeline": 100,
    "pmmp_collector.pipelines.PostgresPipeline": 300,
}

EXTENSIONS = {
    "scrapy.extensions.telnet.TelnetConsole": None,
    "pmmp_collector.extensions.RunRecorder": 500,
}

# DCE : archives volumineuses possibles.
DOWNLOAD_MAXSIZE = 300 * 1024 * 1024
DOWNLOAD_WARNSIZE = 50 * 1024 * 1024

FEED_EXPORT_ENCODING = "utf-8"
LOG_LEVEL = _cfg.log_level
