"""Pipelines : validation Pydantic puis upsert PostgreSQL avec historique."""
from __future__ import annotations

import json
import logging

from pydantic import ValidationError
from scrapy.exceptions import DropItem, NotConfigured

from pmmp_collector.config import load_config
from pmmp_collector.history import compute_changes, derive_statut
from pmmp_collector.models import Consultation

logger = logging.getLogger(__name__)


class ValidationPipeline:
    def __init__(self, stats):
        self.stats = stats

    @classmethod
    def from_crawler(cls, crawler):
        return cls(crawler.stats)

    def process_item(self, item, spider=None):
        try:
            model = Consultation.model_validate(dict(item))
        except ValidationError as exc:
            self.stats.inc_value("pmmp/items_invalid")
            errors = "; ".join(f"{'.'.join(map(str, e['loc']))}: {e['msg']}" for e in exc.errors())
            logger.warning(
                "Consultation écartée %s/%s (%s) : %s",
                item.get("org_acronyme"), item.get("ref_consultation"), item.get("url_detail"), errors,
            )
            raise DropItem(f"invalide : {errors}") from None
        return model.model_dump()


class PostgresPipeline:
    """Upsert ON CONFLICT (org_acronyme, ref_consultation) + historique des modifications.

    En mode test sans PMMP_DATABASE_URL, les items sont écrits en JSONL à la place.
    """

    def __init__(self, crawler):
        self.crawler = crawler
        self.cfg = load_config()
        self.conn = None
        self.jsonl = None

    @classmethod
    def from_crawler(cls, crawler):
        return cls(crawler)

    def open_spider(self, spider=None):
        if not self.cfg.database_url:
            if not self.cfg.is_test:
                raise NotConfigured("PMMP_DATABASE_URL est obligatoire en mode prod")
            path = self.cfg.storage_dir / "test_items.jsonl"
            path.parent.mkdir(parents=True, exist_ok=True)
            self.jsonl = path.open("a", encoding="utf-8")
            logger.warning("Mode test sans base : items écrits dans %s", path)
            return
        from pmmp_collector import db  # import paresseux : libpq n'est requis qu'avec une base

        self.db = db
        self.conn = db.connect(self.cfg.database_url, self.cfg.tz.key)

    def close_spider(self, spider=None):
        if self.conn is not None:
            self.conn.close()
        if self.jsonl is not None:
            self.jsonl.close()

    def process_item(self, item, spider=None):
        stats = self.crawler.stats
        now = self.cfg.now()
        if self.jsonl is not None:
            item["statut"] = derive_statut(item, None, now)
            self.jsonl.write(json.dumps(item, ensure_ascii=False, default=str) + "\n")
            return item

        record = dict(item)
        record["raw_html_detail_path"] = record.get("raw_html_detail")
        try:
            with self.conn.transaction():
                old = self.db.fetch_for_update(self.conn, record["org_acronyme"], record["ref_consultation"])
                record["statut"] = derive_statut(record, old, now)
                changes = compute_changes(old, record)
                cid = self.db.upsert_consultation(self.conn, record)
                self.db.insert_history(self.conn, cid, changes, getattr(self.crawler.spider, "run_id", None))
        except self.db.psycopg.Error:
            stats.inc_value("pmmp/db_errors")
            logger.exception(
                "Erreur PostgreSQL pour %s/%s : item ignoré, le run continue",
                record["org_acronyme"], record["ref_consultation"],
            )
            if self.conn.closed:
                self.conn = self.db.connect(self.cfg.database_url, self.cfg.tz.key)
            raise DropItem("erreur base de données") from None

        stats.inc_value("pmmp/db_upserts")
        if old is None:
            stats.inc_value("pmmp/db_new")
        if changes:
            stats.inc_value("pmmp/history_rows", len(changes))
            logger.info(
                "%s/%s : %s", record["org_acronyme"], record["ref_consultation"],
                ", ".join(f"{c.champ} ({c.type_evenement})" for c in changes),
            )
        item["statut"] = record["statut"]
        return item
