"""Database access for the official-product enrichment (enrich.py only).

Writes to game_product_info, notice_documents, products and game_product_links
(migration 003). Never writes to the scraper's tables.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any

from .client import get_client


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _iso(value: Any) -> Any:
    return value.isoformat() if hasattr(value, "isoformat") else value


def _to_date(value: str | None) -> date | None:
    return date.fromisoformat(value[:10]) if value else None


# ── games (read only) ───────────────────────────────────────────────────────

def load_games(game_ids: list[str]) -> dict[str, dict[str, Any]]:
    """first_seen per game, from the scraper's games table (read only)."""
    if not game_ids:
        return {}
    rows = get_client().table("games").select("game_id, first_seen").in_("game_id", game_ids).execute().data
    return {r["game_id"]: {"first_seen": _to_date(r.get("first_seen"))} for r in rows}


# ── game_product_info ───────────────────────────────────────────────────────

def load_game_info() -> dict[str, dict[str, Any]]:
    rows = get_client().table("game_product_info").select("*").execute().data
    return {r["game_id"]: r for r in rows}


def save_listing_labels(labels: dict[str, str | None]) -> None:
    if labels:
        now = _now()
        get_client().table("game_product_info").upsert(
            [{"game_id": g, "listing_label": label, "label_seen_at": now} for g, label in labels.items()],
            on_conflict="game_id",
        ).execute()


def save_page_info(game_id: str, product_name: str | None, product_key: str | None, appendix: str | None) -> None:
    get_client().table("game_product_info").upsert({
        "game_id": game_id, "product_name": product_name, "product_key": product_key,
        "appendix": appendix, "page_read_at": _now(),
    }, on_conflict="game_id").execute()


def latest_label_periods() -> dict[str, dict[str, Any]]:
    """Each game's most recent listing_label_history row."""
    client = get_client()
    rows, offset = [], 0
    while True:
        page = (client.table("listing_label_history").select("id, game_id, label, first_seen")
                .order("first_seen", desc=True).range(offset, offset + 999).execute().data)
        rows.extend(page)
        if len(page) < 1000:
            break
        offset += 1000
    latest: dict[str, dict[str, Any]] = {}
    for r in rows:
        latest.setdefault(r["game_id"], r)
    return latest


def record_label_history(extend_ids: list[int], opened: list[dict[str, Any]]) -> None:
    now, client = _now(), get_client()
    for i in range(0, len(extend_ids), 200):
        client.table("listing_label_history").update({"last_seen": now}).in_("id", extend_ids[i:i + 200]).execute()
    if opened:
        client.table("listing_label_history").insert(
            [{**o, "first_seen": now, "last_seen": now} for o in opened]
        ).execute()


# ── notice_documents and products ───────────────────────────────────────────

def known_documents() -> set[str]:
    return {r["doc_id"] for r in get_client().table("notice_documents").select("doc_id").execute().data}


def record_document(doc: dict[str, str], products_found: int) -> None:
    get_client().table("notice_documents").upsert({
        "doc_id": doc["doc_id"], "url": doc["url"], "kind": doc["kind"], "label": doc.get("label"),
        "title": doc.get("title"), "products_found": products_found, "fetched_at": _now(),
    }, on_conflict="doc_id").execute()


def merge_products(products: list[dict[str, Any]], doc_id: str) -> None:
    """Merge one document's products into `products`. A stored value is replaced only
    by a non-empty one, and each date keeps the document it came from."""
    if not products:
        return
    client = get_client()
    keys = list({p["product_key"] for p in products})
    existing = {r["product_key"]: r for r in
                client.table("products").select("*").in_("product_key", keys).execute().data}
    rows: dict[str, dict[str, Any]] = {}
    for p in products:
        row = rows.get(p["product_key"]) or dict(existing.get(p["product_key"]) or {})
        row["product_key"] = p["product_key"]
        row["product_name"] = row.get("product_name") or p["product_name"]
        if p.get("appendix"):
            row["appendix"] = p["appendix"]
        if p.get("sale_start"):
            row["sale_start"], row["start_source"] = _iso(p["sale_start"]), doc_id
        if p.get("sale_end"):
            row["sale_end"], row["end_source"] = _iso(p["sale_end"]), doc_id
        row["updated_at"] = _now()
        rows[p["product_key"]] = row
    client.table("products").upsert(list(rows.values()), on_conflict="product_key").execute()


def load_products() -> list[dict[str, Any]]:
    rows = get_client().table("products").select("*").execute().data
    for r in rows:
        r["sale_start"], r["sale_end"] = _to_date(r.get("sale_start")), _to_date(r.get("sale_end"))
    return rows


# ── game_product_links ──────────────────────────────────────────────────────

def manual_links() -> set[str]:
    rows = get_client().table("game_product_links").select("game_id").eq("matched_by", "manual").execute().data
    return {r["game_id"] for r in rows}


def save_link(game_id: str, link: dict[str, Any]) -> None:
    get_client().table("game_product_links").upsert(
        {"game_id": game_id, **link, "updated_at": _now()}, on_conflict="game_id"
    ).execute()
