"""Crawl Scrapy RÉEL (python -m pmmp_collector crawl) contre un faux portail local.

Aucune requête vers marchespublics.gov.ma : le serveur écoute sur 127.0.0.1 et
enregistre chaque requête reçue. On vérifie ainsi, sur ce qui passe vraiment
sur le réseau, les règles de collecte : circuit breaker, User-Agent déclaré,
une requête à la fois, pause entre deux requêtes, refus hors fenêtre horaire.
"""
import json
import os
import subprocess
import sys
import threading
import time
from datetime import datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs
from zoneinfo import ZoneInfo

import pytest

ROOT = Path(__file__).resolve().parents[1]
UA = "TACHFIR-VeilleMarchesPublics/1.0 (+contact: sales@tachfir.com)"
DELAY = 1.0
DETAIL = (ROOT / "fixtures/synthetic/detail_987654.html").read_text(encoding="utf-8")
N_ROWS = 6

ROW = """<tr>
  <td class="col-90"><div class="line-info-bulle">Appel d'offres ouvert</div><div>Travaux</div>
    <div class="date date-min">15/09/2026</div></td>
  <td class="col-450"><div class="objet-line"><span class="ref">{ref}/2026/AOO</span>
    <div id="x_panelBlocObjet"><strong>Objet :</strong> Travaux n°{ref} — تهيئة</div>
    <div id="x_panelBlocDenomination"><strong>Acheteur public :</strong> COMMUNE DE TEST</div></div></td>
  <td class="col-90 cons_dateEnd"><div class="cloture-line"><span>{deadline}</span></div></td>
  <td class="actions"><a href="index.php?page=entreprise.EntrepriseDetailsConsultation&amp;refConsultation={ref}&amp;orgAcronyme=t1">Détail</a></td>
</tr>"""

DEADLINE = "20/10/2026 10:00"  # même date limite que la fiche détail, comme sur le vrai portail
SIZE_SELECT = "ctl0$CONTENU_PAGE$resultSearch$listePageSizeTop"


def listing(page_size: int, deadlines: dict) -> bytes:
    """Page de liste ; la liste déroulante de taille de page reflète le dernier choix posté."""
    selected = ' selected="selected"'  # hors de l'f-string : antislash interdit avant Python 3.12
    options = "".join(
        f'<option value="{n}"{selected if n == page_size else ""}>{n}</option>'
        for n in (10, 20, 50, 100, 500)
    )
    rows = "".join(ROW.format(ref=1000 + i, deadline=deadlines.get(1000 + i, DEADLINE)) for i in range(N_ROWS))
    return f"""<!DOCTYPE html><html><head><meta charset="utf-8"></head><body>
<form method="post" action="liste.html">
<input type="hidden" name="PRADO_PAGESTATE" value="STATE1" />
<select name="{SIZE_SELECT}">{options}</select>
<input type="text" name="ctl0$CONTENU_PAGE$resultSearch$numPageTop" value="1" />
/ <span id="ctl0_CONTENU_PAGE_resultSearch_nombrePageTop">1</span>
<table>{rows}</table>
</form></body></html>""".encode("utf-8")


class FakePortal(BaseHTTPRequestHandler):
    detail_status = 200  # 503 -> panne simulée sur les fiches détail
    detail_body = None  # None -> fixtures/synthetic/detail_987654.html
    deadlines: dict = {}  # ref -> date limite affichée dans la liste (défaut DEADLINE)
    log: list = []
    inflight = 0
    max_inflight = 0
    lock = threading.Lock()

    def _serve(self):
        cls = type(self)
        with cls.lock:
            cls.inflight += 1
            cls.max_inflight = max(cls.max_inflight, cls.inflight)
            body = self.rfile.read(int(self.headers.get("Content-Length") or 0)).decode()
            form = {k: v[0] for k, v in parse_qs(body).items()}
            cls.log.append({"t": time.monotonic(), "path": self.path, "ua": self.headers.get("User-Agent"),
                            "form": form})
        try:
            time.sleep(0.1)  # rend visible un éventuel chevauchement de requêtes
            if self.path == "/robots.txt":
                self._reply(404, b"")
            elif self.path.startswith("/liste.html"):
                self._reply(200, listing(int(form.get(SIZE_SELECT, 10)), cls.deadlines))
            elif "EntrepriseDetailsConsultation" in self.path:
                if cls.detail_status != 200:
                    self._reply(cls.detail_status, b"<html>Service indisponible</html>")
                else:
                    self._reply(200, cls.detail_body or DETAIL.encode("utf-8"))
            elif "Dce" in self.path:
                self._reply(200, b"PK\x03\x04fake", "application/zip", 'attachment; filename="DCE.zip"')
            else:
                self._reply(404, b"")
        finally:
            with cls.lock:
                cls.inflight -= 1

    def _reply(self, status, body, ctype="text/html; charset=utf-8", disposition=None):
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        if disposition:
            self.send_header("Content-Disposition", disposition)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    do_GET = do_POST = _serve

    def log_message(self, *args):
        pass


@pytest.fixture
def portal():
    FakePortal.log, FakePortal.inflight, FakePortal.max_inflight = [], 0, 0
    FakePortal.detail_status, FakePortal.detail_body, FakePortal.deadlines = 200, None, {}
    server = ThreadingHTTPServer(("127.0.0.1", 0), FakePortal)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield server
    server.shutdown()
    server.server_close()


def closed_window() -> str:
    """Fenêtre horaire qui exclut l'heure actuelle : le test ne dépend pas de l'heure."""
    now = datetime.now(ZoneInfo("Africa/Casablanca"))
    start, end = now + timedelta(hours=2), now + timedelta(hours=3)
    return f"{start:%H:%M}-{end:%H:%M}"


def open_window() -> str:
    """Fenêtre horaire qui contient l'heure actuelle (run accepté sans --force)."""
    now = datetime.now(ZoneInfo("Africa/Casablanca"))
    start, end = now - timedelta(minutes=30), now + timedelta(hours=1)
    return f"{start:%H:%M}-{end:%H:%M}"


def crawl_env(portal, tmp_path, database_url="", window=None):
    return {
        **os.environ,
        "PMMP_BASE_URL": f"http://127.0.0.1:{portal.server_port}/",
        "PMMP_SEARCH_PATH": "liste.html",
        "PMMP_DATABASE_URL": database_url,
        "PMMP_MODE": os.environ.get("PMMP_MODE", "test"),
        "PMMP_USER_AGENT": UA,
        "PMMP_DOWNLOAD_DELAY": str(DELAY),
        "PMMP_ALLOWED_WINDOW": window or closed_window(),
        "PMMP_CB_MAX_CONSECUTIVE": "3",
        "PMMP_FORCE_MAX_ITEMS": "10",
        "PMMP_STORAGE_DIR": str(tmp_path / "storage"),
        "PMMP_FIXTURES_DIR": str(tmp_path / "fixtures"),
        "PYTHONPATH": str(ROOT / "src"),
        "PYTHONIOENCODING": "utf-8",
    }


def run_crawl(portal, tmp_path, *args, database_url="", window=None):
    proc = subprocess.run(
        [sys.executable, "-m", "pmmp_collector", "crawl", *args],
        cwd=tmp_path, env=crawl_env(portal, tmp_path, database_url, window),
        capture_output=True, text=True, encoding="utf-8", timeout=120,
    )
    last_run = tmp_path / "storage" / "last_run.json"
    summary = json.loads(last_run.read_text(encoding="utf-8")) if last_run.exists() else None
    return proc, summary


def test_refuses_outside_window_without_any_request(portal, tmp_path):
    proc, _ = run_crawl(portal, tmp_path)
    assert proc.returncode == 2, proc.stderr
    assert "REFUS" in proc.stderr
    assert FakePortal.log == []


@pytest.mark.parametrize("mode,url,message", [
    ("prod", "", "PMMP_DATABASE_URL est obligatoire"),
    ("test", "postgresql://pmmp:x@127.0.0.1:1/pmmp_veille", "connexion PostgreSQL impossible"),
])
def test_unusable_database_fails_fast_with_clear_message(portal, tmp_path, monkeypatch, mode, url, message):
    monkeypatch.setenv("PMMP_MODE", mode)
    proc, summary = run_crawl(portal, tmp_path, "--force", database_url=url)
    assert proc.returncode == 1
    assert message in proc.stderr
    assert "Traceback" not in proc.stderr
    assert FakePortal.log == [] and summary is None


def test_accepted_inside_window_without_force(portal, tmp_path):
    proc, summary = run_crawl(portal, tmp_path, window=open_window())
    assert proc.returncode == 0, proc.stderr[-3000:]
    assert summary["statut"] == "succes" and summary["force"] is False
    assert "Run forcé" not in proc.stderr  # pas de plafond --force : vrai run planifié
    assert summary["consultations_listees"] == N_ROWS


def test_second_crawl_refused_while_first_is_running(portal, tmp_path):
    """Lancement à la main pendant que la tâche planifiée tourne : refusé (code 4), sans requête."""
    first = subprocess.Popen(
        [sys.executable, "-m", "pmmp_collector", "crawl"],
        cwd=tmp_path, env=crawl_env(portal, tmp_path, window=open_window()),
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    try:
        deadline = time.monotonic() + 60
        while not FakePortal.log and time.monotonic() < deadline:  # le 1er run a démarré
            time.sleep(0.2)
        assert FakePortal.log, "le premier run n'a envoyé aucune requête"
        proc, _ = run_crawl(portal, tmp_path, "--force")
        assert proc.returncode == 4, proc.stderr[-3000:]
        assert "déjà en cours" in proc.stderr and "Aucune requête envoyée" in proc.stderr
        assert first.wait(timeout=120) == 0
    finally:
        if first.poll() is None:
            first.kill()
    # Seules les requêtes du premier run : robots.txt + liste + taille de page + fiche et DCE par consultation.
    assert len(FakePortal.log) == 3 + 2 * N_ROWS
    assert json.loads((tmp_path / "storage" / "last_run.json").read_text(encoding="utf-8"))["statut"] == "succes"
    proc, summary = run_crawl(portal, tmp_path, "--force")  # verrou rendu : un nouveau run passe
    assert proc.returncode == 0, proc.stderr[-3000:]


def test_circuit_breaker_stops_real_crawl(portal, tmp_path):
    FakePortal.detail_status = 503
    proc, summary = run_crawl(portal, tmp_path, "--force")

    details = [r for r in FakePortal.log if "EntrepriseDetailsConsultation" in r["path"]]
    # 6 fiches à visiter, mais le crawl s'arrête après 3 erreurs consécutives.
    assert len(details) == 3, [r["path"] for r in FakePortal.log]
    assert proc.returncode == 1, proc.stderr[-3000:]
    assert summary["statut"] == "echec"
    assert summary["raison"] == "circuit_breaker"
    assert "3 problèmes consécutifs" in summary["circuit_breaker"]
    assert "CIRCUIT BREAKER DÉCLENCHÉ" in proc.stderr


def test_nominal_crawl_respects_collection_rules(portal, tmp_path):
    proc, summary = run_crawl(portal, tmp_path, "--force")
    assert proc.returncode == 0, proc.stderr[-3000:]
    assert summary["statut"] == "succes"
    assert summary["consultations_listees"] == N_ROWS
    assert summary["dce_telecharges"] == N_ROWS

    log = FakePortal.log
    # robots.txt + liste + postback « 100 résultats par page » + une fiche et un DCE par consultation
    assert len(log) == 3 + 2 * N_ROWS
    assert log[2]["form"]["PRADO_POSTBACK_TARGET"] == SIZE_SELECT and log[2]["form"][SIZE_SELECT] == "100"
    # User-Agent déclaré sur CHAQUE requête, y compris robots.txt
    assert {r["ua"] for r in log} == {UA}
    # Une seule requête à la fois
    assert FakePortal.max_inflight == 1
    # Pause d'au moins DOWNLOAD_DELAY entre deux requêtes vers le portail (sans jitter)
    starts = [r["t"] for r in log]
    gaps = [b - a for a, b in zip(starts, starts[1:])]
    assert min(gaps) >= DELAY * 0.95, gaps

    items = [json.loads(line) for line in (tmp_path / "storage" / "test_items.jsonl").read_text(encoding="utf-8").splitlines()]
    assert len(items) == N_ROWS
    assert {i["ref_consultation"] for i in items} == {str(1000 + i) for i in range(N_ROWS)}
    assert all(i["dce_statut"] == "telecharge" and i["statut"] == "en_cours" for i in items)


TEST_DB = os.environ.get("PMMP_TEST_DATABASE_URL")


@pytest.mark.skipif(not TEST_DB, reason="PMMP_TEST_DATABASE_URL non défini (base jetable)")
def test_two_crawls_with_database(portal, tmp_path, monkeypatch):
    """Deux runs complets en mode prod : upsert sans doublon, historique rattaché au run, collecte_runs."""
    from pmmp_collector import db

    conn = db.connect(TEST_DB)
    db.init_schema(conn)
    conn.execute("TRUNCATE historique_modifications, consultations, collecte_runs RESTART IDENTITY CASCADE")
    monkeypatch.setenv("PMMP_MODE", "prod")

    proc, summary = run_crawl(portal, tmp_path, "--force", database_url=TEST_DB)
    assert proc.returncode == 0, proc.stderr[-3000:]
    assert summary["consultations_enregistrees"] == N_ROWS

    FakePortal.detail_body = DETAIL.replace("20/10/2026 10:00", "30/10/2026 10:00").encode("utf-8")
    FakePortal.deadlines = {1000 + i: "30/10/2026 10:00" for i in range(N_ROWS)}
    proc, summary = run_crawl(portal, tmp_path, "--force", database_url=TEST_DB)
    assert proc.returncode == 0, proc.stderr[-3000:]

    runs = conn.execute("SELECT id, statut, termine_le, nb_consultations, force FROM collecte_runs ORDER BY id").fetchall()
    assert [(r["statut"], r["nb_consultations"], r["force"]) for r in runs] == [("succes", N_ROWS, True)] * 2
    assert all(r["termine_le"] is not None for r in runs)
    assert conn.execute("SELECT count(*) n FROM consultations").fetchone()["n"] == N_ROWS
    hist = conn.execute("SELECT champ, type_evenement, run_id FROM historique_modifications").fetchall()
    assert len(hist) == 2 * N_ROWS
    assert {(h["champ"], h["type_evenement"], h["run_id"]) for h in hist} == {
        ("date_limite_depot", "report_date", runs[1]["id"]), ("statut", "report_date", runs[1]["id"])}
    assert {r["statut"] for r in conn.execute("SELECT statut FROM consultations")} == {"reporte"}
    conn.close()


@pytest.mark.skipif(not TEST_DB, reason="PMMP_TEST_DATABASE_URL non défini (base jetable)")
def test_incremental_batches_resume_night_after_night(portal, tmp_path, monkeypatch):
    """6 consultations, lot de 4 : 4 fiches la 1re nuit, les 2 autres la 2e, aucune la 3e ;
    une date limite modifiée sur le portail -> seule cette fiche est revisitée."""
    from pmmp_collector import db

    conn = db.connect(TEST_DB)
    db.init_schema(conn)
    conn.execute("TRUNCATE historique_modifications, consultations, collecte_runs RESTART IDENTITY CASCADE")
    monkeypatch.setenv("PMMP_MODE", "prod")
    monkeypatch.setenv("PMMP_MAX_ITEMS", "4")

    def night():
        start = len(FakePortal.log)
        proc, summary = run_crawl(portal, tmp_path, "--force", database_url=TEST_DB)
        assert proc.returncode == 0, proc.stderr[-3000:]
        details = [r["path"] for r in FakePortal.log[start:] if "EntrepriseDetailsConsultation" in r["path"]]
        return sorted(p.split("refConsultation=")[1].split("&")[0] for p in details), summary

    visited1, s1 = night()
    assert len(visited1) == 4 and s1["consultations_enregistrees"] == 4
    visited2, _ = night()
    assert len(visited2) == 2 and set(visited1).isdisjoint(visited2)
    assert conn.execute("SELECT count(*) n FROM consultations").fetchone()["n"] == N_ROWS

    before = conn.execute("SELECT max(derniere_vue_le) m FROM consultations").fetchone()["m"]
    visited3, s3 = night()
    assert visited3 == [] and s3["statut"] == "succes"
    assert conn.execute("SELECT min(derniere_vue_le) m FROM consultations").fetchone()["m"] > before

    FakePortal.deadlines = {1002: "30/10/2026 10:00"}
    FakePortal.detail_body = DETAIL.replace("20/10/2026 10:00", "30/10/2026 10:00").encode("utf-8")
    visited4, _ = night()
    assert visited4 == ["1002"]
    hist = conn.execute(
        "SELECT c.ref_consultation ref, h.champ FROM historique_modifications h "
        "JOIN consultations c ON c.id = h.consultation_id").fetchall()
    assert {(h["ref"], h["champ"]) for h in hist} == {("1002", "date_limite_depot"), ("1002", "statut")}
    conn.close()


@pytest.mark.skipif(not TEST_DB, reason="PMMP_TEST_DATABASE_URL non défini (base jetable)")
def test_crawl_marks_dead_run_before_starting(portal, tmp_path, monkeypatch):
    """Run tué la veille (resté 'en_cours') : le run suivant le signale et le passe en échec."""
    from pmmp_collector import db

    conn = db.connect(TEST_DB)
    db.init_schema(conn)
    conn.execute("TRUNCATE historique_modifications, consultations, collecte_runs RESTART IDENTITY CASCADE")
    conn.execute("INSERT INTO collecte_runs (mode, demarre_le) VALUES ('prod', now() - interval '1 day')")
    monkeypatch.setenv("PMMP_MODE", "prod")

    proc, summary = run_crawl(portal, tmp_path, "--force", database_url=TEST_DB)
    assert proc.returncode == 0, proc.stderr[-3000:]
    assert "le run n°1" in proc.stderr and "ne s'est jamais terminé" in proc.stderr
    runs = conn.execute("SELECT id, statut FROM collecte_runs ORDER BY id").fetchall()
    assert [(r["id"], r["statut"]) for r in runs] == [(1, "echec"), (2, "succes")]
    conn.close()
