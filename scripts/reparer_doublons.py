"""Répare en base les textes doublés par l'ancien extracteur, à partir des pages archivées.

Jusqu'au 26/09/2026, l'extracteur lisait à la fois le texte visible du portail et son
info-bulle cachée : « SALE SALE » pour le lieu d'exécution, « début ... texte complet »
pour l'objet lu sur la liste (voir parsers.value_text). Les consultations déjà en base
ne sont pas relues par la collecte incrémentale tant que rien ne change sur le portail :
ce script relit leurs pages archivées (storage/raw_html) avec l'extracteur corrigé.

- Aucune requête au portail : uniquement les pages déjà sur le disque.
- Fiche détail archivée (raw_html_detail_path) si elle existe, sinon la ligne de la page
  de liste archivée la plus récente (consultations dont la fiche a échoué).
- Seuls objet et lieu_execution sont corrigés, et seulement si la nouvelle valeur est
  non vide. Pas de ligne d'historique : c'est la correction d'une erreur de lecture,
  pas une modification publiée sur le portail.

À lancer depuis la racine du projet, avec le python du .venv :
    python scripts/reparer_doublons.py              # simulation : affiche les changements
    python scripts/reparer_doublons.py --appliquer  # écrit en base (une seule transaction)
Faire une sauvegarde avant d'appliquer (scripts/backup_db.ps1).
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from parsel import Selector

from pmmp_collector import db
from pmmp_collector.config import load_config
from pmmp_collector.parsers import parse_detail_page, parse_listing_page

CHAMPS = ("objet", "lieu_execution")
URL_FICTIVE = "https://www.marchespublics.gov.ma/index.php"  # sert seulement à résoudre les liens


def lire(path: Path) -> Selector:
    return Selector(text=path.read_bytes().decode("utf-8", errors="replace"))


def lignes_de_liste(storage: Path) -> dict[tuple[str, str], dict]:
    """(org, ref) -> ligne extraite, en privilégiant les pages de liste les plus récentes."""
    lignes: dict[tuple[str, str], dict] = {}
    for page in sorted(storage.glob("raw_html/*/liste/*.html"), reverse=True):
        for row in parse_listing_page(lire(page), URL_FICTIVE)["rows"]:
            lignes.setdefault((row["org_acronyme"], row["ref_consultation"]), row)
    return lignes


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--appliquer", action="store_true", help="écrire en base (sinon simulation)")
    args = parser.parse_args()

    cfg = load_config()
    liste = None
    corrections: list[tuple[int, str, str, str, str]] = []
    with db.connect(cfg.database_url, cfg.tz.key) as conn:
        rows = conn.execute(
            "SELECT id, org_acronyme, ref_consultation, objet, lieu_execution, raw_html_detail_path "
            "FROM consultations ORDER BY id"
        ).fetchall()
        for r in rows:
            cle = (r["org_acronyme"], r["ref_consultation"])
            chemin = Path(r["raw_html_detail_path"]) if r["raw_html_detail_path"] else None
            if chemin and chemin.exists():
                source, relu = f"fiche {chemin.name}", parse_detail_page(lire(chemin), URL_FICTIVE)
            else:
                liste = liste if liste is not None else lignes_de_liste(cfg.storage_dir)
                if cle not in liste:
                    print(f"  {cle[0]}/{cle[1]} : aucune page archivée, non traitée")
                    continue
                source, relu = "page de liste archivée", liste[cle]
            for champ in CHAMPS:
                nouveau = relu.get(champ)
                if nouveau and nouveau != r[champ]:
                    corrections.append((r["id"], champ, r[champ], nouveau, f"{cle[0]}/{cle[1]} ({source})"))

        print(f"{len(rows)} consultations lues, {len(corrections)} valeur(s) à corriger.")
        for _, champ, avant, apres, qui in corrections:
            print(f"- {qui} {champ} :\n    avant « {avant[:110]} »\n    après « {apres[:110]} »")
        if not corrections or not args.appliquer:
            if corrections:
                print("\nSimulation : rien n'a été écrit. Relancer avec --appliquer pour corriger.")
            return 0
        with conn.transaction():
            for id_, champ, _, apres, _ in corrections:
                conn.execute(f"UPDATE consultations SET {champ} = %s WHERE id = %s", (apres, id_))
        print(f"\n{len(corrections)} valeur(s) corrigée(s) en base.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
