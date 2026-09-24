"""Extraction des champs depuis le HTML du PMMP (fonctions pures, testables hors ligne).

Le portail (Atexo MPE / PRADO) n'a pas de classes CSS stables pour tous les champs.
L'extraction s'appuie donc d'abord sur les libellés visibles ("Objet :",
"Acheteur public :", ...) puis sur quelques ids/classes connus en secours.

!! Les sélecteurs doivent être validés sur des pages réelles capturées en mode
test (fixtures/live/). Tout est regroupé ici pour n'avoir qu'un fichier à ajuster.
"""
from __future__ import annotations

import re
import unicodedata
from urllib.parse import parse_qs, urljoin, urlparse

from parsel import Selector

DETAIL_HREF_MARKER = "EntrepriseDetailsConsultation"
PAGESTATE_FIELD = "PRADO_PAGESTATE"

DATE_RE = re.compile(r"(\d{1,2})/(\d{1,2})/(\d{4})(?:\s*(?:à|a)?\s*(\d{1,2})\s*[:hH]\s*(\d{2}))?")

# Éléments susceptibles de porter un libellé "Champ :".
LABEL_XPATH = (
    ".//*[self::strong or self::b or self::label or self::th or self::dt "
    "or contains(@class,'intitule') or contains(@class,'label')]"
)


# --- Utilitaires texte ----------------------------------------------------------

def norm_text(value: str | None) -> str:
    if not value:
        return ""
    value = unicodedata.normalize("NFC", value).replace("\xa0", " ")
    return re.sub(r"\s+", " ", value).strip()


def fold(value: str) -> str:
    """Forme de comparaison : minuscules, sans accents ni ponctuation."""
    value = unicodedata.normalize("NFKD", value.lower())
    value = "".join(c for c in value if not unicodedata.combining(c))
    return re.sub(r"[^\w]+", " ", value).strip()


def node_text(sel) -> str:
    return norm_text(" ".join(sel.xpath(".//text()[not(ancestor::script) and not(ancestor::style)]").getall()))


def first_date(text: str | None) -> str | None:
    m = DATE_RE.search(text or "")
    return m.group(0) if m else None


def all_dates(text: str | None) -> list[str]:
    return [m.group(0) for m in DATE_RE.finditer(text or "")]


# --- Libellés -------------------------------------------------------------------

def _is_label(sel) -> bool:
    txt = node_text(sel)
    if not txt or len(txt) > 80:
        return False
    if txt.endswith(":"):
        return True
    cls = sel.attrib.get("class", "")
    if "intitule" in cls:
        return True
    nxt = sel.xpath("following-sibling::node()[1][self::text()]").get()
    return bool(nxt and nxt.strip().startswith(":"))


def extract_labelled(scope) -> dict[str, str]:
    """{libellé normalisé: valeur} pour les paires "Libellé : valeur" du bloc."""
    out: dict[str, str] = {}
    labels = [lab for lab in scope.xpath(LABEL_XPATH) if _is_label(lab)]
    for lab in labels:
        ltxt = node_text(lab)
        key = fold(ltxt.rstrip(": "))
        if not key or key in out:
            continue
        value = ""
        parent = lab.xpath("..")
        if parent and len([x for x in parent[0].xpath(LABEL_XPATH) if _is_label(x)]) == 1:
            ptxt = node_text(parent[0])
            value = ptxt[len(ltxt):] if ptxt.startswith(ltxt) else ptxt.replace(ltxt, "", 1)
        if not value.strip(" :"):
            sib = lab.xpath("following-sibling::*[1]")
            if sib and not _is_label(sib[0]):
                value = node_text(sib[0])
        value = norm_text(value).lstrip(": ").strip()
        if value:
            out[key] = value
    return out


def pick(labelled: dict[str, str], *keys: str) -> str | None:
    folded = [fold(k) for k in keys]
    for k in folded:
        if labelled.get(k):
            return labelled[k]
    for k in folded:
        for lk, v in labelled.items():
            if lk.startswith(k) and v:
                return v
    return None


# --- Interprétations métier -----------------------------------------------------

_REP_ELEC_RE = re.compile(
    r"reponse electronique\s*(?:est\s*)?(obligatoire|exigee|autorisee|facultative|refusee|interdite|oui|non)"
)
_PME_TRUE_RE = re.compile(r"reserve\w*\s+(?:aux\s+|a\s+la\s+|au\s+)?(?:pme|petites et moyennes)")
_PME_LABEL_RE = re.compile(r"(?:reserve\w*\s+)?pme\s+(oui|non)")
_ANNUL_RE = re.compile(r"\b(avis d annulation|consultation annulee|annulation de la consultation|statut annulee?)\b")
_REPORT_RE = re.compile(r"\b(avis de report|report de la date|consultation reportee|statut reportee?)\b")


def interpret_reponse_electronique(text: str) -> bool | None:
    """Réponse électronique EXIGÉE (obligatoire) -> True ; autorisée/refusée -> False."""
    m = _REP_ELEC_RE.search(fold(text))
    if not m:
        return None
    return m.group(1) in {"obligatoire", "exigee", "oui"}


def interpret_pme(text: str) -> bool | None:
    f = fold(text)
    m = _PME_LABEL_RE.search(f)
    if m:
        return m.group(1) == "oui"
    if _PME_TRUE_RE.search(f):
        return True
    return None


def interpret_statut(text: str) -> str | None:
    f = fold(text)
    if _ANNUL_RE.search(f):
        return "annule"
    if _REPORT_RE.search(f):
        return "reporte"
    return None


def looks_like_captcha(text: str) -> bool:
    t = (text or "").lower()
    return any(k in t for k in ("captcha", "g-recaptcha", "hcaptcha"))


def _query_params(url: str) -> dict[str, str]:
    return {k.lower(): v[0] for k, v in parse_qs(urlparse(url).query).items() if v}


def _hints(scope) -> str:
    """Texte visible + title/alt des icônes (le portail signale certains attributs par des pictos)."""
    return " ".join([node_text(scope), *scope.xpath(".//@title | .//@alt").getall()])


# --- Page de liste --------------------------------------------------------------

def parse_listing_row(row, page_url: str) -> dict:
    href = row.xpath(f".//a[contains(@href,'{DETAIL_HREF_MARKER}')]/@href").get()
    url_detail = urljoin(page_url, href) if href else None
    params = _query_params(url_detail or "")
    lab = extract_labelled(row)
    hints = _hints(row)

    def by_id(fragment: str) -> str | None:
        node = row.xpath(f".//*[contains(@id,'{fragment}')]")
        if not node:
            return None
        txt = node_text(node[0])
        return re.sub(r"^[^:]{1,40}:\s*", "", txt) if ":" in txt[:40] else (txt or None)

    dl_node = row.xpath(".//*[contains(@class,'dateEnd') or contains(@class,'cloture')]")
    date_limite = first_date(node_text(dl_node[0])) if dl_node else None
    dates = all_dates(node_text(row))
    if not date_limite and dates:
        date_limite = dates[-1]
    pub_node = row.xpath(".//*[contains(@class,'date-min') or contains(@class,'publication')]")
    date_publication = pick(lab, "date de publication", "date de mise en ligne")
    date_publication = first_date(date_publication) or (first_date(node_text(pub_node[0])) if pub_node else None)
    if not date_publication and len(dates) >= 2 and dates[0] != date_limite:
        date_publication = dates[0]

    categorie = pick(lab, "categorie principale", "categorie")
    if not categorie:
        for txt in row.xpath(".//text()").getall():
            if fold(txt) in {"travaux", "fournitures", "services"}:
                categorie = norm_text(txt)
                break

    return {
        "org_acronyme": params.get("orgacronyme"),
        "ref_consultation": params.get("refconsultation") or params.get("id"),
        "reference": norm_text(row.xpath(".//*[contains(@class,'ref')]//text()").get()) or pick(lab, "reference"),
        "objet": pick(lab, "objet") or by_id("Objet"),
        "acheteur": pick(lab, "acheteur public", "acheteur", "entite publique", "organisme") or by_id("Denomination"),
        "categorie": categorie,
        "type_procedure": pick(lab, "procedure", "type de procedure")
        or norm_text(row.xpath(".//*[contains(@class,'line-info-bulle')]/text()").get()) or None,
        "lieu_execution": pick(lab, "lieu d execution", "lieux d execution") or by_id("LieuxExec"),
        "date_publication": date_publication,
        "date_limite_depot": date_limite,
        "reservation_pme": interpret_pme(hints),
        "reponse_electronique": interpret_reponse_electronique(hints),
        "statut_portail": interpret_statut(hints),
        "url_detail": url_detail,
    }


def parse_pager(sel: Selector) -> dict:
    """État de pagination PRADO : PRADO_PAGESTATE à réinjecter + contrôle de page."""
    pagestate = sel.xpath(f"//input[@name='{PAGESTATE_FIELD}']/@value").get()
    num_input = sel.xpath("//input[contains(@name,'numPageTop') or contains(@name,'numPageBottom')]")
    page_input_name = num_input[0].attrib.get("name") if num_input else None
    current = None
    if num_input:
        try:
            current = int(num_input[0].attrib.get("value", "").strip())
        except ValueError:
            current = None
    total = None
    total_node = sel.xpath("(//*[contains(@id,'nombrePageTop') or contains(@id,'nombrePageBottom')])[1]")
    if total_node:
        m = re.search(r"\d+", node_text(total_node[0]))
        total = int(m.group(0)) if m else None
    target = page_input_name.replace("numPage", "DefaultButton") if page_input_name else None
    return {
        "pagestate": pagestate,
        "page_input_name": page_input_name,
        "postback_target": target,
        "current_page": current,
        "total_pages": total,
    }


def form_fields(sel: Selector, page_url: str) -> tuple[str, dict[str, str]]:
    """(URL d'action, champs) du formulaire PRADO, comme un navigateur le soumettrait
    sans cliquer de bouton : champs cachés/texte, cases cochées, options sélectionnées."""
    form = sel.xpath(f"//form[.//input[@name='{PAGESTATE_FIELD}']]")
    if not form:
        return page_url, {}
    form = form[0]
    action = urljoin(page_url, form.attrib.get("action") or page_url)
    fields: dict[str, str] = {}
    # Un navigateur n'envoie jamais un champ désactivé.
    for inp in form.xpath(".//input[@name and not(@disabled)]"):
        kind = (inp.attrib.get("type") or "text").lower()
        if kind in {"submit", "button", "image", "reset", "file"}:
            continue
        if kind in {"checkbox", "radio"} and "checked" not in inp.attrib:
            continue
        fields[inp.attrib["name"]] = inp.attrib.get("value", "on" if kind in {"checkbox", "radio"} else "")
    for select in form.xpath(".//select[@name and not(@disabled)]"):
        value = select.xpath(".//option[@selected]/@value").get() or select.xpath(".//option[1]/@value").get()
        if value is not None:
            fields[select.attrib["name"]] = value
    for area in form.xpath(".//textarea[@name and not(@disabled)]"):
        fields[area.attrib["name"]] = "".join(area.xpath("./text()").getall())
    return action, fields


def find_search_button(sel: Selector) -> tuple[str, str] | None:
    """(name, value) du bouton « Lancer la recherche » du formulaire de recherche avancée."""
    btn = sel.xpath(
        f"//form[.//input[@name='{PAGESTATE_FIELD}']]"
        "//input[@type='submit' and contains(@name,'lancerRecherche')]"
    )
    if not btn:
        return None
    return btn[0].attrib["name"], btn[0].attrib.get("value", "")


def parse_listing_page(sel: Selector, page_url: str) -> dict:
    rows = sel.xpath(f"//tr[.//a[contains(@href,'{DETAIL_HREF_MARKER}')] and not(.//tr)]")
    return {
        "rows": [parse_listing_row(r, page_url) for r in rows],
        "pager": parse_pager(sel),
        "captcha": looks_like_captcha(sel.get() if not rows else ""),
    }


# --- Fiche détail ---------------------------------------------------------------

def extract_dce_links(sel: Selector, page_url: str) -> list[str]:
    hrefs = sel.xpath(
        "//a[contains(@href,'Dce') or contains(@href,'DCE') or contains(@href,'dce')"
        " or contains(@id,'Dce') or contains(@id,'DCE')"
        " or contains(normalize-space(.),'Dossier de consultation')]/@href"
    ).getall()
    host = urlparse(page_url).netloc
    links: list[str] = []
    for href in hrefs:
        href = href.strip()
        if not href or href.startswith(("javascript:", "#", "mailto:")):
            continue
        url = urljoin(page_url, href)
        if urlparse(url).netloc == host and url not in links:
            links.append(url)
    return links


def parse_detail_page(sel: Selector, page_url: str) -> dict:
    lab = extract_labelled(sel)
    text = _hints(sel)
    statut_label = pick(lab, "statut", "etat de la consultation", "etat")
    return {
        "reference": pick(lab, "reference", "reference de la consultation"),
        "objet": pick(lab, "objet", "objet de la consultation"),
        "acheteur": pick(lab, "acheteur public", "acheteur", "entite publique", "organisme"),
        "categorie": pick(lab, "categorie principale", "categorie"),
        "type_procedure": pick(lab, "type de procedure", "procedure"),
        "lieu_execution": pick(lab, "lieu d execution", "lieux d execution"),
        "date_publication": first_date(pick(lab, "date de mise en ligne", "date de publication")),
        "date_limite_depot": first_date(
            pick(lab, "date et heure limite de remise des plis", "date limite de remise des plis", "date limite")
        ),
        "reservation_pme": interpret_pme(" ".join(f"{k} {v}" for k, v in lab.items()) + " " + text),
        "reponse_electronique": interpret_reponse_electronique(
            " ".join(f"{k} {v}" for k, v in lab.items()) + " " + text
        ),
        "statut_portail": interpret_statut(f"statut {statut_label}" if statut_label else text),
        "resultat": pick(lab, "attributaire", "resultat", "titulaire"),
        "dce_urls": extract_dce_links(sel, page_url),
        "captcha": looks_like_captcha(sel.get()),
    }


def merge_listing_detail(listing: dict, detail: dict) -> dict:
    """La fiche détail complète/écrase la ligne de liste ; la clé naturelle vient de l'URL."""
    merged = dict(listing)
    for key, value in detail.items():
        if key in {"org_acronyme", "ref_consultation", "url_detail", "captcha"}:
            continue
        if value not in (None, "", []):
            merged[key] = value
    merged.setdefault("dce_urls", detail.get("dce_urls", []))
    return merged
