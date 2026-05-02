from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from .client import get_client


def upsert_game(game: dict[str, Any]) -> None:
    game["last_seen"] = _now()
    get_client().table("games").upsert(game, on_conflict="game_id").execute()


def open_scrape_run(run_type: str) -> str:
    res = (
        get_client()
        .table("scrape_runs")
        .insert({"run_type": run_type, "status": "running"})
        .execute()
    )
    return res.data[0]["run_id"]


def close_scrape_run(run_id: str, status: str, games_scraped: int | None = None) -> None:
    payload: dict[str, Any] = {"status": status, "completed_at": _now()}
    if games_scraped is not None:
        payload["games_scraped"] = games_scraped
    get_client().table("scrape_runs").update(payload).eq("run_id", run_id).execute()


def insert_snapshot(snapshot: dict[str, Any]) -> str:
    res = get_client().table("game_snapshots").insert(snapshot).execute()
    return res.data[0]["snapshot_id"]


def insert_prize_tiers(tiers: list[dict[str, Any]]) -> list[str]:
    if not tiers:
        return []
    res = get_client().table("prize_tiers").insert(tiers).execute()
    return [row["tier_id"] for row in res.data]


def upsert_claimed_prize(claim: dict[str, Any]) -> None:
    get_client().table("claimed_prizes").upsert(
        claim,
        on_conflict="game_name,winner,prize_amount,claimed_at",
    ).execute()


def update_snapshot_ev(snapshot_id: str, fields: dict[str, Any]) -> None:
    payload = {**fields, "ev_recomputed_at": _now()}
    get_client().table("game_snapshots").update(payload).eq("snapshot_id", snapshot_id).execute()


def nullify_ambiguous_prize_tiers(game_id: str) -> None:
    """Set prize_tier_id = NULL on claimed_prizes where prize_amount appears in
    more than one price tier for this game (condition (b) of observable tier set O).

    Two-step query — embedded-join filters on supabase-py are unreliable.
    """
    client = get_client()

    snap_rows = (
        client.table("game_snapshots")
        .select("snapshot_id, price")
        .eq("game_id", game_id)
        .execute()
        .data
    )
    if not snap_rows:
        return
    snap_to_price: dict[str, float] = {r["snapshot_id"]: float(r["price"]) for r in snap_rows}

    tier_rows = (
        client.table("prize_tiers")
        .select("prize_amount, snapshot_id")
        .in_("snapshot_id", list(snap_to_price.keys()))
        .execute()
        .data
    )

    from collections import defaultdict
    price_by_amount: dict[float, set] = defaultdict(set)
    for row in tier_rows:
        price = snap_to_price.get(row["snapshot_id"])
        if price is not None:
            price_by_amount[float(row["prize_amount"])].add(price)

    ambiguous = [amt for amt, prices in price_by_amount.items() if len(prices) > 1]
    for amt in ambiguous:
        (
            client.table("claimed_prizes")
            .update({"prize_tier_id": None})
            .eq("game_id", game_id)
            .eq("prize_amount", amt)
            .execute()
        )


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
