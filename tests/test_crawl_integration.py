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
from zoneinfo import ZoneInfo

import pytest

ROOT = Path(__file__).resolve().parents[1]
UA = "TACHFIR-VeilleMarchesPublics/1.0 (+contact: sales@tachfir.com)"
DELAY = 1.0
N_ROWS = 6

ROW = """<tr>
  <td class="col-90"><div class="line-info-bulle">Appel d'offres ouvert</div><div>Travaux</div>
    <div class="date date-min">15/09/2026</div></td>
  <td class="col-450"><div class="objet-line"><span class="ref">{ref}/2026/AOO</span>
    <div id="x_panelBlocObjet"><strong>Objet :</strong> Travaux n°{ref} — تهيئة</div>
    <div id="x_panelBlocDenomination"><strong>Acheteur public :</strong> COMMUNE DE TEST</div></div></td>
  <td class="col-90 cons_dateEnd"><div class="cloture-line"><span>20/10/2030 10:00</span></div></td>
  <td class="actions"><a href="index.php?page=entreprise.EntrepriseDetailsConsultation&amp;refConsultation={ref}&amp;orgAcronyme=t1">Détail</a></td>
</tr>"""

LISTING = f"""<!DOCTYPE html><html><head><meta charset="utf-8"></head><body>
<form method="post" action="liste.html">
<input type="hidden" name="PRADO_PAGESTATE" value="STATE1" />
<input type="text" name="ctl0$CONTENU_PAGE$resultSearch$numPageTop" value="1" />
/ <span id="ctl0_CONTENU_PAGE_resultSearch_nombrePageTop">1</span>
<table>{"".join(ROW.format(ref=1000 + i) for i in range(N_ROWS))}</table>
</form></body></html>""".encode("utf-8")


class FakePortal(BaseHTTPRequestHandler):
    detail_status = 200  # 503 -> panne simulée sur les fiches détail
    log: list = []
    inflight = 0
    max_inflight = 0
    lock = threading.Lock()

    def _serve(self):
        cls = type(self)
        with cls.lock:
            cls.inflight += 1
            cls.max_inflight = max(cls.max_inflight, cls.inflight)
            cls.log.append({"t": time.monotonic(), "path": self.path, "ua": self.headers.get("User-Agent")})
        try:
            time.sleep(0.1)  # rend visible un éventuel chevauchement de requêtes
            if self.path == "/robots.txt":
                self._reply(404, b"")
            elif self.path.startswith("/liste.html"):
                self._reply(200, LISTING)
            elif "EntrepriseDetailsConsultation" in self.path:
                if cls.detail_status != 200:
                    self._reply(cls.detail_status, b"<html>Service indisponible</html>")
                else:
                    self._reply(200, (ROOT / "fixtures/synthetic/detail_987654.html").read_bytes())
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
    FakePortal.detail_status = 200
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


def run_crawl(portal, tmp_path, *args, database_url=""):
    env = {
        **os.environ,
        "PMMP_BASE_URL": f"http://127.0.0.1:{portal.server_port}/",
        "PMMP_SEARCH_PATH": "liste.html",
        "PMMP_DATABASE_URL": database_url,
        "PMMP_MODE": os.environ.get("PMMP_MODE", "test"),
        "PMMP_USER_AGENT": UA,
        "PMMP_DOWNLOAD_DELAY": str(DELAY),
        "PMMP_ALLOWED_WINDOW": closed_window(),
        "PMMP_CB_MAX_CONSECUTIVE": "3",
        "PMMP_FORCE_MAX_ITEMS": "10",
        "PMMP_STORAGE_DIR": str(tmp_path / "storage"),
        "PMMP_FIXTURES_DIR": str(tmp_path / "fixtures"),
        "PYTHONPATH": str(ROOT / "src"),
        "PYTHONIOENCODING": "utf-8",
    }
    proc = subprocess.run(
        [sys.executable, "-m", "pmmp_collector", "crawl", *args],
        cwd=tmp_path, env=env, capture_output=True, text=True, encoding="utf-8", timeout=120,
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
    # robots.txt + liste + une fiche et un DCE par consultation
    assert len(log) == 2 + 2 * N_ROWS
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
