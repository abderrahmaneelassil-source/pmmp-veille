"""Tests d'intégration PostgreSQL : upsert, historique, clôture automatique.

Exécutés seulement si PMMP_TEST_DATABASE_URL pointe vers une base JETABLE
(les tables y sont vidées) :
    PMMP_TEST_DATABASE_URL=postgresql://postgres:...@localhost/pmmp_test pytest tests/test_db.py
(voir README §7 pour créer la base pmmp_test)
"""
import os
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import pytest
from parsel import Selector
from scrapy.http import HtmlResponse

from pmmp_collector.history import compute_changes, derive_statut
from pmmp_collector.models import TZ
from pmmp_collector.parsers import merge_listing_detail, parse_detail_page, parse_listing_page

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


# --- Cycle complet sur les pages RÉELLES de fixtures/live/ ------------------------

LIVE = Path(__file__).resolve().parents[1] / "fixtures" / "live"
LIVE_BASE = "https://www.marchespublics.gov.ma/index.php"


def page_text(path: Path) -> str:
    """Décodage identique à Scrapy (quelques octets non UTF-8 dans les commentaires du portail)."""
    return HtmlResponse(LIVE_BASE, body=path.read_bytes()).text


def live_items(edit=None):
    """Items construits comme par le spider : ligne de liste réelle + fiche détail réelle."""
    listing = parse_listing_page(Selector(text=page_text(LIVE / "liste/page0001.html")), LIVE_BASE)
    rows = {(r["org_acronyme"], r["ref_consultation"]): r for r in listing["rows"]}
    items = []
    for path in sorted((LIVE / "detail").glob("*.html")):
        org, _, ref = path.stem.partition("__")
        body = page_text(path)
        if edit:
            body = edit(ref, body)
        detail = parse_detail_page(Selector(text=body), LIVE_BASE)
        item = merge_listing_detail(rows[(org, ref)], detail)
        item.update(raw_html_detail=str(path), dce_paths=[], dce_statut="aucun_lien")
        items.append(item)
    return items


@pytest.fixture
def pipelines(conn, monkeypatch):
    from scrapy.utils.test import get_crawler

    from pmmp_collector import db
    from pmmp_collector.pipelines import PostgresPipeline, ValidationPipeline
    from pmmp_collector.spiders.pmmp import PmmpSpider

    monkeypatch.setenv("PMMP_DATABASE_URL", URL)
    crawler = get_crawler(PmmpSpider)
    validation, postgres = ValidationPipeline(crawler.stats), PostgresPipeline(crawler)
    postgres.open_spider()

    def run(items):
        crawler.spider = SimpleNamespace(run_id=db.start_run(conn, "test", True))
        for item in items:
            postgres.process_item(validation.process_item(item))
        return crawler.spider.run_id

    yield run
    postgres.close_spider()


def test_full_cycle_on_live_fixtures(conn, pipelines):
    # 1) Première insertion : 5 consultations réelles, aucun historique
    pipelines(live_items())
    rows = conn.execute("SELECT * FROM consultations ORDER BY ref_consultation").fetchall()
    assert len(rows) == 5 and conn.execute("SELECT count(*) n FROM historique_modifications").fetchone()["n"] == 0
    first = {r["ref_consultation"]: r for r in rows}
    assert all(r["statut"] == "en_cours" and r["resultat"] is None for r in rows)

    # Dates : '12/11/2026 10:00' du portail = 10:00 à Casablanca, restituée dans ce fuseau
    tz_row = conn.execute(
        "SELECT current_setting('TimeZone') tz, to_char(date_limite_depot, 'DD/MM/YYYY HH24:MI') affiche "
        "FROM consultations WHERE ref_consultation = '1038578'"
    ).fetchone()
    assert tz_row == {"tz": "Africa/Casablanca", "affiche": "12/11/2026 10:00"}
    assert first["1038578"]["date_limite_depot"] == datetime(2026, 11, 12, 10, 0, tzinfo=TZ)
    assert first["1038578"]["date_limite_depot"].utcoffset() == TZ.utcoffset(datetime(2026, 11, 12, 10, 0))

    # 2) Mêmes pages rejouées : pas de doublon, pas d'historique, premiere_vue_le conservée
    pipelines(live_items())
    assert conn.execute("SELECT count(*) n FROM consultations").fetchone()["n"] == 5
    assert conn.execute("SELECT count(*) n FROM historique_modifications").fetchone()["n"] == 0

    # 3) Mêmes pages, modifiées comme le ferait le portail
    def edit(ref, body):
        if ref == "1038578":  # report de la date limite
            return body.replace("12/11/2026 10:00", "26/11/2026 10:00")
        if ref == "1014491":  # rectificatif de l'objet
            return body.replace("Fourniture et installation", "Fourniture, livraison et installation", 1)
        if ref == "1041301":  # avis d'annulation
            return body.replace("<body", "<body><div><strong>Statut :</strong> Consultation annulée</div><x", 1)
        if ref == "1034700":  # résultat publié
            return body.replace("<body", "<body><div><strong>Attributaire :</strong> SOCIETE X SARL</div><x", 1)
        return body

    run_id = pipelines(live_items(edit))
    assert conn.execute("SELECT count(*) n FROM consultations").fetchone()["n"] == 5
    hist = conn.execute(
        "SELECT c.ref_consultation ref, h.champ, h.ancienne_valeur, h.nouvelle_valeur, h.type_evenement, h.run_id "
        "FROM historique_modifications h JOIN consultations c ON c.id = h.consultation_id ORDER BY 1, 2"
    ).fetchall()
    got = {(h["ref"], h["champ"]): (h["ancienne_valeur"], h["nouvelle_valeur"], h["type_evenement"]) for h in hist}
    assert all(h["run_id"] == run_id for h in hist)
    assert got == {
        ("1014491", "objet"): (first["1014491"]["objet"], first["1014491"]["objet"].replace(
            "Fourniture et installation", "Fourniture, livraison et installation"), "rectificatif"),
        ("1034700", "resultat"): (None, "SOCIETE X SARL", "resultat"),
        ("1038578", "date_limite_depot"): (
            datetime(2026, 11, 12, 10, tzinfo=TZ).isoformat(), datetime(2026, 11, 26, 10, tzinfo=TZ).isoformat(),
            "report_date"),
        ("1038578", "statut"): ("en_cours", "reporte", "report_date"),
        ("1041301", "statut"): ("en_cours", "annule", "annulation"),
    }
    statuts = {r["ref_consultation"]: r["statut"] for r in conn.execute("SELECT ref_consultation, statut FROM consultations")}
    assert statuts == {"1038578": "reporte", "1041301": "annule", "1014491": "en_cours",
                       "1034700": "en_cours", "1040952": "en_cours"}
    # Pas de donnée orpheline
    assert conn.execute(
        "SELECT count(*) n FROM historique_modifications h LEFT JOIN consultations c ON c.id = h.consultation_id "
        "WHERE c.id IS NULL").fetchone()["n"] == 0
