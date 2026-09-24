"""Non-régression sur les pages RÉELLES capturées en mode test (fixtures/live/).

Ignorés tant qu'aucune page n'a été capturée. Après une capture, ces tests
vérifient que les sélecteurs extraient bien les champs obligatoires.
"""
from pathlib import Path

import pytest
from parsel import Selector

from pmmp_collector.models import Consultation
from pmmp_collector.parsers import merge_listing_detail, parse_detail_page, parse_listing_page

LIVE = Path(__file__).resolve().parents[1] / "fixtures" / "live"
BASE = "https://www.marchespublics.gov.ma/pmmp/index.php"

listing_pages = sorted((LIVE / "liste").glob("*.html")) if (LIVE / "liste").is_dir() else []
detail_pages = sorted((LIVE / "detail").glob("*.html")) if (LIVE / "detail").is_dir() else []


def read(path: Path) -> Selector:
    return Selector(text=path.read_bytes().decode("utf-8", errors="replace"))


@pytest.mark.skipif(not listing_pages, reason="aucune page de liste réelle dans fixtures/live/liste")
@pytest.mark.parametrize("path", listing_pages, ids=lambda p: p.name)
def test_real_listing_page(path):
    data = parse_listing_page(read(path), BASE)
    assert data["rows"], "aucune ligne extraite : sélecteurs à ajuster dans parsers.py"
    assert data["pager"]["pagestate"], "PRADO_PAGESTATE introuvable"
    for row in data["rows"]:
        assert row["org_acronyme"] and row["ref_consultation"], row
        Consultation.model_validate(row)


@pytest.mark.skipif(not detail_pages, reason="aucune fiche détail réelle dans fixtures/live/detail")
@pytest.mark.parametrize("path", detail_pages, ids=lambda p: p.name)
def test_real_detail_page(path):
    org, _, ref = path.stem.partition("__")
    detail = parse_detail_page(read(path), BASE)
    assert detail["objet"], "objet introuvable sur la fiche détail"
    assert detail["date_limite_depot"], "date limite introuvable sur la fiche détail"
    # Aucune de ces fiches n'a de résultat publié : ne pas confondre avec "Résultats par page".
    assert detail["resultat"] is None, detail["resultat"]
    merged = merge_listing_detail({"org_acronyme": org, "ref_consultation": ref, "url_detail": f"{BASE}?x"}, detail)
    Consultation.model_validate(merged)


RECHERCHE = sorted((LIVE / "recherche").glob("*.html")) if (LIVE / "recherche").is_dir() else []


@pytest.mark.skipif(not RECHERCHE, reason="aucun formulaire de recherche réel dans fixtures/live/recherche")
@pytest.mark.parametrize("path", RECHERCHE, ids=lambda p: p.name)
def test_real_search_form(path):
    from pmmp_collector.parsers import find_search_button, form_fields

    sel = read(path)
    name, _ = find_search_button(sel)
    assert name.endswith("$lancerRecherche")
    _, fields = form_fields(sel, BASE)
    assert fields.get("PRADO_PAGESTATE")
    assert "ctl0$CONTENU_PAGE$AdvancedSearch$annonceType" not in fields  # désactivé sur le portail
