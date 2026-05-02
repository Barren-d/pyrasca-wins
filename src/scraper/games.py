from __future__ import annotations

import sys
sys.stdout.reconfigure(encoding="utf-8")

from datetime import datetime, timezone
from typing import Any

from bs4 import BeautifulSoup

from . import session

BASE_URL = "https://www.juegosonce.es"
LISTING_URL = f"{BASE_URL}/rascas-todos"


def scrape_games() -> list[dict[str, Any]]:
    html = session.get(LISTING_URL)
    soup = BeautifulSoup(html, "lxml")

    section = soup.find("section", class_="modulorasca favorita")
    if not section:
        raise RuntimeError("Listing section not found — ONCE page structure may have changed")

    games: list[dict[str, Any]] = []
    for li in section.find_all("li", class_="rascaOrdenable"):
        game = _parse_game_li(li)
        if game:
            games.append(game)

    return games


def _parse_game_li(li) -> dict[str, Any] | None:
    game_id = li.get("data-producto")
    name = li.get("data-name")
    if not game_id or not name:
        return None

    price_raw = li.get("data-price", "")
    prices = [_parse_price(p) for p in price_raw.split(" - ") if p.strip()]
    multi_price = len(prices) > 1

    link = li.find("a", class_="informacionrasca")
    url = BASE_URL + link["href"] if link else None

    img = li.find("img")
    img_url = img["src"] if img else None

    start_span = li.find("span", class_="ocu")
    game_start = None
    if start_span and start_span.get("data-fecha"):
        ts_ms = int(start_span["data-fecha"])
        game_start = datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc).isoformat()

    payout_p = li.find("p", class_="premio")
    max_payout = payout_p.get("data-premio") if payout_p else None

    return {
        "game_id": game_id,
        "name": name,
        "url": url,
        "img_url": img_url,
        "game_start": game_start,
        "max_payout": max_payout,
        "prices": prices,
        "multi_price": multi_price,
        "active": True,
    }


def _parse_price(raw: str) -> float:
    return float(raw.strip().replace(",", "."))
