"""Modèle Pydantic de validation d'une consultation avant insertion en base."""
from __future__ import annotations

import re
import unicodedata
from datetime import datetime
from typing import Literal
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict, Field, field_validator

TZ = ZoneInfo("Africa/Casablanca")

Statut = Literal["en_cours", "cloture", "annule", "reporte"]

# Chiffres arabes-indiens -> chiffres occidentaux (dates parfois saisies ainsi).
_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")
_FR_DATE = re.compile(r"(\d{1,2})/(\d{1,2})/(\d{4})(?:\s*(?:à|a)?\s*(\d{1,2})\s*[:hH]\s*(\d{2}))?")
_TRUE = {"oui", "o", "yes", "true", "1", "obligatoire", "exigée", "exigee"}
_FALSE = {"non", "n", "no", "false", "0", "autorisée", "autorisee", "refusée", "refusee", "facultative"}


def clean_text(value):
    if value is None:
        return None
    value = unicodedata.normalize("NFC", str(value)).replace("\xa0", " ")
    value = re.sub(r"\s+", " ", value).strip()
    return value or None


def parse_datetime(value) -> datetime | None:
    """'12/10/2026 10:00' ou ISO -> datetime aware Africa/Casablanca."""
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=TZ)
    text = str(value).translate(_DIGITS).strip()
    m = _FR_DATE.search(text)
    if m:
        d, mo, y, h, mi = m.groups()
        return datetime(int(y), int(mo), int(d), int(h or 0), int(mi or 0), tzinfo=TZ)
    try:
        dt = datetime.fromisoformat(text)
    except ValueError as exc:
        raise ValueError(f"date illisible : {value!r}") from exc
    return dt if dt.tzinfo else dt.replace(tzinfo=TZ)


class Consultation(BaseModel):
    model_config = ConfigDict(extra="ignore")

    # Clé naturelle (paramètres orgAcronyme / refConsultation de l'URL du portail)
    org_acronyme: str = Field(min_length=1, max_length=64)
    ref_consultation: str = Field(min_length=1, max_length=128)

    reference: str | None = None
    objet: str = Field(min_length=3)
    acheteur: str = Field(min_length=2)
    categorie: str | None = None
    type_procedure: str | None = None
    lieu_execution: str | None = None
    date_publication: datetime | None = None
    date_limite_depot: datetime
    reservation_pme: bool | None = None
    reponse_electronique: bool | None = None
    statut_portail: Statut | None = None
    resultat: str | None = None

    url_detail: str = Field(min_length=10)
    dce_urls: list[str] = Field(default_factory=list)
    dce_paths: list[str] = Field(default_factory=list)
    dce_statut: str | None = None
    raw_html_liste: str | None = None
    raw_html_detail: str | None = None

    @field_validator(
        "org_acronyme", "ref_consultation", "reference", "objet", "acheteur", "categorie",
        "type_procedure", "lieu_execution", "resultat", "url_detail", mode="before",
    )
    @classmethod
    def _clean(cls, v):
        return clean_text(v)

    @field_validator("date_publication", "date_limite_depot", mode="before")
    @classmethod
    def _dates(cls, v):
        return parse_datetime(v)

    @field_validator("date_publication", "date_limite_depot")
    @classmethod
    def _plausible(cls, v):
        if v is not None and not 2000 <= v.year <= 2100:
            raise ValueError(f"année invraisemblable : {v.year}")
        return v

    @field_validator("reservation_pme", "reponse_electronique", mode="before")
    @classmethod
    def _bool(cls, v):
        if v is None or isinstance(v, bool):
            return v
        s = clean_text(v)
        if s is None:
            return None
        s = s.lower()
        if s in _TRUE:
            return True
        if s in _FALSE:
            return False
        raise ValueError(f"valeur oui/non illisible : {v!r}")
