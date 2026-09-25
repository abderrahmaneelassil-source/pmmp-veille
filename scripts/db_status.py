"""Script de diagnostic ponctuel : etat reel de la base pmmp_veille.
A executer depuis la racine du projet (cwd) avec le python du venv du projet.
Ecrit son resultat dans scripts/db_status_output.txt (a cote de ce script).
"""
from __future__ import annotations

import sys
import traceback
from pathlib import Path

out = []

try:
    from pmmp_collector.config import load_config
    from pmmp_collector import db

    cfg = load_config()
    out.append(f"Heure locale au moment du diagnostic : {cfg.now():%Y-%m-%d %H:%M:%S} ({cfg.tz.key})")
    out.append(f"PMMP_DATABASE_URL (hote/base, sans mot de passe) : "
               f"{cfg.database_url.split('@')[-1] if '@' in cfg.database_url else '(non definie)'}")
    out.append("")

    with db.connect(cfg.database_url, cfg.tz.key) as conn:
        out.append("=== Comptes de lignes ===")
        for table in ("consultations", "historique_modifications", "collecte_runs"):
            n = conn.execute(f"SELECT count(*) AS n FROM {table}").fetchone()["n"]
            out.append(f"{table} : {n}")

        out.append("")
        out.append("=== 10 derniers runs (collecte_runs, id desc) ===")
        rows = conn.execute(
            "SELECT id, mode, force, statut, raison, "
            "to_char(demarre_le, 'YYYY-MM-DD HH24:MI:SS') AS demarre_le, "
            "to_char(termine_le, 'YYYY-MM-DD HH24:MI:SS') AS termine_le, "
            "nb_pages, nb_consultations, nb_ecartees "
            "FROM collecte_runs ORDER BY id DESC LIMIT 10"
        ).fetchall()
        if rows:
            for r in rows:
                out.append(str(r))
        else:
            out.append("(aucune ligne)")

        out.append("")
        out.append("=== Dernier run reussi (db.last_success) ===")
        ls = db.last_success(conn)
        out.append(str(ls) if ls else "(aucun run reussi)")

except Exception:
    out.append("ERREUR pendant le diagnostic :")
    out.append(traceback.format_exc())

script_dir = Path(__file__).resolve().parent
(script_dir / "db_status_output.txt").write_text("\n".join(out), encoding="utf-8")
print("Termine. Voir scripts/db_status_output.txt")
