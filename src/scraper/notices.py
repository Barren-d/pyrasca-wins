"""Official launch and end-of-sale dates from ONCE's regulations page.

Used only by enrich.py: this enriches the scraped data and never feeds the scraper.

ONCE must publish the end of sale of an electronic instant-lottery product on
JuegosONCE.es at least 30 days ahead (Reglamento Lotería Instantánea, art. 19.4).
It does so in two kinds of PDF linked from /reglamentos:

- "Resolución … Director General … terminación": approves the end of one or more
  products and gives each one's last day of sale (and the day it first went on sale).
- "Certificado Consejo Protectorado … Lanzamiento y finalización": lists new
  products with their appendix and first day of sale, sometimes with an end date.

Both name products by their internal regulatory name (e.g. "Importes iguales 6"),
which each game's page also states: "RascaCash (Importes iguales 6) es el juego…".
That name, normalised by product_key(), links a game to its dates.
"""
from __future__ import annotations

import hashlib
import io
import random
import re
import sys
import time
import unicodedata
from datetime import date, timedelta
from typing import Any

from bs4 import BeautifulSoup

from . import session

sys.stdout.reconfigure(encoding="utf-8")

BASE_URL = "https://www.juegosonce.es"
REGULATIONS_URL = f"{BASE_URL}/reglamentos"
LISTING_URL = f"{BASE_URL}/rascas-todos"

_MONTHS = {
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6, "julio": 7,
    "agosto": 8, "septiembre": 9, "setiembre": 9, "octubre": 10, "noviembre": 11, "diciembre": 12,
}
_LONG_DATE = re.compile(r"(\d{1,2}) de (" + "|".join(_MONTHS) + r") de (\d{4})", re.I)
_NAME = re.compile(r"con el nombre\s*[“\"«]\s*([^”\"»]+?)\s*[”\"»]", re.I)
_QUOTED = re.compile(r"[“\"«]\s*([^”\"»]+?)\s*[”\"»]")
_STARTED = re.compile(r"comenz\w+ a comercializarse con fecha\s+" + _LONG_DATE.pattern, re.I)
_APPENDIX = r"[EF]-\d{4}-\d{2}"
# Launch-table row: "<name> E-2026-22 «Con mecánica …» a cinco euros, clase 2 25/11/2026"
_LAUNCH_ROW = re.compile(
    r"(" + _APPENDIX + r")\s+«[^»]*»\s*a\s+.{1,30}?euros?,\s*clase\s+\d+\s*[“\"]?\s*(\d{2})/(\d{2})/(\d{4})", re.I
)
# What can precede a launch-table name: the table header, a PDF signature footer
# ("… | Sin acción específica"), the previous row's date, or the end of a sentence
# (text extraction sometimes moves a table row after the closing paragraph).
_ROW_BOUNDARY = re.compile(r"Comercializaci[óo]n|Sin acción específica|\d{2}/\d{2}/\d{4}|\.\s", re.I)
# End date fixed at launch (art. 19.5), for one or several products:
#   "la fecha de finalización del producto «X» (grupo de productos del apéndice F-2026-17) será el 24 de febrero de 2027"
#   "la fecha de finalización de los productos «A» (… E-2026-20) y «B» (… F-2026-16) será el 3 de febrero de 2027"
_CLAUSE_END = re.compile(
    r"fecha de finalización de(?:l producto| los productos)\s+(.{3,400}?)\s*será el\s+" + _LONG_DATE.pattern,
    re.I,
)
_CLAUSE_PRODUCT = re.compile(
    r"[“\"«]\s*([^”\"»]+?)\s*[”\"»](?:\s*\(grupo de productos del ap[ée]ndice\s+(" + _APPENDIX + r")\))?", re.I
)


def product_key(name: str) -> str:
    """Normalise a product name for matching: no accents, lower case, single spaces."""
    text = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    return " ".join(re.sub(r"[“”\"«»]", " ", text).lower().split())


def _long_date(m: re.Match, offset: int = 1) -> date:
    return date(int(m.group(offset + 2)), _MONTHS[m.group(offset + 1).lower()], int(m.group(offset)))


def _flat(text: str) -> str:
    return " ".join(text.split())


# ── Listing and game pages ───────────────────────────────────────────────────

def parse_listing(html: str) -> list[dict[str, Any]]:
    """Each game card on the listing: id, page URL, card badge and the listing's
    start timestamp (local midnight stored as UTC, i.e. 22:00/23:00 UTC the day before)."""
    soup = BeautifulSoup(html, "lxml")
    out = []
    for li in soup.select("li.rascaOrdenable"):
        link = li.find("a", class_="informacionrasca")
        badge = li.find("span", class_="lblsorteohoy")
        start = li.find("span", attrs={"data-fecha": True})
        listed = None
        if start:
            # +3 h moves 22:00/23:00 UTC onto the Madrid calendar date
            listed = (date(1970, 1, 1) + timedelta(milliseconds=int(start["data-fecha"]) + 3 * 3600 * 1000))
        out.append({
            "game_id": li.get("data-producto"),
            "url": BASE_URL + link["href"] if link else None,
            "listing_label": badge.get_text(strip=True) if badge else None,
            "listed_start": listed,
        })
    return [g for g in out if g["game_id"] and g["url"]]




def parse_product_info(html: str) -> dict[str, str | None]:
    """Internal product name and appendix code from a game's information page.

    "RascaCash (Importes iguales 6) es el juego en el que…" → "Importes iguales 6"
    "…puedes consultar el apéndice E-2022-01 del reglamento…" → "E-2022-01"
    Either can be missing; some pages don't state the internal name.
    """
    soup = BeautifulSoup(html, "lxml")
    product_name = None
    for p in soup.find_all("p"):
        m = re.match(r"\s*[^()]{1,80}?\(([^()]{2,60})\)\s+es\s+(?:el|un)\s+(?:juego|rasca)", _flat(p.get_text(" ")), re.I)
        if m:
            product_name = m.group(1).strip()
            break
    m = re.search(r"ap[ée]ndice\s+(" + _APPENDIX + r")", soup.get_text(" "), re.I)
    return {"product_name": product_name, "appendix": m.group(1) if m else None}


# ── Regulation PDFs ──────────────────────────────────────────────────────────

def list_notice_documents() -> list[dict[str, str]]:
    """Instant-lottery launch and end-of-sale PDFs linked from /reglamentos.

    Includes the BOE copies: ONCE has reused a PDF file name for two different
    agreements (the later upload replacing the earlier), and the BOE verification
    notices also carry end dates fixed at launch. Each document is identified by
    its URL *and* its listing text, so a reused URL with new text counts as new.
    """
    soup = BeautifulSoup(session.get(REGULATIONS_URL, cache=False), "lxml")
    docs: dict[str, dict[str, str]] = {}
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if not href.lower().endswith(".pdf") or not re.search(r"juegosonce\.es|boe\.es", href):
            continue
        parent = a.find_parent(["li", "p", "tr", "div"])
        context = _flat(parent.get_text(" ")) if parent else _flat(a.get_text(" "))
        if not re.search(r"lotería instantánea", context, re.I):
            continue
        if re.search(r"terminaci[óo]n", context, re.I):
            kind = "end"
        elif re.search(r"lanzamiento|finalizaci[óo]n", context, re.I):
            kind = "launch"  # launch agreements, incl. end dates fixed at launch
        else:
            continue
        doc_id = hashlib.sha1(f"{href}|{context}".encode()).hexdigest()[:16]
        docs[doc_id] = {"doc_id": doc_id, "url": href, "kind": kind,
                        "label": doc_label(context, href), "title": context[:300]}
    return list(docs.values())


def doc_label(title: str, url: str = "") -> str:
    """Short reference for showing a date's source, e.g. 'Resolución 98/2026'."""
    m = re.search(r"Resoluci[óo]n\s+(?:n[úu]m\.\s*)?(\d+/\d{4})", title, re.I)
    if m:
        return f"Resolución {m.group(1)}"
    m = re.search(r"Acuerdos?\s+(CEP\.\s?\d+/\d{4}-[\d.]+)", title, re.I)
    if m:
        prefix = "BOE, " if "boe.es" in url else ""
        return f"{prefix}Acuerdo {m.group(1).replace(' ', '')}"
    return "BOE" if "boe.es" in url else "ONCE"


def get_pdf(url: str, attempts: int = 3) -> bytes:
    """Fetch a regulation PDF. Kept separate from the scraper's session.get so the
    enrichment never changes how game pages are fetched."""
    from curl_cffi import requests  # same client the scraper uses

    last: Exception | None = None
    for attempt in range(attempts):
        if attempt:
            time.sleep(15 * attempt)
        try:
            print(f"  [pdf] {url}")
            r = requests.get(url, impersonate="chrome", timeout=60)
            r.raise_for_status()
            time.sleep(random.uniform(1.5, 4.5))
            return r.content
        except Exception as exc:  # network errors, 4xx/5xx
            last = exc
    raise RuntimeError(f"could not fetch {url}: {last}")


def pdf_text(data: bytes) -> str:
    from pypdf import PdfReader  # imported lazily: only the full scrape needs it

    return _flat(" ".join(page.extract_text() or "" for page in PdfReader(io.BytesIO(data)).pages))


def parse_termination(text: str) -> list[dict[str, Any]]:
    """Products and dates from a Director General end-of-sale resolution."""
    text = _flat(text)
    split = re.search(r"\b2\s*º", text)
    head, tail = (text[: split.start()], text[split.start():]) if split else (text, "")

    names = list(dict.fromkeys(m.group(1) for m in _NAME.finditer(head)))
    products: dict[str, dict[str, Any]] = {n: {"product_name": n, "sale_start": None, "sale_end": None} for n in names}

    # First day of sale: the next "comenzó a comercializarse con fecha …" after each name
    started = [(m.start(), _long_date(m, 1)) for m in _STARTED.finditer(head)]
    for m in _NAME.finditer(head):
        nxt = next((d for pos, d in started if pos > m.end()), None)
        if nxt:
            products[m.group(1)]["sale_start"] = nxt

    # Last day of sale: in the decision clauses, each named product takes the next
    # date after its name; with no names there ("los anteriores productos"), all
    # products take the first date.
    dates = [(m.start(), _long_date(m, 1)) for m in _LONG_DATE.finditer(tail)]
    mentioned = [(m.end(), m.group(1)) for m in _QUOTED.finditer(tail) if m.group(1) in products]
    if mentioned:
        for pos, name in mentioned:
            nxt = next((d for p, d in dates if p > pos), None)
            if nxt and products[name]["sale_end"] is None:
                products[name]["sale_end"] = nxt
    elif dates:
        for p in products.values():
            p["sale_end"] = dates[0][1]
    return list(products.values())


def parse_launch(text: str) -> list[dict[str, Any]]:
    """Products from a launch agreement: name, appendix, first day of sale, and any
    end date fixed at launch (art. 19.5)."""
    text = _flat(text)
    products: dict[str, dict[str, Any]] = {}
    prev_end = 0
    for m in _LAUNCH_ROW.finditer(text):
        before = text[prev_end:m.start()]
        # the name is what follows the table header, a page footer or the previous row
        name = _ROW_BOUNDARY.split(before)[-1].strip(" .:;")
        prev_end = m.end()
        if not name or len(name) > 60:
            continue
        products[name] = {
            "product_name": name, "appendix": m.group(1),
            "sale_start": date(int(m.group(4)), int(m.group(3)), int(m.group(2))), "sale_end": None,
        }
    for m in _CLAUSE_END.finditer(text):
        end = _long_date(m, 2)
        for pm in _CLAUSE_PRODUCT.finditer(m.group(1)):
            name = pm.group(1)
            p = products.setdefault(name, {"product_name": name, "appendix": None, "sale_start": None, "sale_end": None})
            p["appendix"] = p["appendix"] or pm.group(2)
            p["sale_end"] = end
    return list(products.values())


LAUNCH_TOLERANCE_DAYS = 3
LAST_DAYS_WINDOW = 7       # art. 19.6: the end date is shown at least a week ahead


def link_game(game: dict[str, Any], products: list[dict[str, Any]], today: date) -> dict[str, Any] | None:
    """Propose the link between a website game and the official product it sells.

    Finding the product:
    1. The internal name on the game's page matches a product exactly (after
       product_key normalisation). Physical products (appendix F-…) are never used:
       every game on the site is electronic, and physical twins such as
       "Millonario 2024" have their own end dates.
    2. Fallback for pages without an internal name: exactly one product in the same
       electronic appendix that went on sale within a few days of the date the
       listing gives the game. The appendix alone is not enough (one appendix covers
       several products over time; the three Súper Millones editions share E-2021-12).

    Checking it: a link that contradicts what we saw on the website is returned
    with status 'rejected' and the reason, so it is visible instead of silently used.
    Softer disagreements are kept as 'auto' with a note.

    `game` keys: product_key, appendix, listed_start, first_seen (dates), listing_label.
    Returns {"product_key", "matched_by", "status", "check_notes"} or None.
    """
    electronic = [p for p in products if not (p.get("appendix") or "").upper().startswith("F-")]
    product, matched_by = None, None

    key = game.get("product_key")
    if key:
        product = next((p for p in electronic if p["product_key"] == key), None)
        matched_by = "product_name" if product else None

    appendix, listed = game.get("appendix"), game.get("listed_start")
    if product is None and appendix and listed:
        candidates = [
            p for p in electronic
            if p.get("appendix") == appendix and p.get("sale_start")
            and abs((p["sale_start"] - listed).days) <= LAUNCH_TOLERANCE_DAYS
        ]
        if len(candidates) == 1:
            product, matched_by = candidates[0], "appendix"

    if product is None:
        return None

    rejected, warnings = [], []
    start, end = product.get("sale_start"), product.get("sale_end")
    first_seen = game.get("first_seen")
    if end and first_seen and end < first_seen - timedelta(days=1):
        rejected.append(f"product ended {end} before the game was first seen {first_seen}")
    if start and listed and start > listed + timedelta(days=LAUNCH_TOLERANCE_DAYS):
        rejected.append(f"product launched {start} after the game was listed {listed}")
    last_days = "ltimos" in (game.get("listing_label") or "")
    if end and today <= end <= today + timedelta(days=LAST_DAYS_WINDOW) and not last_days:
        warnings.append(f"ends {end} but the listing has no last-days label")
    if last_days and end and end > today + timedelta(days=2 * LAST_DAYS_WINDOW):
        warnings.append(f"listing says last days but the product ends {end}")

    return {
        "product_key": product["product_key"],
        "matched_by": matched_by,
        "status": "rejected" if rejected else "auto",
        "check_notes": "; ".join(rejected + warnings) or None,
    }


def fetch_and_parse(doc: dict[str, str]) -> list[dict[str, Any]]:
    text = pdf_text(get_pdf(doc["url"]))
    parsed = parse_termination(text) if doc["kind"] == "end" else parse_launch(text)
    for p in parsed:
        p["product_key"] = product_key(p["product_name"])
        p.setdefault("appendix", None)
    return parsed
