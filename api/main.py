"""API de consultation PMMP, en LECTURE SEULE (README §12).

Composant séparé du collecteur : il lit la base pmmp_veille, le collecteur reste
seul à y écrire. Aucune route d'écriture, aucune authentification (choix
temporaire : à n'exposer que sur 127.0.0.1).

Lancement, depuis la racine du projet :
    python -m uvicorn api.main:app --host 127.0.0.1 --port 8000
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Annotated

import psycopg
from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.responses import JSONResponse, RedirectResponse

from api import db
from api.schemas import (
    Consultation, ConsultationResume, DernierRun, Modification, PageConsultations, Sante,
    StatutConsultation,
)

logger = logging.getLogger("pmmp_api")

app = FastAPI(
    title="API PMMP (lecture seule)",
    description=(
        "Consultation des appels d'offres collectés sur le Portail Marocain des "
        "Marchés Publics. Lecture seule, sans authentification : usage local uniquement."
    ),
    version="1.0.0",
)

Conn = Annotated[psycopg.Connection, Depends(db.get_conn)]

_RESUME = ", ".join(ConsultationResume.model_fields)
_DETAIL = ", ".join(Consultation.model_fields)


@app.exception_handler(db.DatabaseUnavailable)
@app.exception_handler(psycopg.OperationalError)
def base_indisponible(request: Request, exc: Exception) -> JSONResponse:
    # Le détail (hôte, cause) va dans le log du serveur, pas dans la réponse.
    logger.warning("Base de données indisponible (%s) : %s", request.url.path, exc)
    return JSONResponse(status_code=503, content={"detail": "Base de données indisponible"})


def _contient(valeur: str) -> str:
    """Motif ILIKE « contient » ; % et _ saisis par l'utilisateur restent littéraux."""
    echappee = valeur.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{echappee}%"


def _introuvable(org: str, ref: str) -> HTTPException:
    return HTTPException(status_code=404, detail=f"Consultation introuvable : {org}/{ref}")


@app.get("/", include_in_schema=False)
def accueil() -> RedirectResponse:
    """Le lien affiché par uvicorn (http://127.0.0.1:8000) mène à la documentation."""
    return RedirectResponse(url="/docs")


@app.get("/health", response_model=Sante, responses={503: {"model": Sante}})
def health():
    """L'API répond et la base est joignable, en lecture seule."""
    try:
        with db.connection() as conn:
            row = conn.execute(
                "SELECT current_database() AS base_de_donnees,"
                " current_setting('transaction_read_only') = 'on' AS lecture_seule"
            ).fetchone()
    except (db.DatabaseUnavailable, psycopg.Error) as exc:
        logger.warning("Contrôle de santé : base indisponible : %s", exc)
        return JSONResponse(status_code=503, content={"api": "ok", "base": "indisponible"})
    return Sante(api="ok", base="ok", **row)


@app.get("/consultations", response_model=PageConsultations)
def lister_consultations(
    conn: Conn,
    categorie: Annotated[str | None, Query(description="Contient ce texte, sans tenir compte de la casse (ex. travaux)")] = None,
    acheteur: Annotated[str | None, Query(description="Contient ce texte, sans tenir compte de la casse")] = None,
    statut: StatutConsultation | None = None,
    date_limite_avant: Annotated[datetime | None, Query(description="Date limite de dépôt strictement antérieure (ex. 2026-10-01 ou 2026-10-01T10:00). Sans fuseau : heure du Maroc.")] = None,
    date_limite_apres: Annotated[datetime | None, Query(description="Date limite de dépôt postérieure ou égale")] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0, le=1_000_000)] = 0,
):
    """Consultations triées par date limite de dépôt, la plus proche d'abord."""
    # Chaque filtre ajoute un fragment SQL fixe ; les valeurs passent en paramètres.
    conditions, params = [], []
    if categorie:
        conditions.append("categorie ILIKE %s")
        params.append(_contient(categorie))
    if acheteur:
        conditions.append("acheteur ILIKE %s")
        params.append(_contient(acheteur))
    if statut:
        conditions.append("statut = %s")
        params.append(statut)
    if date_limite_avant:
        conditions.append("date_limite_depot < %s")
        params.append(date_limite_avant)
    if date_limite_apres:
        conditions.append("date_limite_depot >= %s")
        params.append(date_limite_apres)
    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""

    total = conn.execute(f"SELECT count(*) AS n FROM consultations {where}", params).fetchone()["n"]
    rows = conn.execute(
        f"SELECT {_RESUME} FROM consultations {where} ORDER BY date_limite_depot, id LIMIT %s OFFSET %s",
        [*params, limit, offset],
    ).fetchall()
    return PageConsultations(total=total, limit=limit, offset=offset, resultats=rows)


@app.get("/consultations/{org_acronyme}/{ref_consultation}", response_model=Consultation,
         responses={404: {"description": "Consultation introuvable"}})
def detail_consultation(org_acronyme: str, ref_consultation: str, conn: Conn):
    """Toutes les informations d'une consultation (clé du portail : orgAcronyme + refConsultation)."""
    row = conn.execute(
        f"SELECT {_DETAIL} FROM consultations WHERE org_acronyme = %s AND ref_consultation = %s",
        (org_acronyme, ref_consultation),
    ).fetchone()
    if row is None:
        raise _introuvable(org_acronyme, ref_consultation)
    return row


@app.get("/consultations/{org_acronyme}/{ref_consultation}/historique", response_model=list[Modification],
         responses={404: {"description": "Consultation introuvable"}})
def historique_consultation(org_acronyme: str, ref_consultation: str, conn: Conn):
    """Modifications détectées entre deux collectes, de la plus ancienne à la plus récente.

    Liste vide : consultation connue mais jamais modifiée."""
    row = conn.execute(
        "SELECT id FROM consultations WHERE org_acronyme = %s AND ref_consultation = %s",
        (org_acronyme, ref_consultation),
    ).fetchone()
    if row is None:
        raise _introuvable(org_acronyme, ref_consultation)
    return conn.execute(
        "SELECT champ, ancienne_valeur, nouvelle_valeur, type_evenement, detecte_le, run_id"
        " FROM historique_modifications WHERE consultation_id = %s ORDER BY detecte_le, id",
        (row["id"],),
    ).fetchall()


@app.get("/collecte/dernier-run", response_model=DernierRun)
def dernier_run(conn: Conn):
    """Dernier run du collecteur (quel que soit son statut, y compris en cours) et
    date du dernier run réussi. dernier_run vaut null si aucun run n'a encore eu lieu."""
    run = conn.execute(
        "SELECT id, statut, mode, force, demarre_le, termine_le,"
        " extract(epoch FROM termine_le - demarre_le)::int AS duree_secondes,"
        " raison, nb_pages, nb_consultations, nb_ecartees, stats"
        " FROM collecte_runs ORDER BY demarre_le DESC, id DESC LIMIT 1"
    ).fetchone()
    if run is not None:
        stats = run.pop("stats") or {}
        run["erreurs"] = {
            cle.removeprefix("pmmp/"): valeur for cle, valeur in stats.items()
            if cle.startswith("pmmp/") and cle.endswith("_errors") and isinstance(valeur, int)
        }
    succes = conn.execute("SELECT termine_le FROM v_dernier_run_reussi").fetchone()
    return DernierRun(dernier_run=run, dernier_succes_le=succes["termine_le"] if succes else None)
