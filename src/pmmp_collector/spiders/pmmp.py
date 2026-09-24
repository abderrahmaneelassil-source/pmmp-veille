"""Spider PMMP : liste paginée (postbacks PRADO) -> fiche détail -> DCE.

Ordre de parcours : toutes les pages de liste d'abord (chaque postback PRADO
rejoue l'état de la page précédente, sans requête intercalée), puis les fiches
détail, puis les DCE.
"""
from __future__ import annotations

import logging
from datetime import datetime
from urllib.parse import urljoin

import scrapy
from scrapy.exceptions import CloseSpider, IgnoreRequest
from scrapy.http import FormRequest
from scrapy.spidermiddlewares.httperror import HttpError

from pmmp_collector.config import load_config
from pmmp_collector.parsers import (
    PAGESTATE_FIELD,
    find_search_button,
    form_fields,
    looks_like_captcha,
    merge_listing_detail,
    parse_detail_page,
    parse_listing_page,
)
from pmmp_collector.storage import DceStore, HtmlArchiver, consultation_key, filename_from_response

logger = logging.getLogger(__name__)

PRIORITY_LISTING = 10
PRIORITY_DETAIL = 0
PRIORITY_DCE = -5


def _truthy(value) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes", "oui", "on"}


def _int_or(value, default: int) -> int:
    return int(value) if value not in (None, "") else default


def _cancelled_by_us(failure) -> bool:
    """Requête annulée par nos middlewares (circuit breaker, fenêtre horaire) : rien à signaler.

    HttpError (réponse 404, 500...) hérite aussi d'IgnoreRequest : c'est une vraie erreur."""
    return bool(failure.check(IgnoreRequest)) and not failure.check(HttpError)


class PmmpSpider(scrapy.Spider):
    name = "pmmp"

    def __init__(self, force=False, max_pages=None, max_items=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.cfg = load_config()
        self.force = _truthy(force)
        self.max_pages = _int_or(max_pages, self.cfg.max_pages)
        self.max_items = _int_or(max_items, self.cfg.max_items)
        if self.force and not self.cfg.in_window():
            # --force sert aux tests manuels : jamais un crawl complet en journée.
            self.max_pages = min(self.max_pages or self.cfg.force_max_pages, self.cfg.force_max_pages)
            self.max_items = min(self.max_items or self.cfg.force_max_items, self.cfg.force_max_items)
            logger.warning(
                "Run forcé hors fenêtre horaire : limité à %d page(s) et %d consultation(s).",
                self.max_pages, self.max_items,
            )
        run_stamp = datetime.now(self.cfg.tz).strftime("%Y%m%d_%H%M%S")
        self.archiver = HtmlArchiver(
            self.cfg.storage_dir / "raw_html",
            run_stamp,
            fixtures_dir=self.cfg.fixtures_dir / "live" if self.cfg.is_test else None,
        )
        self.dce_store = DceStore(self.cfg.storage_dir / "dce")
        self.items_scheduled = 0
        self.pending_details: list[scrapy.Request] = []
        self.dce_blocked_reason: str | None = None
        self._previous_page_keys: set | None = None

    # --- Démarrage ---------------------------------------------------------------

    def start_requests(self):
        url = urljoin(self.cfg.base_url, self.cfg.search_path)
        logger.info("Démarrage du crawl sur %s (mode=%s, force=%s)", url, self.cfg.mode, self.force)
        yield scrapy.Request(
            url, callback=self.parse_search_form, errback=self.listing_failed, priority=PRIORITY_LISTING,
        )

    async def start(self):  # Scrapy >= 2.13
        for request in self.start_requests():
            yield request

    def parse_search_form(self, response):
        """Le portail redirige vers le formulaire de recherche avancée. Ses valeurs par
        défaut (annonces de consultation, date limite à venir) correspondent aux
        consultations en cours : on le soumet tel quel, comme un clic sur
        « Lancer la recherche »."""
        if parse_listing_page(response.selector, response.url)["rows"]:
            yield from self.parse_listing(response, page=1)
            return
        raw = self.archiver.save(response, "recherche", "formulaire")
        button = find_search_button(response.selector)
        if button is None:
            logger.error(
                "Ni résultats ni bouton « Lancer la recherche » sur %s : vérifier PMMP_BASE_URL / "
                "PMMP_SEARCH_PATH. HTML : %s", response.url, raw,
            )
            return
        name, value = button
        action, formdata = form_fields(response.selector, response.url)
        formdata.update({"PRADO_POSTBACK_TARGET": name, "PRADO_POSTBACK_PARAMETER": "", name: value})
        logger.info("Soumission du formulaire de recherche (%s)", name)
        yield FormRequest(
            action, formdata=formdata, callback=self.parse_listing, errback=self.listing_failed,
            cb_kwargs={"page": 1}, priority=PRIORITY_LISTING,
        )

    # --- Liste -------------------------------------------------------------------

    def parse_listing(self, response, page: int):
        """Une page de liste. Les fiches détail sont mises de côté et libérées
        seulement quand la pagination est terminée : aucune requête ne s'intercale
        entre deux postbacks PRADO."""
        raw = self.archiver.save(response, "liste", f"page{page:04d}")
        self.crawler.stats.inc_value("pmmp/pages")
        try:
            data = parse_listing_page(response.selector, response.url)
        except Exception:
            logger.exception("Erreur de parsing de la page de liste %d (%s) — HTML archivé : %s", page, response.url, raw)
            self.crawler.stats.inc_value("pmmp/parse_errors")
            yield from self._release_details()
            return

        rows = data["rows"]
        self.crawler.stats.inc_value("pmmp/listing_rows", len(rows))
        if data["captcha"]:
            raise CloseSpider("captcha_detecte")
        if not rows:
            if not data["pager"]["pagestate"]:
                logger.error(
                    "Page %d (%s) : ni consultation ni formulaire PRADO — ce n'est pas une page de résultats. "
                    "Vérifier PMMP_BASE_URL / PMMP_SEARCH_PATH. HTML : %s", page, response.url, raw,
                )
            else:
                logger.warning("Page %d : aucune consultation trouvée (structure HTML changée ?). HTML : %s", page, raw)
            yield from self._release_details()
            return

        keys = {(r["org_acronyme"], r["ref_consultation"]) for r in rows}
        if keys == self._previous_page_keys:
            logger.error("Page %d identique à la précédente : pagination PRADO non prise en compte, arrêt.", page)
            yield from self._release_details()
            return
        self._previous_page_keys = keys

        for row in rows:
            if self.max_items and self.items_scheduled >= self.max_items:
                break
            if not (row["url_detail"] and row["org_acronyme"] and row["ref_consultation"]):
                logger.warning("Ligne ignorée (lien détail ou clé absente) page %d : %r", page, row.get("objet"))
                self.crawler.stats.inc_value("pmmp/rows_without_key")
                continue
            self.items_scheduled += 1
            row["raw_html_liste"] = str(raw) if raw else None
            self.pending_details.append(scrapy.Request(
                row["url_detail"], callback=self.parse_detail, errback=self.detail_failed,
                cb_kwargs={"listing": row}, priority=PRIORITY_DETAIL,
            ))

        next_request = self._next_page_request(response, data["pager"], page)
        if next_request is not None:
            yield next_request
        else:
            yield from self._release_details()

    def _release_details(self):
        logger.info("Pagination terminée : %d fiche(s) détail à visiter.", len(self.pending_details))
        pending, self.pending_details = self.pending_details, []
        yield from pending

    def _next_page_request(self, response, pager: dict, page: int):
        if self.max_items and self.items_scheduled >= self.max_items:
            logger.info("Limite de %d consultations atteinte : fin de la pagination.", self.max_items)
            return None
        if self.max_pages and page >= self.max_pages:
            logger.info("Limite de %d page(s) atteinte : fin de la pagination.", self.max_pages)
            return None
        total = pager["total_pages"]
        if total is not None and page >= total:
            logger.info("Dernière page atteinte (%d/%d).", page, total)
            return None
        if not pager["pagestate"]:
            logger.error("%s absent de la page %d : pagination impossible.", PAGESTATE_FIELD, page)
            self.crawler.stats.inc_value("pmmp/pagination_errors")
            return None
        if not pager["page_input_name"]:
            logger.warning("Contrôle de pagination introuvable page %d : arrêt après cette page.", page)
            self.crawler.stats.inc_value("pmmp/pagination_errors")
            return None

        # Postback PRADO : on renvoie le formulaire tel que reçu (champs cachés
        # compris) avec le PRADO_PAGESTATE de CETTE réponse et la page suivante.
        action, formdata = form_fields(response.selector, response.url)
        formdata.update({
            PAGESTATE_FIELD: pager["pagestate"],
            "PRADO_POSTBACK_TARGET": pager["postback_target"],
            "PRADO_POSTBACK_PARAMETER": "",
            pager["page_input_name"]: str(page + 1),
        })
        return FormRequest(
            action,
            formdata=formdata,
            callback=self.parse_listing,
            errback=self.listing_failed,
            cb_kwargs={"page": page + 1},
            priority=PRIORITY_LISTING,
        )

    def listing_failed(self, failure):
        if _cancelled_by_us(failure):
            return
        self.crawler.stats.inc_value("pmmp/listing_errors")
        logger.error("Échec de la page de liste %s : %r", failure.request.url, failure.value)
        yield from self._release_details()

    # --- Fiche détail ------------------------------------------------------------

    def parse_detail(self, response, listing: dict):
        org, ref = listing["org_acronyme"], listing["ref_consultation"]
        raw = self.archiver.save(response, "detail", consultation_key(org, ref))
        try:
            detail = parse_detail_page(response.selector, response.url)
        except Exception:
            logger.exception("Erreur de parsing de la fiche %s/%s — HTML archivé : %s", org, ref, raw)
            self.crawler.stats.inc_value("pmmp/parse_errors")
            detail = {}

        item = merge_listing_detail(listing, detail)
        item["raw_html_detail"] = str(raw) if raw else None
        item["dce_paths"] = []
        links = item.get("dce_urls") or []

        if not self.cfg.download_dce:
            item["dce_statut"] = "desactive"
        elif not links:
            item["dce_statut"] = "aucun_lien"
        elif existing := self.dce_store.existing(org, ref):
            item["dce_paths"], item["dce_statut"] = existing, "deja_present"
        elif self.dce_blocked_reason:
            item["dce_statut"] = self.dce_blocked_reason
        else:
            yield self._dce_request(item, links, index=1)
            return
        yield item

    def detail_failed(self, failure):
        if _cancelled_by_us(failure):
            return
        self.crawler.stats.inc_value("pmmp/detail_errors")
        listing = failure.request.cb_kwargs.get("listing", {})
        logger.error("Échec de la fiche détail %s : %r", failure.request.url, failure.value)
        # On garde au moins les données de la liste (validées ensuite comme les autres).
        yield {**listing, "dce_paths": [], "dce_statut": "echec_fiche_detail"}

    # --- DCE ---------------------------------------------------------------------

    def _dce_request(self, item: dict, remaining: list[str], index: int):
        return scrapy.Request(
            remaining[0], callback=self.save_dce, errback=self.dce_failed,
            cb_kwargs={"item": item, "remaining": remaining[1:], "index": index},
            meta={"dce_download": True}, priority=PRIORITY_DCE,
            dont_filter=True,  # sinon un doublon filtré ferait perdre l'item
        )

    def _continue_dce(self, item: dict, remaining: list[str], index: int):
        if remaining and not self.dce_blocked_reason:
            yield self._dce_request(item, remaining, index + 1)
        else:
            yield item

    def save_dce(self, response, item: dict, remaining: list[str], index: int):
        org, ref = item["org_acronyme"], item["ref_consultation"]
        ctype = (response.headers.get("Content-Type") or b"").decode("latin-1").lower()
        looks_html = response.body.lstrip()[:15].lower().startswith((b"<!doctype", b"<html"))
        is_html = "text/html" in ctype or (not ctype and looks_html)
        is_file = bool(response.headers.get("Content-Disposition")) or not is_html

        if is_file:
            try:
                path = self.dce_store.save(org, ref, filename_from_response(response, index), response.body)
                item["dce_paths"].append(str(path))
                item["dce_statut"] = "telecharge"
                self.crawler.stats.inc_value("pmmp/dce_downloaded")
                logger.info("DCE enregistré : %s", path)
            except OSError:
                logger.exception("Impossible d'écrire le DCE de %s/%s", org, ref)
                item.setdefault("dce_statut", "echec")
        else:
            # Page HTML intermédiaire (formulaire, conditions, identification…) :
            # archivée pour analyse, jamais soumise automatiquement.
            raw = self.archiver.save(response, "dce_intermediaire", f"{consultation_key(org, ref)}_{index}")
            if looks_like_captcha(response.text):
                self.dce_blocked_reason = "captcha"
                logger.warning(
                    "Captcha sur la page DCE de %s/%s : téléchargements DCE suspendus pour ce run "
                    "(aucun contournement). HTML : %s", org, ref, raw,
                )
                item["dce_statut"] = "captcha"
            elif item.get("dce_statut") != "telecharge":
                item["dce_statut"] = "page_intermediaire"
                logger.info("DCE %s/%s : page intermédiaire, non soumise (HTML : %s)", org, ref, raw)
        yield from self._continue_dce(item, remaining, index)

    def dce_failed(self, failure):
        if _cancelled_by_us(failure):
            return
        kw = failure.request.cb_kwargs
        item = kw["item"]
        self.crawler.stats.inc_value("pmmp/dce_errors")
        logger.error("Échec du téléchargement DCE %s : %r", failure.request.url, failure.value)
        if item.get("dce_statut") != "telecharge":
            item["dce_statut"] = "echec"
        yield from self._continue_dce(item, kw["remaining"], kw["index"])
