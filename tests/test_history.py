from datetime import datetime

from pmmp_collector.history import compute_changes, derive_statut
from pmmp_collector.models import TZ

NOW = datetime(2026, 9, 23, 23, 30, tzinfo=TZ)
D1 = datetime(2026, 10, 20, 10, 0, tzinfo=TZ)
D2 = datetime(2026, 10, 30, 10, 0, tzinfo=TZ)

OLD = {"statut": "en_cours", "date_limite_depot": D1, "objet": "Travaux A", "resultat": None, "reservation_pme": True}


def types(changes):
    return {c.champ: c.type_evenement for c in changes}


def test_new_record_has_no_history():
    assert compute_changes(None, {"objet": "x"}) == []


def test_report_de_date():
    new = {"date_limite_depot": D2, "objet": "Travaux A"}
    new["statut"] = derive_statut(new, OLD, NOW)
    assert new["statut"] == "reporte"
    assert types(compute_changes(OLD, new)) == {"date_limite_depot": "report_date", "statut": "report_date"}


def test_annulation():
    new = {"date_limite_depot": D1, "objet": "Travaux A", "statut_portail": "annule"}
    new["statut"] = derive_statut(new, OLD, NOW)
    assert types(compute_changes(OLD, new)) == {"statut": "annulation"}


def test_rectificatif_et_resultat():
    new = {"date_limite_depot": D1, "objet": "Travaux A (rectifié)", "resultat": "SOCIETE X", "statut": "en_cours"}
    assert types(compute_changes(OLD, new)) == {"objet": "rectificatif", "resultat": "resultat"}


def test_absent_value_is_not_a_change():
    new = {"date_limite_depot": D1, "objet": "Travaux A", "statut": "en_cours", "reservation_pme": None}
    assert compute_changes(OLD, new) == []


def test_bool_history_text():
    new = {"date_limite_depot": D1, "objet": "Travaux A", "statut": "en_cours", "reservation_pme": False}
    (c,) = compute_changes(OLD, new)
    assert (c.ancienne_valeur, c.nouvelle_valeur) == ("oui", "non")


def test_statut_cloture_when_deadline_passed():
    past = datetime(2026, 9, 1, tzinfo=TZ)
    assert derive_statut({"date_limite_depot": past}, None, NOW) == "cloture"
    assert derive_statut({"date_limite_depot": D1}, None, NOW) == "en_cours"
    assert derive_statut({"date_limite_depot": D1}, {"statut": "reporte", "date_limite_depot": D1}, NOW) == "reporte"
