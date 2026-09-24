from parsel import Selector

from pmmp_collector.parsers import (
    interpret_pme,
    interpret_reponse_electronique,
    interpret_statut,
    merge_listing_detail,
    parse_detail_page,
    parse_listing_page,
)

LIST_URL = "https://www.marchespublics.gov.ma/pmmp/index.php?page=entreprise.EntrepriseAdvancedSearch&AllCons"
DETAIL_URL = (
    "https://www.marchespublics.gov.ma/pmmp/index.php?page=entreprise.EntrepriseDetailsConsultation"
    "&refConsultation=987654&orgAcronyme=x7k"
)


def test_listing_rows(fixture_html):
    data = parse_listing_page(Selector(text=fixture_html("synthetic/liste_page1.html")), LIST_URL)
    rows = data["rows"]
    assert len(rows) == 2
    r = rows[0]
    assert (r["org_acronyme"], r["ref_consultation"]) == ("x7k", "987654")
    assert r["reference"] == "12/2026/AOO"
    assert r["objet"].startswith("Travaux d'aménagement")
    assert "تهيئة الطرق الجماعية" in r["objet"]
    assert r["acheteur"] == "COMMUNE DE TIZNIT"
    assert r["categorie"] == "Travaux"
    assert r["lieu_execution"] == "Tiznit"
    assert r["date_limite_depot"] == "20/10/2026 10:00"
    assert r["date_publication"] == "15/09/2026"
    assert r["reservation_pme"] is True
    assert r["reponse_electronique"] is True
    assert r["url_detail"] == DETAIL_URL
    assert rows[1]["reponse_electronique"] is False
    assert rows[1]["reservation_pme"] is None


def test_pager(fixture_html):
    pager = parse_listing_page(Selector(text=fixture_html("synthetic/liste_page1.html")), LIST_URL)["pager"]
    assert pager["pagestate"].endswith("PAGE1")
    assert pager["current_page"] == 1
    assert pager["total_pages"] == 3
    assert pager["page_input_name"] == "ctl0$CONTENU_PAGE$resultSearch$numPageTop"
    assert pager["postback_target"] == "ctl0$CONTENU_PAGE$resultSearch$DefaultButtonTop"


def test_detail_page(fixture_html):
    d = parse_detail_page(Selector(text=fixture_html("synthetic/detail_987654.html")), DETAIL_URL)
    assert d["reference"] == "12/2026/AOO"
    assert d["objet"].endswith("(lot unique)")
    assert d["categorie"] == "Travaux"
    assert d["type_procedure"] == "Appel d'offres ouvert"
    assert d["date_publication"] == "15/09/2026 09:30"
    assert d["date_limite_depot"] == "20/10/2026 10:00"
    assert d["reponse_electronique"] is True
    assert d["reservation_pme"] is True
    # Seul le lien DCE direct du même site est retenu (pas javascript:, pas externe).
    assert d["dce_urls"] == [
        "https://www.marchespublics.gov.ma/pmmp/index.php?page=entreprise.EntrepriseDownloadCompleteDce"
        "&refConsultation=987654&orgAcronyme=x7k"
    ]


def test_merge_keeps_natural_key_and_prefers_detail():
    merged = merge_listing_detail(
        {"org_acronyme": "x7k", "ref_consultation": "1", "objet": "court", "categorie": "Travaux"},
        {"org_acronyme": "AUTRE", "objet": "objet complet", "categorie": None, "dce_urls": ["u"]},
    )
    assert merged["org_acronyme"] == "x7k"
    assert merged["objet"] == "objet complet"
    assert merged["categorie"] == "Travaux"
    assert merged["dce_urls"] == ["u"]


def test_interpretations():
    assert interpret_reponse_electronique("Réponse électronique : Obligatoire") is True
    assert interpret_reponse_electronique("Réponse électronique refusée") is False
    assert interpret_reponse_electronique("rien") is None
    assert interpret_pme("Réservé PME : Non") is False
    assert interpret_pme("Marché réservé aux PME") is True
    assert interpret_statut("Avis d'annulation publié le 01/10/2026") == "annule"
    assert interpret_statut("Avis de report de la date limite") == "reporte"
    assert interpret_statut("Rapport annuel") is None
