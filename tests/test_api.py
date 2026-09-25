"""Tests de l'API de consultation (api/, README §12).

Les deux premiers tests tournent toujours, sans base. Les autres ont besoin de
PMMP_TEST_DATABASE_URL (base JETABLE pmmp_test, tables vidées, voir README §7) :
ils y insèrent un petit jeu de données connu, puis interrogent l'API dessus.
"""
import os
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

from api.main import app

TZ = ZoneInfo("Africa/Casablanca")
URL = os.environ.get("PMMP_TEST_DATABASE_URL")
avec_base = pytest.mark.skipif(not URL, reason="PMMP_TEST_DATABASE_URL non défini")


def test_aucune_route_d_ecriture():
    routes = {r.path: r.methods for r in app.routes if isinstance(r, APIRoute)}
    assert set(routes) == {
        "/",  # redirection vers /docs
        "/health",
        "/consultations",
        "/consultations/{org_acronyme}/{ref_consultation}",
        "/consultations/{org_acronyme}/{ref_consultation}/historique",
        "/collecte/dernier-run",
    }
    assert all(methods == {"GET"} for methods in routes.values())


def test_racine_redirige_vers_docs():
    r = TestClient(app).get("/", follow_redirects=False)
    assert r.status_code == 307 and r.headers["location"] == "/docs"


def test_base_injoignable_503(monkeypatch):
    # Port 1 : rien n'y écoute, la connexion est refusée immédiatement.
    monkeypatch.setenv("PMMP_DATABASE_URL", "postgresql://pmmp_app:x@127.0.0.1:1/pmmp_veille")
    client = TestClient(app)
    r = client.get("/health")
    assert r.status_code == 503 and r.json() == {"api": "ok", "base": "indisponible"}
    r = client.get("/consultations")
    assert r.status_code == 503 and r.json() == {"detail": "Base de données indisponible"}
    assert "pmmp_app" not in r.text and "127.0.0.1" not in r.text  # rien sur la connexion


# --- Avec la base de test --------------------------------------------------------

def _consultation(org, ref, **kw):
    return {
        "org_acronyme": org, "ref_consultation": ref, "reference": f"{ref}/2026/AOO",
        "objet": "Travaux — تهيئة", "acheteur": "COMMUNE DE TIZNIT", "categorie": "Travaux",
        "date_limite_depot": datetime(2030, 10, 20, 10, tzinfo=TZ), "statut": "en_cours",
        "url_detail": f"https://www.marchespublics.gov.ma/pmmp/?ref={ref}", **kw,
    }


CONSULTATIONS = [
    _consultation("x7k", "111", categorie="Travaux / Construction d'ouvrages"),
    _consultation("abc", "222", categorie="Fournitures", acheteur="OFFICE NATIONAL DE L'EAU",
                  date_limite_depot=datetime(2020, 1, 10, 10, tzinfo=TZ), statut="cloture"),
    _consultation("x7k", "333", categorie="Services", statut="reporte",
                  date_limite_depot=datetime(2030, 12, 1, 10, tzinfo=TZ)),
]


@pytest.fixture
def base():
    """Base de test vidée puis remplie avec CONSULTATIONS, un historique et deux runs."""
    from pmmp_collector import db as collector_db

    conn = collector_db.connect(URL)
    collector_db.init_schema(conn)
    conn.execute("TRUNCATE historique_modifications, consultations, collecte_runs RESTART IDENTITY CASCADE")
    ids = {c["ref_consultation"]: collector_db.upsert_consultation(conn, c) for c in CONSULTATIONS}
    # Heures sans décalage : heure du Maroc (session en Africa/Casablanca), dont le
    # décalage UTC varie selon la date. Ne pas écrire « +01 » en dur.
    conn.execute(
        "INSERT INTO collecte_runs (demarre_le, termine_le, statut, mode, nb_pages, nb_consultations)"
        " VALUES ('2026-09-24 06:00', '2026-09-24 06:45', 'succes', 'prod', 3, 3)"
    )
    conn.execute(
        "INSERT INTO collecte_runs (demarre_le, termine_le, statut, raison, mode, nb_pages, stats)"
        " VALUES ('2026-09-25 06:00', '2026-09-25 06:02', 'echec', 'circuit_breaker', 'prod', 1,"
        " '{\"pmmp/pages\": 1, \"pmmp/detail_errors\": 3, \"pmmp/dce_errors\": 1}')"
    )
    conn.execute(
        "INSERT INTO historique_modifications"
        " (consultation_id, champ, ancienne_valeur, nouvelle_valeur, type_evenement, detecte_le, run_id)"
        " VALUES (%(id)s, 'date_limite_depot', '2030-10-10', '2030-10-20', 'report_date', '2026-09-24 06:30', 1),"
        "        (%(id)s, 'objet', 'Travaux', 'Travaux — تهيئة', 'rectificatif', '2026-09-24 06:31', 1)",
        {"id": ids["111"]},
    )
    yield conn
    conn.close()


@pytest.fixture
def client(base, monkeypatch):
    monkeypatch.setenv("PMMP_DATABASE_URL", URL)
    return TestClient(app)


def _refs(r):
    return [c["ref_consultation"] for c in r.json()["resultats"]]


@avec_base
def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"api": "ok", "base": "ok", "base_de_donnees": "pmmp_test", "lecture_seule": True}


@avec_base
def test_liste_triee_par_date_limite(client):
    r = client.get("/consultations")
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 3 and body["limit"] == 50 and body["offset"] == 0
    assert _refs(r) == ["222", "111", "333"]
    premiere = body["resultats"][1]
    assert premiere["objet"] == "Travaux — تهيئة"  # arabe intact
    assert datetime.fromisoformat(premiere["date_limite_depot"]) == datetime(2030, 10, 20, 10, tzinfo=TZ)


@avec_base
def test_filtre_statut(client):
    assert _refs(client.get("/consultations", params={"statut": "en_cours"})) == ["111"]
    assert client.get("/consultations", params={"statut": "inconnu"}).status_code == 422


@avec_base
def test_autres_filtres_et_pagination(client):
    def refs(**params):
        return _refs(client.get("/consultations", params=params))

    assert refs(categorie="travaux") == ["111"]            # « contient », casse ignorée
    assert refs(acheteur="tiznit") == ["111", "333"]
    assert refs(acheteur="%") == []                        # joker pris littéralement
    assert refs(date_limite_apres="2030-01-01", date_limite_avant="2030-11-01") == ["111"]
    assert refs(date_limite_avant="2030-10-20T10:00") == ["222"]  # borne exclue, heure du Maroc

    r = client.get("/consultations", params={"limit": 1, "offset": 1})
    assert r.json()["total"] == 3 and _refs(r) == ["111"]
    assert client.get("/consultations", params={"limit": 0}).status_code == 422


@avec_base
def test_detail(client):
    r = client.get("/consultations/x7k/111")
    assert r.status_code == 200
    body = r.json()
    assert body["categorie"] == "Travaux / Construction d'ouvrages" and body["dce_urls"] == []
    assert {"premiere_vue_le", "mis_a_jour_le", "resultat"} <= set(body)


@avec_base
def test_reference_inexistante_404(client):
    for path in ("/consultations/x7k/999", "/consultations/x7k/999/historique"):
        r = client.get(path)
        assert r.status_code == 404
        assert r.json() == {"detail": "Consultation introuvable : x7k/999"}


@avec_base
def test_historique(client):
    r = client.get("/consultations/x7k/111/historique")
    assert r.status_code == 200
    assert [(m["champ"], m["type_evenement"], m["run_id"]) for m in r.json()] == [
        ("date_limite_depot", "report_date", 1), ("objet", "rectificatif", 1),
    ]
    assert client.get("/consultations/x7k/333/historique").json() == []  # connue, jamais modifiée


@avec_base
def test_dernier_run(client):
    body = client.get("/collecte/dernier-run").json()
    run = body["dernier_run"]
    assert run["id"] == 2 and run["statut"] == "echec" and run["raison"] == "circuit_breaker"
    assert run["duree_secondes"] == 120
    assert run["erreurs"] == {"detail_errors": 3, "dce_errors": 1}
    # Le dernier run a échoué : la date du dernier succès reste visible.
    assert datetime.fromisoformat(body["dernier_succes_le"]) == datetime(2026, 9, 24, 6, 45, tzinfo=TZ)


@avec_base
def test_dernier_run_base_vide(client, base):
    # Situation de pmmp_veille avant le premier run réel.
    base.execute("TRUNCATE collecte_runs CASCADE")
    r = client.get("/collecte/dernier-run")
    assert r.status_code == 200 and r.json() == {"dernier_run": None, "dernier_succes_le": None}


@avec_base
def test_session_api_refuse_les_ecritures(base, monkeypatch):
    import psycopg

    from api import db

    monkeypatch.setenv("PMMP_DATABASE_URL", URL)
    with db.connection() as conn:
        with pytest.raises(psycopg.errors.ReadOnlySqlTransaction):
            conn.execute("UPDATE consultations SET objet = 'modifié'")
    assert base.execute("SELECT count(*) AS n FROM consultations WHERE objet = 'modifié'").fetchone()["n"] == 0
