"""Formats des réponses (servent aussi à la documentation /docs)."""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel

# Valeurs autorisées par le CHECK de consultations.statut (db/schema.sql).
StatutConsultation = Literal["en_cours", "cloture", "annule", "reporte"]


class Sante(BaseModel):
    api: str
    base: str
    base_de_donnees: str | None = None
    lecture_seule: bool | None = None


class ConsultationResume(BaseModel):
    org_acronyme: str
    ref_consultation: str
    reference: str | None
    objet: str
    acheteur: str
    categorie: str | None
    type_procedure: str | None
    lieu_execution: str | None
    date_publication: datetime | None
    date_limite_depot: datetime
    statut: str
    url_detail: str


class Consultation(ConsultationResume):
    reservation_pme: bool | None
    reponse_electronique: bool | None
    resultat: str | None
    dce_urls: list[str]
    dce_statut: str | None
    premiere_vue_le: datetime
    derniere_vue_le: datetime
    mis_a_jour_le: datetime


class PageConsultations(BaseModel):
    total: int  # nombre total de résultats pour ces filtres, toutes pages confondues
    limit: int
    offset: int
    resultats: list[ConsultationResume]


class Modification(BaseModel):
    champ: str
    ancienne_valeur: str | None
    nouvelle_valeur: str | None
    type_evenement: str
    detecte_le: datetime
    run_id: int | None


class Run(BaseModel):
    id: int
    statut: str
    mode: str
    force: bool
    demarre_le: datetime
    termine_le: datetime | None
    duree_secondes: int | None
    raison: str | None
    nb_pages: int | None
    nb_consultations: int | None
    nb_ecartees: int | None
    # Compteurs pmmp/*_errors du JSON stats (ex. {"detail_errors": 2}) : seul endroit
    # où les erreurs de fiche, de DCE et de base sont comptées (CHECKLIST.md §9).
    erreurs: dict[str, int]


class DernierRun(BaseModel):
    dernier_run: Run | None          # None : le collecteur n'a encore jamais tourné
    dernier_succes_le: datetime | None
