"""Enrich the scraped games with official product data from ONCE's regulations.

Usage:
    python enrich.py            # daily: listing labels, new game pages, new documents, links

Separate from scrape.py on purpose: it only reads the scraper's games table and
writes to its own tables (migration 003), so nothing here can affect scraping.
Problems are printed as warnings and the run still exits 0.

Each run costs: the listing (1 request) and /reglamentos (1 request), plus pages of
games not seen before and PDFs not read before; usually nothing else.
"""
from __future__ import annotations

import sys
from datetime import date, datetime, timedelta, timezone

sys.stdout.reconfigure(encoding="utf-8")

from src.db import products as db
from src.scraper import notices, session

PAGE_REFRESH_DAYS = 30   # re-read a game's page monthly in case ONCE re-themes it


def main() -> None:
    today = datetime.now(timezone.utc).date()
    steps = [_labels_and_pages, _documents, _links]
    listing: list[dict] = []
    for step in steps:
        try:
            result = step(today, listing)
            if step is _labels_and_pages:
                listing = result
        except Exception as exc:
            print(f"WARN {step.__name__.strip('_')} step failed: {exc}")
    print("Enrichment done")


def _labels_and_pages(today: date, _listing) -> list[dict]:
    listing = notices.parse_listing(session.get(notices.LISTING_URL, cache=False))
    # Only games the scraper already knows (our tables reference games); a brand-new
    # game is picked up on the first run after the full scrape adds it.
    known = db.load_games([g["game_id"] for g in listing])
    skipped = [g["game_id"] for g in listing if g["game_id"] not in known]
    listing = [g for g in listing if g["game_id"] in known]
    print(f"Listing: {len(listing)} games" + (f" ({len(skipped)} not scraped yet: {', '.join(skipped)})" if skipped else ""))
    db.save_listing_labels({g["game_id"]: g["listing_label"] for g in listing})

    info = db.load_game_info()
    stale = datetime.now(timezone.utc) - timedelta(days=PAGE_REFRESH_DAYS)
    to_read = [
        g for g in listing
        if not info.get(g["game_id"], {}).get("page_read_at")
        or datetime.fromisoformat(info[g["game_id"]]["page_read_at"]) < stale
    ]
    for g in to_read:
        try:
            page = notices.parse_product_info(session.get(g["url"], cache=False))
        except Exception as exc:
            print(f"  WARN could not read {g['url']}: {exc}")
            continue
        key = notices.product_key(page["product_name"]) if page["product_name"] else None
        db.save_page_info(g["game_id"], page["product_name"], key, page["appendix"])
    print(f"Game pages read: {len(to_read)}")
    return listing


def _documents(today: date, _listing) -> None:
    known = db.known_documents()
    new_docs = [d for d in notices.list_notice_documents() if d["doc_id"] not in known]
    for doc in new_docs:
        try:
            found = notices.fetch_and_parse(doc)
        except Exception as exc:
            print(f"  WARN could not read {doc['url']}: {exc}")
            continue
        db.record_document(doc, 0)  # recorded first: products reference it
        db.merge_products(found, doc["doc_id"])
        db.record_document(doc, len(found))
        print(f"  {doc['label']}: {len(found)} product(s)")
    print(f"Regulation documents: {len(new_docs)} new")


def _links(today: date, listing: list[dict]) -> None:
    if not listing:
        print("Links: skipped (no listing)")
        return
    products = db.load_products()
    info = db.load_game_info()
    games = db.load_games([g["game_id"] for g in listing])
    manual = db.manual_links()
    counts = {"auto": 0, "rejected": 0, "none": 0, "manual": 0}
    for g in listing:
        gid = g["game_id"]
        if gid in manual:
            counts["manual"] += 1
            continue
        page = info.get(gid, {})
        link = notices.link_game({
            "product_key": page.get("product_key"),
            "appendix": page.get("appendix"),
            "listed_start": g["listed_start"],
            "first_seen": games.get(gid, {}).get("first_seen"),
            "listing_label": g["listing_label"],
        }, products, today)
        if link is None:
            counts["none"] += 1
            continue
        db.save_link(gid, link)
        counts[link["status"]] += 1
        if link["check_notes"]:
            print(f"  {link['status'].upper()} {gid} → {link['product_key']}: {link['check_notes']}")
    print(f"Links: {counts['auto']} accepted, {counts['rejected']} rejected, "
          f"{counts['manual']} manual (kept), {counts['none']} without a product")


if __name__ == "__main__":
    main()
