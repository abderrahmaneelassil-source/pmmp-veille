"""Accès PostgreSQL (psycopg 3). Requêtes paramétrées uniquement."""
from __future__ import annotations

import json
import logging
from pathlib import Path

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from pmmp_collector.history import Change

logger = logging.getLogger(__name__)

SCHEMA_PATH = Path(__file__).resolve().parents[2] / "db" / "schema.sql"
CONNECT_TIMEOUT = 10  # secondes

COLUMNS = [
    "org_acronyme", "ref_consultation", "reference", "objet", "acheteur", "categorie",
    "type_procedure", "lieu_execution", "date_publication", "date_limite_depot",
    "reservation_pme", "reponse_electronique", "statut", "resultat", "url_detail",
    "dce_urls", "dce_paths", "dce_statut", "raw_html_detail_path",
]

# Sur conflit : une valeur absente (NULL / liste vide) ne remplace jamais une valeur connue.
_ALWAYS_REPLACE = {"objet", "acheteur", "date_limite_depot", "statut", "url_detail"}
_ARRAYS = {"dce_urls", "dce_paths"}


def _update_clause(col: str) -> str:
    if col in _ALWAYS_REPLACE:
        return f"{col} = EXCLUDED.{col}"
    if col in _ARRAYS:
        return f"{col} = CASE WHEN cardinality(EXCLUDED.{col}) > 0 THEN EXCLUDED.{col} ELSE consultations.{col} END"
    return f"{col} = COALESCE(EXCLUDED.{col}, consultations.{col})"


UPSERT_SQL = f"""
INSERT INTO consultations ({", ".join(COLUMNS)})
VALUES ({", ".join(f"%({c})s" for c in COLUMNS)})
ON CONFLICT (org_acronyme, ref_consultation) DO UPDATE SET
    {", ".join(_update_clause(c) for c in COLUMNS if c not in ("org_acronyme", "ref_consultation"))},
    derniere_vue_le = now(),
    mis_a_jour_le = now()
RETURNING id
"""


def connect(url: str, timezone: str = "Africa/Casablanca") -> psycopg.Connection:
    """`timezone` : fuseau de la session (PMMP_TIMEZONE), utilisé pour afficher les timestamptz."""
    conn = psycopg.connect(
        url,
        autocommit=True,
        row_factory=dict_row,
        client_encoding="UTF8",
        options=f"-c timezone={timezone}",
        # Sans délai maximal, une base arrêtée bloque le collecteur indéfiniment.
        connect_timeout=CONNECT_TIMEOUT,
    )
    return conn


def init_schema(conn: psycopg.Connection, path: Path = SCHEMA_PATH) -> None:
    conn.execute(path.read_text(encoding="utf-8"))


def fetch_for_update(conn, org: str, ref: str) -> dict | None:
    return conn.execute(
        "SELECT * FROM consultations WHERE org_acronyme = %s AND ref_consultation = %s FOR UPDATE",
        (org, ref),
    ).fetchone()


def upsert_consultation(conn, record: dict) -> int:
    params = {c: record.get(c) for c in COLUMNS}
    for c in _ARRAYS:
        params[c] = params[c] or []
    return conn.execute(UPSERT_SQL, params).fetchone()["id"]


def insert_history(conn, consultation_id: int, changes: list[Change], run_id: int | None) -> None:
    if not changes:
        return
    with conn.cursor() as cur:
        cur.executemany(
            "INSERT INTO historique_modifications "
            "(consultation_id, champ, ancienne_valeur, nouvelle_valeur, type_evenement, run_id) "
            "VALUES (%s, %s, %s, %s, %s, %s)",
            [(consultation_id, c.champ, c.ancienne_valeur, c.nouvelle_valeur, c.type_evenement, run_id) for c in changes],
        )


def fetch_known(conn, keys: list[tuple[str, str]]) -> dict[tuple[str, str], dict]:
    """État en base des consultations d'une page de liste (collecte incrémentale)."""
    if not keys:
        return {}
    orgs, refs = [k[0] for k in keys], [k[1] for k in keys]
    rows = conn.execute(
        """
        SELECT c.org_acronyme, c.ref_consultation, c.date_limite_depot, c.statut, c.dce_statut
        FROM consultations c
        JOIN unnest(%s::text[], %s::text[]) AS k(org, ref)
          ON c.org_acronyme = k.org AND c.ref_consultation = k.ref
        """,
        (orgs, refs),
    ).fetchall()
    return {(r["org_acronyme"], r["ref_consultation"]): r for r in rows}


def touch_seen(conn, keys: list[tuple[str, str]]) -> None:
    """Consultations toujours présentes dans la liste mais inchangées : seule derniere_vue_le bouge."""
    if not keys:
        return
    conn.execute(
        """
        UPDATE consultations c SET derniere_vue_le = now()
        FROM unnest(%s::text[], %s::text[]) AS k(org, ref)
        WHERE c.org_acronyme = k.org AND c.ref_consultation = k.ref
        """,
        ([k[0] for k in keys], [k[1] for k in keys]),
    )


def close_expired(conn, run_id: int | None) -> int:
    """Passe en 'cloture' les consultations dont la date limite est dépassée (sans requête au site)."""
    with conn.transaction():
        rows = conn.execute(
            """
            WITH cibles AS (
                SELECT id, statut FROM consultations
                WHERE statut IN ('en_cours', 'reporte') AND date_limite_depot < now()
                FOR UPDATE
            ), maj AS (
                UPDATE consultations c SET statut = 'cloture', mis_a_jour_le = now()
                FROM cibles WHERE c.id = cibles.id
                RETURNING c.id
            )
            INSERT INTO historique_modifications
                (consultation_id, champ, ancienne_valeur, nouvelle_valeur, type_evenement, run_id)
            SELECT cibles.id, 'statut', cibles.statut, 'cloture', 'autre', %s
            FROM cibles JOIN maj ON maj.id = cibles.id
            RETURNING id
            """,
            (run_id,),
        ).fetchall()
    return len(rows)


def start_run(conn, mode: str, force: bool) -> int:
    return conn.execute(
        "INSERT INTO collecte_runs (mode, force) VALUES (%s, %s) RETURNING id", (mode, force)
    ).fetchone()["id"]


def finish_run(conn, run_id: int, statut: str, raison: str, stats: dict) -> None:
    conn.execute(
        """
        UPDATE collecte_runs
        SET termine_le = now(), statut = %s, raison = %s,
            nb_pages = %s, nb_consultations = %s, nb_ecartees = %s, stats = %s
        WHERE id = %s
        """,
        (
            statut, raison,
            stats.get("pmmp/pages", 0), stats.get("pmmp/db_upserts", 0), stats.get("pmmp/items_invalid", 0),
            Jsonb(json.loads(json.dumps(stats, default=str))), run_id,
        ),
    )


def last_success(conn) -> dict | None:
    return conn.execute(
        "SELECT id, demarre_le, termine_le, nb_consultations FROM collecte_runs "
        "WHERE statut = 'succes' ORDER BY termine_le DESC LIMIT 1"
    ).fetchone()
