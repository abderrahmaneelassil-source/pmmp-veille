"""Parcours du spider sur les fixtures, sans réseau : pagination PRADO et fiche détail."""
from urllib.parse import parse_qs
from pathlib import Path

import pytest
from scrapy.http import FormRequest, HtmlResponse, Request
from scrapy.utils.test import get_crawler

from pmmp_collector.spiders.pmmp import PRIORITY_DETAIL, PRIORITY_LISTING, PmmpSpider
from pmmp_collector.storage import DceStore

ROOT = Path(__file__).resolve().parents[1]
LIST_URL = "https://www.marchespublics.gov.ma/pmmp/index.php?page=entreprise.EntrepriseAdvancedSearch&AllCons"
DETAIL_URL = (
    "https://www.marchespublics.gov.ma/pmmp/index.php?page=entreprise.EntrepriseDetailsConsultation"
    "&refConsultation=987654&orgAcronyme=x7k"
)


@pytest.fixture
def spider(tmp_path, monkeypatch):
    monkeypatch.setenv("PMMP_STORAGE_DIR", str(tmp_path / "storage"))
    monkeypatch.setenv("PMMP_FIXTURES_DIR", str(tmp_path / "fixtures"))
    crawler = get_crawler(PmmpSpider)
    return PmmpSpider.from_crawler(crawler, force="0", max_pages="", max_items="")


def html_response(url, body, request=None):
    request = request or Request(url)
    return HtmlResponse(url, body=body.encode("utf-8"), encoding="utf-8", request=request)


def test_listing_yields_prado_postback_and_defers_details(spider, fixture_html):
    response = html_response(LIST_URL, fixture_html("synthetic/liste_page1.html"))
    out = list(spider.parse_listing(response, page=1))

    # Rien ne s'intercale entre deux postbacks : seule la page suivante est émise.
    (nxt,) = out
    assert isinstance(nxt, FormRequest)
    assert [r.url for r in spider.pending_details][0] == DETAIL_URL
    assert all(r.priority == PRIORITY_DETAIL for r in spider.pending_details)
    assert nxt.url == LIST_URL
    assert nxt.method == "POST"
    assert nxt.priority == PRIORITY_LISTING
    form = {k: v[0] if v else "" for k, v in parse_qs(nxt.body.decode(), keep_blank_values=True).items()}
    # Le PRADO_PAGESTATE de la réponse est réinjecté tel quel dans le postback suivant.
    assert form["PRADO_PAGESTATE"].endswith("PAGE1")
    assert form["PRADO_POSTBACK_TARGET"] == "ctl0$CONTENU_PAGE$resultSearch$DefaultButtonTop"
    assert form["ctl0$CONTENU_PAGE$resultSearch$numPageTop"] == "2"
    assert nxt.cb_kwargs == {"page": 2}

    # HTML brut archivé + copie en fixtures (mode test)
    assert list((spider.cfg.storage_dir / "raw_html").rglob("page0001.html"))
    assert list((spider.cfg.fixtures_dir / "live" / "liste").glob("page0001.html"))


def test_last_page_releases_details(spider, fixture_html):
    spider.max_pages = 1
    response = html_response(LIST_URL, fixture_html("synthetic/liste_page1.html"))
    out = list(spider.parse_listing(response, page=1))
    assert len(out) == 2 and not any(isinstance(r, FormRequest) for r in out)
    assert spider.pending_details == []


def test_pagination_stops_if_page_repeats(spider, fixture_html):
    body = fixture_html("synthetic/liste_page1.html")
    list(spider.parse_listing(html_response(LIST_URL, body), page=1))
    out = list(spider.parse_listing(html_response(LIST_URL, body), page=2))
    assert len(out) == 2 and not any(isinstance(r, FormRequest) for r in out)


def test_max_items(spider, fixture_html):
    spider.max_items = 1
    out = list(spider.parse_listing(html_response(LIST_URL, fixture_html("synthetic/liste_page1.html")), page=1))
    assert len(out) == 1 and not isinstance(out[0], FormRequest)


def _listing_row(spider, fixture_html):
    spider.max_pages = 1
    out = list(spider.parse_listing(html_response(LIST_URL, fixture_html("synthetic/liste_page1.html")), page=1))
    return out[0].cb_kwargs["listing"]


def test_detail_then_dce_download(spider, fixture_html):
    listing = _listing_row(spider, fixture_html)
    (dce_req,) = spider.parse_detail(html_response(DETAIL_URL, fixture_html("synthetic/detail_987654.html")), listing)
    assert dce_req.meta["dce_download"] is True

    zip_resp = HtmlResponse(
        dce_req.url, body=b"PK\x03\x04fake", request=dce_req,
        headers={"Content-Type": "application/zip", "Content-Disposition": 'attachment; filename="DCE_12-2026.zip"'},
    )
    (item,) = spider.save_dce(zip_resp, **dce_req.cb_kwargs)
    assert item["dce_statut"] == "telecharge"
    assert item["dce_paths"][0].endswith("DCE_12-2026.zip")
    assert item["categorie"] == "Travaux" and item["raw_html_detail"]

    # Second passage : DCE déjà présent sur disque -> aucune nouvelle requête.
    (again,) = spider.parse_detail(html_response(DETAIL_URL, fixture_html("synthetic/detail_987654.html")), listing)
    assert isinstance(again, dict) and again["dce_statut"] == "deja_present"


def test_dce_intermediate_page_is_never_submitted(spider, fixture_html):
    listing = _listing_row(spider, fixture_html)
    (dce_req,) = spider.parse_detail(html_response(DETAIL_URL, fixture_html("synthetic/detail_987654.html")), listing)
    page = html_response(dce_req.url, "<html><form><div class='g-recaptcha'></div></form></html>", request=dce_req)
    (item,) = spider.save_dce(page, **dce_req.cb_kwargs)
    assert item["dce_statut"] == "captcha"
    assert spider.dce_blocked_reason == "captcha"
    assert DceStore(spider.cfg.storage_dir / "dce").existing("x7k", "987654") == []

SEARCH_URL = "https://www.marchespublics.gov.ma/index.php?page=entreprise.EntrepriseAdvancedSearch&searchAnnCons"


def test_search_form_is_submitted_with_defaults(spider, fixture_html):
    response = html_response(SEARCH_URL, fixture_html("synthetic/recherche_formulaire.html"))
    (req,) = list(spider.parse_search_form(response))
    assert isinstance(req, FormRequest) and req.method == "POST"
    assert req.url == SEARCH_URL
    assert req.callback == spider.parse_listing and req.cb_kwargs == {"page": 1}
    form = {k: v[0] if v else "" for k, v in parse_qs(req.body.decode(), keep_blank_values=True).items()}
    button = "ctl0$CONTENU_PAGE$AdvancedSearch$lancerRecherche"
    assert form["PRADO_POSTBACK_TARGET"] == button and form[button] == "Lancer la recherche"
    assert form["PRADO_PAGESTATE"] == "eJzFORMSTATE"
    # Champ désactivé non envoyé (comme un navigateur) ; valeurs par défaut conservées.
    assert "ctl0$CONTENU_PAGE$AdvancedSearch$annonceType" not in form
    assert form["ctl0$CONTENU_PAGE$AdvancedSearch$categorie"] == "0"
    assert form["ctl0$CONTENU_PAGE$AdvancedSearch$dateMiseEnLigneStart"] == "23/09/2026"
    assert form["ctl0$CONTENU_PAGE$AdvancedSearch$rechercheFloue"] == "ctl0$CONTENU_PAGE$AdvancedSearch$floue"
    # Aucun autre bouton « cliqué ».
    assert "ctl0$CONTENU_PAGE$AdvancedSearch$boutonClear" not in form
    assert "ctl0$CONTENU_PAGE$AdvancedSearch$ctl85" not in form
    assert list((spider.cfg.fixtures_dir / "live" / "recherche").glob("formulaire.html"))


def test_results_page_as_start_page_is_parsed_directly(spider, fixture_html):
    out = list(spider.parse_search_form(html_response(LIST_URL, fixture_html("synthetic/liste_page1.html"))))
    (nxt,) = out
    assert nxt.cb_kwargs == {"page": 2}


def test_page_size_is_requested_once_then_listing_is_parsed(spider):
    from parsel import Selector

    from pmmp_collector.parsers import parse_listing_page

    # Vraie page de liste (10 résultats par page, taille par défaut du portail)
    body = HtmlResponse(LIST_URL, body=(ROOT / "fixtures/live/liste/page0001.html").read_bytes()).text
    (resize,) = list(spider.parse_listing(html_response(LIST_URL, body), page=1))
    assert isinstance(resize, FormRequest) and resize.cb_kwargs == {"page": 1}
    form = {k: v[0] if v else "" for k, v in parse_qs(resize.body.decode(), keep_blank_values=True).items()}
    target = "ctl0$CONTENU_PAGE$resultSearch$listePageSizeTop"
    assert form["PRADO_POSTBACK_TARGET"] == target and form[target] == "100"
    assert spider.pending_details == [] and spider.items_scheduled == 0

    # Réponse au postback (même page ici) : pas de nouvelle demande, les lignes sont traitées.
    out = list(spider.parse_listing(html_response(LIST_URL, body), page=1))
    assert len(out) == 1 and out[0].cb_kwargs == {"page": 2}
    assert len(spider.pending_details) == len(parse_listing_page(Selector(text=body), LIST_URL)["rows"]) == 10
