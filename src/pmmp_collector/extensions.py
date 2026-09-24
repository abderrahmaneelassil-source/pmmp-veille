"""Suivi des exécutions : table collecte_runs + fichiers storage/last_run.json et last_success.json.

Un run qui "se termine" sans avoir extrait la moindre consultation est compté
en échec : c'est le cas typique de panne silencieuse (HTML du portail modifié).
"""
from __future__ import annotations

import json
import logging

from scrapy import signals

from pmmp_collector.config import load_config
from pmmp_collector.middlewares import REASON_REFUSED_WINDOW, REASON_WINDOW_ENDED

logger = logging.getLogger(__name__)

EXIT_CODES = {"succes": 0, "echec": 1, "refuse": 2, "partiel": 3}


def run_status(reason: str, stats: dict) -> str:
    if reason == REASON_REFUSED_WINDOW:
        return "refuse"
    if reason == REASON_WINDOW_ENDED:
        return "partiel"
    if reason != "finished":
        return "echec"
    if not stats.get("pmmp/listing_rows"):
        return "echec"
    if stats.get("pmmp/db_errors") and not stats.get("pmmp/db_upserts"):
        return "echec"
    return "succes"


class RunRecorder:
    def __init__(self, crawler):
        self.crawler = crawler
        self.cfg = load_config()
        self.conn = None
        self.run_id = None

    @classmethod
    def from_crawler(cls, crawler):
        ext = cls(crawler)
        crawler.signals.connect(ext.spider_opened, signal=signals.spider_opened)
        crawler.signals.connect(ext.spider_closed, signal=signals.spider_closed)
        return ext

    def spider_opened(self, spider):
        if not self.cfg.database_url:
            return
        from pmmp_collector import db  # import paresseux : libpq n'est requis qu'avec une base

        self.db = db
        try:
            self.conn = db.connect(self.cfg.database_url, self.cfg.tz.key)
            self.run_id = db.start_run(self.conn, self.cfg.mode, getattr(spider, "force", False))
            spider.run_id = self.run_id
            logger.info("Run n°%s enregistré", self.run_id)
        except self.db.psycopg.Error:
            logger.exception("Impossible d'enregistrer le run en base")

    def spider_closed(self, spider, reason):
        stats = self.crawler.stats.get_stats()
        status = run_status(reason, stats)
        if reason == "finished" and status == "echec":
            reason = "aucune_consultation_extraite" if not stats.get("pmmp/listing_rows") else "erreurs_base"
        spider.run_status = status
        cb_reason = stats.get("pmmp/circuit_breaker/reason")
        summary = {
            "run_id": self.run_id,
            "statut": status,
            "raison": reason,
            "circuit_breaker": cb_reason,
            "termine_le": self.cfg.now().isoformat(),
            "force": getattr(spider, "force", False),
            "mode": self.cfg.mode,
            "pages": stats.get("pmmp/pages", 0),
            "consultations_listees": stats.get("pmmp/listing_rows", 0),
            "consultations_enregistrees": stats.get("pmmp/db_upserts", 0),
            "consultations_ecartees": stats.get("pmmp/items_invalid", 0),
            "dce_telecharges": stats.get("pmmp/dce_downloaded", 0),
        }

        if self.conn is not None:
            try:
                if status == "succes":
                    n = self.db.close_expired(self.conn, self.run_id)
                    summary["passees_en_cloture"] = n
                self.db.finish_run(self.conn, self.run_id, status, cb_reason or reason, stats)
            except self.db.psycopg.Error:
                logger.exception("Impossible de finaliser le run en base")
            finally:
                self.conn.close()

        self._write_json("last_run.json", summary)
        if status == "succes":
            self._write_json("last_success.json", summary)

        log = logger.info if status == "succes" else logger.error
        log("Fin du run : statut=%s raison=%s %s", status, cb_reason or reason, summary)

    def _write_json(self, name: str, data: dict) -> None:
        try:
            path = self.cfg.storage_dir / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(data, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
        except OSError:
            logger.exception("Impossible d'écrire %s", name)
