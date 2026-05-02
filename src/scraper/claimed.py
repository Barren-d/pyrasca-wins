from __future__ import annotations

import re
import sys
sys.stdout.reconfigure(encoding="utf-8")

from datetime import datetime, timezone
from typing import Any

from bs4 import BeautifulSoup

from . import session
from ..db.client import get_client

BASE_URL = "https://www.juegosonce.es"
CAROUSEL_URL = f"{BASE_URL}/rascas-once"


def scrape_claimed() -> list[dict[str, Any]]:
    html = session.get(CAROUSEL_URL, cache=False)
    soup = BeautifulSoup(html, "lxml")

    carousel = soup.find("div", id="ultimosPremios")
    if not carousel:
        raise RuntimeError("Claimed prizes carousel not found — ONCE page structure may have changed")

    claims: list[dict[str, Any]] = []
    for li in carousel.find_all("li", class_="glide__slide"):
        claim = _parse_carousel_item(li)
        if claim:
            claims.append(claim)

    return claims


def _parse_carousel_item(li) -> dict[str, Any] | None:
    a = li.find("a", class_="boton")
    if not a:
        return None

    game_url_rel = a.get("href", "")
    game_url = BASE_URL + game_url_rel

    img = a.find("img")
    game_name = img["alt"] if img and img.get("alt") else None
    if not game_name:
        return None

    # game_id from image src: .../premio/EJ4/...
    game_id = None
    if img and img.get("src"):
        m = re.search(r"/premio/([^/]+)/", img["src"])
        if m:
            game_id = m.group(1)

    # winner from aria-labelledby: "V.L.M.1 RascaCandyCash1" → "V.L.M."
    labelledby = a.get("aria-labelledby", "")
    winner = _extract_winner_initials(labelledby)

    # prize amount from second visible <p>
    visible_ps = [p for p in a.find_all("p") if not p.get("class")]
    prize_amount_raw = visible_ps[1].get_text(strip=True) if len(visible_ps) >= 2 else None
    prize_amount = _parse_prize_amount(prize_amount_raw) if prize_amount_raw else None

    # claimed_at from last visible <p> e.g. "02/05/2026 14:05"
    claimed_at_str = visible_ps[2].get_text(strip=True) if len(visible_ps) >= 3 else None
    claimed_at = _parse_claimed_at(claimed_at_str) if claimed_at_str else None

    if not prize_amount or not claimed_at:
        return None

    return {
        "game_id": game_id,
        "game_name": game_name,
        "game_url": game_url,
        "winner": winner,
        "prize_amount": prize_amount,
        "prize_amount_raw": prize_amount_raw,
        "claimed_at": claimed_at,
    }


def _extract_winner_initials(labelledby: str) -> str:
    # "V.L.M.1 RascaCandyCash1" → take the first token, strip trailing digits
    token = labelledby.split()[0] if labelledby else ""
    return re.sub(r"\d+$", "", token)


def _parse_prize_amount(raw: str) -> float | None:
    cleaned = raw.replace("€", "").replace(" ", "").replace(".", "").replace(",", ".")
    try:
        return float(cleaned)
    except ValueError:
        return None


def _parse_claimed_at(raw: str) -> str | None:
    # "02/05/2026 14:05"
    try:
        dt = datetime.strptime(raw.strip(), "%d/%m/%Y %H:%M")
        return dt.replace(tzinfo=timezone.utc).isoformat()
    except ValueError:
        return None


def match_prize_tier_ids(claims: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Attempt to link each claim to a prize_tier_id where unambiguous.

    Restricts the candidate pool to the LATEST snapshot per (game, price) — older
    snapshots contain the same logical tiers under different tier_ids, which would
    spuriously inflate the unambiguity count.

    Two-step query rather than an embedded join — supabase-py's filter on a nested
    table (.in_("game_snapshots.game_id", …)) is unreliable.
    """
    if not claims:
        return claims

    client = get_client()
    game_ids = list({c["game_id"] for c in claims if c.get("game_id")})
    if not game_ids:
        for claim in claims:
            claim["prize_tier_id"] = None
        return claims

    # Step 1 — all snapshots, ordered newest first, so the dict pickup keeps the latest
    snap_rows = (
        client.table("game_snapshots")
        .select("snapshot_id, game_id, price, scraped_at")
        .in_("game_id", game_ids)
        .order("scraped_at", desc=True)
        .execute()
        .data
    )
    latest_snap_per_price: dict[tuple, str] = {}
    for r in snap_rows:
        key = (r["game_id"], float(r["price"]))
        if key not in latest_snap_per_price:
            latest_snap_per_price[key] = r["snapshot_id"]
    if not latest_snap_per_price:
        for claim in claims:
            claim["prize_tier_id"] = None
        return claims

    snap_to_game: dict[str, str] = {sid: g for (g, _), sid in latest_snap_per_price.items()}

    # Step 2 — prize tiers under those latest snapshots only
    tier_rows = (
        client.table("prize_tiers")
        .select("tier_id, prize_amount, snapshot_id")
        .in_("snapshot_id", list(snap_to_game.keys()))
        .execute()
        .data
    )

    from collections import defaultdict
    tier_map: dict[tuple, set] = defaultdict(set)
    for row in tier_rows:
        gid = snap_to_game.get(row["snapshot_id"])
        if gid:
            tier_map[(gid, float(row["prize_amount"]))].add(row["tier_id"])

    for claim in claims:
        key = (claim.get("game_id"), claim.get("prize_amount"))
        tier_ids = tier_map.get(key, set())
        # exactly one tier across the game's latest snapshots → unambiguous match
        claim["prize_tier_id"] = next(iter(tier_ids)) if len(tier_ids) == 1 else None

    return claims
