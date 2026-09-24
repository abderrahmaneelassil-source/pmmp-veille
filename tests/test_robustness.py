"""Cas limites : un item ou une page en erreur est loggé et écarté, le run continue."""
import logging

import pytest
from scrapy.exceptions import DropItem
from scrapy.http import HtmlResponse, Request
from scrapy.spidermiddlewares.httperror import HttpError
from scrapy.utils.test import get_crawler
from twisted.internet.error import TimeoutError as TxTimeoutError
from twisted.python.failure import Failure

from pmmp_collector.pipelines import ValidationPipeline
from pmmp_collector.spiders.pmmp import PmmpSpider

LIST_URL = "https://www.marchespublics.gov.ma/pmmp/index.php?page=entreprise.EntrepriseAdvancedSearch&AllCons"
DETAIL_URL = (
    "https://www.marchespublics.gov.ma/pmmp/index.php?page=entreprise.EntrepriseDetailsConsultation"
    "&refConsultation=987654&orgAcronyme=x7k"
)
UNEXPECTED_HTML = "<html><body><h1>Maintenance en cours</h1><p>Revenez plus tard.</p></body></html>"


@pytest.fixture
def spider(tmp_path, monkeypatch):
    monkeypatch.setenv("PMMP_STORAGE_DIR", str(tmp_path / "storage"))
    monkeypatch.setenv("PMMP_FIXTURES_DIR", str(tmp_path / "fixtures"))
    crawler = get_crawler(PmmpSpider)
    return PmmpSpider.from_crawler(crawler, force="0", max_pages="1", max_items="")


def html(url, body, request=None):
    return HtmlResponse(url, body=body.encode("utf-8"), encoding="utf-8", request=request or Request(url))


def listing_row(spider, fixture_html):
    out = list(spider.parse_listing(html(LIST_URL, fixture_html("synthetic/liste_page1.html")), page=1))
    return out[0].cb_kwargs["listing"]


def failure_for(request, exc):
    f = Failure(exc)
    f.request = request
    return f


# --- Validation : un item invalide est écarté, les suivants passent -----------

@pytest.mark.parametrize("date", [None, "", "bientôt", "32/13/2026", "01/01/1900"])
def test_bad_deadline_drops_only_that_item(spider, fixture_html, caplog, date):
    pipeline = ValidationPipeline(spider.crawler.stats)
    good = listing_row(spider, fixture_html)
    bad = {**good, "date_limite_depot": date}

    with caplog.at_level(logging.WARNING), pytest.raises(DropItem):
        pipeline.process_item(bad)
    assert "Consultation écartée x7k/987654" in caplog.text and "date_limite_depot" in caplog.text
    assert spider.crawler.stats.get_value("pmmp/items_invalid") == 1
    assert pipeline.process_item(dict(good))["ref_consultation"] == "987654"


# --- Fiche détail ----------------------------------------------------------------

def test_detail_without_dce_link(spider, fixture_html):
    listing = listing_row(spider, fixture_html)
    body = fixture_html("synthetic/detail_987654.html").replace("Dce", "Xyz").replace("Dossier de consultation", "Dossier")
    (item,) = spider.parse_detail(html(DETAIL_URL, body), listing)
    assert item["dce_statut"] == "aucun_lien" and item["dce_paths"] == []
    ValidationPipeline(spider.crawler.stats).process_item(item)


def test_detail_unexpected_html_keeps_listing_data(spider, fixture_html):
    listing = listing_row(spider, fixture_html)
    (item,) = spider.parse_detail(html(DETAIL_URL, UNEXPECTED_HTML), listing)
    model = ValidationPipeline(spider.crawler.stats).process_item(item)
    assert model["objet"].startswith("Travaux d'aménagement") and model["dce_statut"] == "aucun_lien"


@pytest.mark.parametrize("exc", [
    "404",
    TxTimeoutError("délai dépassé"),
])
def test_detail_not_found_or_timeout_keeps_listing_data(spider, fixture_html, caplog, exc):
    listing = listing_row(spider, fixture_html)
    request = Request(DETAIL_URL, cb_kwargs={"listing": listing})
    if exc == "404":
        exc = HttpError(HtmlResponse(DETAIL_URL, status=404, body=b"", request=request))
    with caplog.at_level(logging.ERROR):
        (item,) = spider.detail_failed(failure_for(request, exc))
    assert "Échec de la fiche détail" in caplog.text
    assert item["dce_statut"] == "echec_fiche_detail"
    assert spider.crawler.stats.get_value("pmmp/detail_errors") == 1
    ValidationPipeline(spider.crawler.stats).process_item(item)


# --- Liste et DCE ----------------------------------------------------------------

def test_listing_unexpected_html_is_logged_not_raised(spider, caplog):
    with caplog.at_level(logging.WARNING):
        out = list(spider.parse_listing(html(LIST_URL, UNEXPECTED_HTML), page=1))
    assert out == []
    assert "ni consultation ni formulaire PRADO" in caplog.text


def test_listing_timeout_releases_pending_details(spider, fixture_html, caplog):
    spider.max_pages = 0
    list(spider.parse_listing(html(LIST_URL, fixture_html("synthetic/liste_page1.html")), page=1))
    assert len(spider.pending_details) == 2
    with caplog.at_level(logging.ERROR):
        out = list(spider.listing_failed(failure_for(Request(LIST_URL), TxTimeoutError())))
    assert len(out) == 2 and spider.pending_details == []
    assert "Échec de la page de liste" in caplog.text


@pytest.mark.parametrize("kind", ["timeout", "404"])
def test_dce_failure_still_yields_item(spider, fixture_html, caplog, kind):
    listing = listing_row(spider, fixture_html)
    (dce_req,) = spider.parse_detail(html(DETAIL_URL, fixture_html("synthetic/detail_987654.html")), listing)
    exc = TxTimeoutError() if kind == "timeout" else HttpError(
        HtmlResponse(dce_req.url, status=404, body=b"", request=dce_req))
    with caplog.at_level(logging.ERROR):
        (item,) = spider.dce_failed(failure_for(dce_req, exc))
    assert item["dce_statut"] == "echec" and "Échec du téléchargement DCE" in caplog.text
    ValidationPipeline(spider.crawler.stats).process_item(item)
