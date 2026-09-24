"""Tests d'intégration PostgreSQL : upsert, historique, clôture automatique.

Exécutés seulement si PMMP_TEST_DATABASE_URL pointe vers une base JETABLE
(les tables y sont vidées) :
    PMMP_TEST_DATABASE_URL=postgresql://pmmp:...@localhost/pmmp_test pytest tests/test_db.py
"""
import os
from datetime import datetime, timedelta

import pytest

from pmmp_collector.history import compute_changes, derive_statut
from pmmp_collector.models import TZ

URL = os.environ.get("PMMP_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not URL, reason="PMMP_TEST_DATABASE_URL non défini")


@pytest.fixture
def conn():
    from pmmp_collector import db

    c = db.connect(URL)
    db.init_schema(c)
    c.execute("TRUNCATE historique_modifications, consultations, collecte_runs RESTART IDENTITY CASCADE")
    yield c
    c.close()


def record(**kw):
    base = {
        "org_acronyme": "x7k", "ref_consultation": "987654", "reference": "12/2026/AOO",
        "objet": "Travaux — تهيئة", "acheteur": "COMMUNE DE TIZNIT",
        "date_limite_depot": datetime(2030, 10, 20, 10, tzinfo=TZ),
        "url_detail": "https://www.marchespublics.gov.ma/pmmp/index.php?x", "dce_urls": [], "dce_paths": [],
    }
    return {**base, **kw}


def save(conn, rec):
    from pmmp_collector import db

    with conn.transaction():
        old = db.fetch_for_update(conn, rec["org_acronyme"], rec["ref_consultation"])
        rec["statut"] = derive_statut(rec, old, datetime.now(TZ))
        cid = db.upsert_consultation(conn, rec)
        db.insert_history(conn, cid, compute_changes(old, rec), None)
    return cid


def test_upsert_no_duplicates_and_history(conn):
    cid = save(conn, record(reservation_pme=True))
    assert save(conn, record()) == cid  # même clé, pas de doublon ; PME conservée (COALESCE)
    save(conn, record(date_limite_depot=datetime(2030, 10, 30, 10, tzinfo=TZ)))

    row = conn.execute("SELECT * FROM consultations").fetchone()
    assert conn.execute("SELECT count(*) AS n FROM consultations").fetchone()["n"] == 1
    assert row["statut"] == "reporte" and row["reservation_pme"] is True and "تهيئة" in row["objet"]
    events = {r["champ"]: r["type_evenement"] for r in conn.execute("SELECT * FROM historique_modifications")}
    assert events == {"date_limite_depot": "report_date", "statut": "report_date"}


def test_close_expired(conn):
    from pmmp_collector import db

    save(conn, record())
    conn.execute("UPDATE consultations SET date_limite_depot = now() - interval '1 day'")
    assert db.close_expired(conn, None) == 1
    assert conn.execute("SELECT statut FROM consultations").fetchone()["statut"] == "cloture"
