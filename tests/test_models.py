from datetime import datetime

import pytest
from pydantic import ValidationError

from pmmp_collector.models import TZ, Consultation

BASE = {
    "org_acronyme": "x7k",
    "ref_consultation": "987654",
    "objet": "  Travaux   d'aménagement\xa0— تهيئة ",
    "acheteur": "COMMUNE DE TIZNIT",
    "date_limite_depot": "20/10/2026 10:00",
    "url_detail": "https://www.marchespublics.gov.ma/pmmp/index.php?x=1",
}


def test_valid_item_is_normalised():
    c = Consultation.model_validate({**BASE, "date_publication": "15/09/2026", "reservation_pme": "Oui"})
    assert c.objet == "Travaux d'aménagement — تهيئة"
    assert c.date_limite_depot == datetime(2026, 10, 20, 10, 0, tzinfo=TZ)
    assert c.date_publication == datetime(2026, 9, 15, tzinfo=TZ)
    assert c.reservation_pme is True
    assert c.reponse_electronique is None


def test_arabic_indic_digits():
    c = Consultation.model_validate({**BASE, "date_limite_depot": "٢٠/١٠/٢٠٢٦ ١٠:٠٠"})
    assert c.date_limite_depot == datetime(2026, 10, 20, 10, 0, tzinfo=TZ)


@pytest.mark.parametrize("field,value", [
    ("objet", "   "),
    ("acheteur", None),
    ("org_acronyme", ""),
    ("date_limite_depot", "bientôt"),
    ("date_limite_depot", None),
    ("date_limite_depot", "01/01/1900"),
    ("reservation_pme", "peut-être"),
])
def test_invalid_items_are_rejected(field, value):
    with pytest.raises(ValidationError):
        Consultation.model_validate({**BASE, field: value})
