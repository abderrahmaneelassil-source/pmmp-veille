"""Connexion PostgreSQL de l'API : lecture seule, nombre de connexions limité.

L'API utilise le compte du collecteur, pmmp_app (PMMP_DATABASE_URL), qui a aussi
les droits INSERT et UPDATE. C'est un risque accepté le 25/09 (README §12) :
CHECKLIST.md recommandait un compte en lecture seule dédié. Le garde-fou retenu :
chaque session est ouverte avec default_transaction_read_only=on, donc toute
écriture échoue (ReadOnlySqlTransaction). Ce n'est pas une barrière de droits :
une requête « SET default_transaction_read_only = off » le lèverait. Aucune
requête de l'API ne le fait, et aucune ne construit de SQL avec une valeur reçue.
"""
from __future__ import annotations

import os
import threading
from collections.abc import Iterator
from contextlib import contextmanager

import psycopg
from dotenv import find_dotenv, load_dotenv
from psycopg.rows import dict_row

# Même .env que le collecteur ; n'écrase jamais une variable déjà définie.
load_dotenv(find_dotenv(usecwd=True), override=False)

CONNECT_TIMEOUT = 5          # s : base arrêtée → réponse 503 rapide, pas d'attente infinie
STATEMENT_TIMEOUT_MS = 5000  # une requête trop longue est coupée au lieu de charger la base
# pmmp_app est limité à 10 connexions (db/roles.sql), partagées avec le collecteur :
# l'API n'en ouvre jamais plus de 3 à la fois, pour ne pas bloquer un run.
MAX_CONNECTIONS = 3
WAIT_SECONDS = 5             # attente maximale d'une connexion libre

_slots = threading.BoundedSemaphore(MAX_CONNECTIONS)


class DatabaseUnavailable(RuntimeError):
    """Base injoignable, non configurée ou saturée : l'API répond 503."""


def connect() -> psycopg.Connection:
    """Ouvre une session en lecture seule sur PMMP_DATABASE_URL (lu à chaque appel)."""
    url = os.environ.get("PMMP_DATABASE_URL", "").strip()
    if not url:
        raise DatabaseUnavailable("PMMP_DATABASE_URL non défini")
    timezone = os.environ.get("PMMP_TIMEZONE", "").strip() or "Africa/Casablanca"
    return psycopg.connect(
        url,
        autocommit=True,
        row_factory=dict_row,
        client_encoding="UTF8",
        application_name="pmmp_api",  # repérable dans pg_stat_activity
        connect_timeout=CONNECT_TIMEOUT,
        options=(
            "-c default_transaction_read_only=on"
            f" -c statement_timeout={STATEMENT_TIMEOUT_MS}"
            f" -c timezone={timezone}"
        ),
    )


@contextmanager
def connection() -> Iterator[psycopg.Connection]:
    """Connexion le temps d'une requête HTTP, dans la limite de MAX_CONNECTIONS."""
    if not _slots.acquire(timeout=WAIT_SECONDS):
        raise DatabaseUnavailable(f"plus de {MAX_CONNECTIONS} requêtes simultanées")
    try:
        with connect() as conn:  # fermée en sortie, même en cas d'erreur
            yield conn
    finally:
        _slots.release()


def get_conn() -> Iterator[psycopg.Connection]:
    """Dépendance FastAPI."""
    with connection() as conn:
        yield conn
