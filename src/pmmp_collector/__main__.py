"""Ligne de commande : python -m pmmp_collector {crawl,init-db,status}

Codes de sortie de `crawl` : 0 succès, 1 échec, 2 refusé (hors fenêtre), 3 partiel.
"""
from __future__ import annotations

import argparse
import os
import sys

os.environ.setdefault("SCRAPY_SETTINGS_MODULE", "pmmp_collector.settings")

from pmmp_collector.config import ConfigError, load_config  # noqa: E402


def check_database(cfg) -> str | None:
    """Message d'erreur si la base n'est pas utilisable, sinon None.

    Vérifié avant de lancer Scrapy : sinon l'erreur survient dans open_spider et
    se termine en traces Twisted illisibles."""
    if not cfg.database_url:
        if cfg.is_test:
            return None  # mode test sans base : items écrits dans storage/test_items.jsonl
        return "PMMP_DATABASE_URL est obligatoire en mode prod (voir .env)."
    from pmmp_collector import db

    try:
        with db.connect(cfg.database_url, cfg.tz.key) as conn:
            conn.execute("SELECT 1 FROM consultations LIMIT 1")
    except db.psycopg.errors.UndefinedTable:
        return "les tables n'existent pas : appliquer d'abord db/schema.sql (README §4.3)."
    except db.psycopg.Error as exc:
        return f"connexion PostgreSQL impossible, vérifier PMMP_DATABASE_URL dans .env : {exc}"
    return None


def cmd_crawl(args) -> int:
    cfg = load_config()
    if not cfg.in_window() and not args.force:
        print(
            f"REFUS : il est {cfg.now():%H:%M} ({cfg.tz.key}), hors de la fenêtre autorisée "
            f"{cfg.window_spec}. Le crawl complet ne tourne qu'en heures creuses.\n"
            f"Pour un test manuel limité ({cfg.force_max_pages} page(s), {cfg.force_max_items} consultations) : --force",
            file=sys.stderr,
        )
        return 2
    problem = check_database(cfg)
    if problem:
        print(f"ÉCHEC avant démarrage (aucune requête envoyée au portail) : {problem}", file=sys.stderr)
        return 1

    from scrapy.crawler import CrawlerProcess
    from scrapy.utils.project import get_project_settings

    from pmmp_collector.extensions import EXIT_CODES
    from pmmp_collector.spiders.pmmp import PmmpSpider

    process = CrawlerProcess(get_project_settings())
    crawler = process.create_crawler(PmmpSpider)
    process.crawl(
        crawler,
        force="1" if args.force else "0",
        max_pages=args.max_pages if args.max_pages is not None else "",
        max_items=args.max_items if args.max_items is not None else "",
    )
    process.start()
    status = getattr(crawler.spider, "run_status", "echec") if crawler.spider else "echec"
    return EXIT_CODES.get(status, 1)


def cmd_init_db(args) -> int:
    from pmmp_collector import db

    cfg = load_config()
    if not cfg.database_url:
        print("PMMP_DATABASE_URL n'est pas renseignée.", file=sys.stderr)
        return 1
    try:
        with db.connect(cfg.database_url, cfg.tz.key) as conn:
            db.init_schema(conn)
    except db.psycopg.errors.InsufficientPrivilege as exc:
        print(
            f"Droits insuffisants ({exc.diag.message_primary}). Le compte applicatif (pmmp_app) ne peut "
            "pas modifier le schéma : l'appliquer en superutilisateur, voir README §4.3.",
            file=sys.stderr,
        )
        return 1
    except db.psycopg.Error as exc:
        print(f"Connexion PostgreSQL impossible, vérifier PMMP_DATABASE_URL dans .env : {exc}", file=sys.stderr)
        return 1
    print("Schéma appliqué.")
    return 0


def cmd_status(args) -> int:
    cfg = load_config()
    print(f"Heure locale : {cfg.now():%Y-%m-%d %H:%M} ({cfg.tz.key})")
    print(f"Fenêtre autorisée : {cfg.window_spec} -> {'OUVERTE' if cfg.in_window() else 'fermée'}")
    for name in ("last_success.json", "last_run.json"):
        path = cfg.storage_dir / name
        print(f"\n{name} :\n" + (path.read_text(encoding="utf-8") if path.exists() else "  (aucun)"))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="pmmp_collector", description="Collecteur de veille PMMP (TACHFIR)")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("crawl", help="lancer une collecte")
    p.add_argument("--force", action="store_true",
                   help="autoriser un test manuel hors fenêtre horaire (run plafonné)")
    p.add_argument("--max-pages", type=int, default=None)
    p.add_argument("--max-items", type=int, default=None)
    p.set_defaults(func=cmd_crawl)

    sub.add_parser("init-db", help="appliquer db/schema.sql").set_defaults(func=cmd_init_db)
    sub.add_parser("status", help="fenêtre horaire et dernier run").set_defaults(func=cmd_status)

    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except ConfigError as exc:
        print(f"Configuration invalide : {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
