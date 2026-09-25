"""Détection des modifications entre l'enregistrement en base et la nouvelle collecte.

Fonctions pures : aucune dépendance à la base, testées dans tests/test_history.py.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

# Champs suivis -> type d'événement par défaut en cas de changement.
TRACKED_FIELDS = {
    "statut": "autre",               # affiné dans classify()
    "date_limite_depot": "report_date",  # affiné dans classify()
    "objet": "rectificatif",
    "resultat": "resultat",
    "reference": "rectificatif",
    "acheteur": "rectificatif",
    "categorie": "rectificatif",
    "lieu_execution": "rectificatif",
    "reservation_pme": "rectificatif",
    "reponse_electronique": "rectificatif",
    "date_publication": "autre",
}

EVENT_TYPES = {"rectificatif", "report_date", "annulation", "resultat", "autre"}


@dataclass(frozen=True)
class Change:
    champ: str
    ancienne_valeur: str | None
    nouvelle_valeur: str | None
    type_evenement: str


def to_text(value) -> str | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return "oui" if value else "non"
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def derive_statut(new: dict, old: dict | None, now: datetime) -> str:
    """Statut courant : annulé > reporté (date repoussée) > clôturé (date passée) > en cours."""
    if new.get("statut_portail") == "annule":
        return "annule"
    limite = new.get("date_limite_depot")
    if limite is not None and limite <= now:
        return "cloture"
    if new.get("statut_portail") == "reporte":
        return "reporte"
    old_limite = old.get("date_limite_depot") if old else None
    if old_limite is not None and limite is not None and limite > old_limite:
        return "reporte"
    if old and old.get("statut") == "reporte":
        return "reporte"
    return "en_cours"


def classify(champ: str, old_value, new_value) -> str:
    if champ == "statut":
        return {"annule": "annulation", "reporte": "report_date"}.get(new_value, "autre")
    if champ == "date_limite_depot":
        if old_value is not None and new_value is not None and new_value > old_value:
            return "report_date"
        return "rectificatif"
    return TRACKED_FIELDS.get(champ, "autre")


# Fiches à revisiter même sans changement visible dans la liste : la dernière visite a échoué.
RETRY_DCE_STATUTS = {"echec", "echec_fiche_detail"}


def refresh_reason(listing_deadline: datetime | None, listing_statut: str | None, known: dict | None) -> str | None:
    """Pourquoi la fiche détail doit être (re)visitée, ou None si la base est déjà à jour.

    Collecte incrémentale : seules les consultations nouvelles, modifiées d'après la
    liste (date limite, annulation/report) ou en échec au run précédent coûtent des requêtes.
    """
    if known is None:
        return "nouvelle"
    if known.get("dce_statut") in RETRY_DCE_STATUTS:
        return "echec_precedent"
    if listing_statut and listing_statut != known.get("statut"):
        return "statut"
    if listing_deadline is not None and listing_deadline != known.get("date_limite_depot"):
        return "date_limite"
    return None


def compute_changes(old: dict | None, new: dict) -> list[Change]:
    """Liste des champs suivis qui changent. Nouvel enregistrement -> aucune ligne.

    Une valeur absente de la nouvelle collecte (None) n'est pas un changement :
    l'upsert conserve alors l'ancienne valeur (COALESCE).
    """
    if not old:
        return []
    changes = []
    for champ in TRACKED_FIELDS:
        new_value = new.get(champ)
        if new_value is None:
            continue
        old_value = old.get(champ)
        if old_value == new_value:
            continue
        changes.append(Change(champ, to_text(old_value), to_text(new_value), classify(champ, old_value, new_value)))
    return changes
