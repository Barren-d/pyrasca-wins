"""Pipeline entry point.

Usage:
    python scrape.py --mode full      # daily: games + prizes + claimed + EV
    python scrape.py --mode claimed   # hourly: claimed + EV update
"""
from __future__ import annotations

import argparse
import sys
from datetime import date, timezone, datetime

sys.stdout.reconfigure(encoding="utf-8")

from src.db.client import get_client
from src.db import write as db
from src.scraper import games as games_scraper
from src.scraper import prizes as prizes_scraper
from src.scraper import claimed as claimed_scraper
from src.analysis import retention as ret_module
from src.analysis.depletion import compute_adj_ev


def run_full() -> None:
    run_id = db.open_scrape_run("full")
    print(f"Full scrape started — run_id={run_id}")
    games_scraped = 0

    try:
        games = games_scraper.scrape_games()
        print(f"Found {len(games)} games")

        empirical_retention = ret_module.load_empirical_retention()

        for game in games:
            print(f"  game_id={game['game_id']} — {game['name']}")
            db.upsert_game({
                "game_id": game["game_id"],
                "name": game["name"],
                "url": game["url"],
                "img_url": game["img_url"],
                "game_start": game["game_start"],
                "max_payout": game["max_payout"],
                "prices": game["prices"],
                "multi_price": game["multi_price"],
                "active": True,
            })

            snapshots = prizes_scraper.scrape_prizes(
                game["game_id"], game["url"], game["prices"]
            )

            for snap in snapshots:
                snapshot_id = db.insert_snapshot({
                    "run_id": run_id,
                    "game_id": snap["game_id"],
                    "price": snap["price"],
                    "total_scenarios": snap["total_scenarios"],
                    "winning_scenarios": snap["winning_scenarios"],
                    "losing_scenarios": snap["losing_scenarios"],
                    "expected_return": snap["expected_return"],
                    "expected_return_per_euro": snap["expected_return_per_euro"],
                    "adj_expected_return": snap["adj_expected_return"],
                    "adj_expected_return_per_euro": snap["adj_expected_return_per_euro"],
                    "sell_through": snap["sell_through"],
                    "sell_through_se": snap["sell_through_se"],
                    "low_confidence": snap["low_confidence"],
                    "retention_calibrated": snap["retention_calibrated"],
                })

                if snap["prize_tiers"]:
                    tiers_to_insert = [
                        {**t, "snapshot_id": snapshot_id}
                        for t in snap["prize_tiers"]
                    ]
                    db.insert_prize_tiers(tiers_to_insert)

            db.nullify_ambiguous_prize_tiers(game["game_id"])
            games_scraped += 1

        # claimed scrape + EV update
        _run_claimed_inner(run_id, empirical_retention)

        db.close_scrape_run(run_id, "success", games_scraped)
        print(f"Full scrape complete — {games_scraped} games")

    except Exception as exc:
        db.close_scrape_run(run_id, "failed")
        raise


def run_claimed() -> None:
    run_id = db.open_scrape_run("claimed")
    print(f"Claimed scrape started — run_id={run_id}")

    try:
        empirical_retention = ret_module.load_empirical_retention()
        needs_full = _run_claimed_inner(run_id, empirical_retention)
        db.close_scrape_run(run_id, "success")
        print("Claimed scrape complete")
    except Exception:
        db.close_scrape_run(run_id, "failed")
        raise

    if needs_full:
        print("  Missing game(s) detected — escalating to full scrape")
        run_full()


def _run_claimed_inner(run_id: str, empirical_retention) -> bool:
    """Returns True if any FK errors were detected (game missing from games table)."""
    client = get_client()

    claims = claimed_scraper.scrape_claimed()
    print(f"  Fetched {len(claims)} carousel entries")

    claims = claimed_scraper.match_prize_tier_ids(claims)
    matched = sum(1 for c in claims if c.get("prize_tier_id"))
    print(f"  Matched to prize tier: {matched}/{len(claims)} ({100*matched/len(claims):.0f}%)" if claims else "  No claims")

    count_before = client.table("claimed_prizes").select("claim_id", count="exact").execute().count or 0

    errors = 0
    needs_full_scrape = False
    for claim in claims:
        try:
            db.upsert_claimed_prize({
                "first_run_id": run_id,
                "last_run_id": run_id,
                "game_id": claim.get("game_id"),
                "game_name": claim["game_name"],
                "game_url": claim.get("game_url"),
                "winner": claim.get("winner"),
                "prize_amount": claim["prize_amount"],
                "prize_amount_raw": claim["prize_amount_raw"],
                "claimed_at": claim["claimed_at"],
                "prize_tier_id": claim.get("prize_tier_id"),
            })
        except Exception as e:
            msg = str(e).lower()
            if "foreign key" in msg or "23503" in msg:
                print(f"  WARN FK error — '{claim.get('game_name')}' not in games table")
                needs_full_scrape = True
            else:
                print(f"  WARN upsert failed: {claim.get('game_name')} {claim.get('prize_amount')} — {e}")
            errors += 1

    count_after = client.table("claimed_prizes").select("claim_id", count="exact").execute().count or 0
    print(f"  claimed_prizes: {count_before} → {count_after} (+{count_after - count_before} new, {errors} errors)")

    _recalculate_ev(empirical_retention)
    return needs_full_scrape


def _recalculate_ev(empirical_retention) -> None:
    client = get_client()
    today = date.today()

    # Floor on scraping_days: the earliest moment we've actually been observing
    # the claimed-prizes carousel. games.first_seen records when each game was
    # added to our DB, but for old games that predates the claimed scraper —
    # using it would overstate scraping_days and let the depletion MLE run on
    # thin claim data. (See depletion.py MIN_SCRAPING_DAYS guard.)
    earliest_claim_row = (
        client.table("claimed_prizes")
        .select("first_seen")
        .order("first_seen")
        .limit(1)
        .execute()
        .data
    )
    claims_observation_start = (
        _parse_date(earliest_claim_row[0]["first_seen"]) if earliest_claim_row else None
    )

    # fetch all active games with their latest snapshot per price
    games_rows = (
        client.table("games")
        .select("game_id, game_start, first_seen")
        .eq("active", True)
        .execute()
        .data
    )

    for game_row in games_rows:
        game_id = game_row["game_id"]
        game_start = _parse_date(game_row.get("game_start"))
        game_first_seen = _parse_date(game_row.get("first_seen"))
        scrape_start = _floor_scrape_start(game_first_seen, claims_observation_start)

        # latest snapshot per price
        snapshots = (
            client.table("game_snapshots")
            .select("snapshot_id, price, total_scenarios")
            .eq("game_id", game_id)
            .order("scraped_at", desc=True)
            .execute()
            .data
        )

        seen_prices: set[float] = set()
        for snap in snapshots:
            price = float(snap["price"])
            if price in seen_prices:
                continue
            seen_prices.add(price)

            # prize tiers for this snapshot
            tiers = (
                client.table("prize_tiers")
                .select("occurrences, prize_amount")
                .eq("snapshot_id", snap["snapshot_id"])
                .execute()
                .data
            )

            # matched claimed prizes for this game
            claimed = (
                client.table("claimed_prizes")
                .select("prize_amount, prize_tier_id")
                .eq("game_id", game_id)
                .not_.is_("prize_tier_id", "null")
                .execute()
                .data
            )

            result = compute_adj_ev(
                snapshot_id=snap["snapshot_id"],
                game_id=game_id,
                price=price,
                prize_tiers=[{"occurrences": int(t["occurrences"]), "prize_amount": float(t["prize_amount"])} for t in tiers],
                claimed_prizes=claimed,
                game_start=game_start,
                scrape_start=scrape_start,
                today=today,
                empirical_retention=empirical_retention,
                total_scenarios=int(snap["total_scenarios"]) if snap.get("total_scenarios") else None,
            )

            db.update_snapshot_ev(snap["snapshot_id"], {
                k: result[k]
                for k in ("sell_through", "sell_through_se", "adj_expected_return",
                          "adj_expected_return_per_euro", "low_confidence", "retention_calibrated")
            })


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value).date()
    except (ValueError, TypeError):
        return None


def _floor_scrape_start(game_first_seen: date | None, claims_observation_start: date | None) -> date | None:
    """The later of game-first-seen and claims-scraper-start defines when we
    were actually capable of observing claims for this game."""
    if game_first_seen and claims_observation_start:
        return max(game_first_seen, claims_observation_start)
    return game_first_seen or claims_observation_start


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["full", "claimed"], required=True)
    args = parser.parse_args()

    if args.mode == "full":
        run_full()
    else:
        run_claimed()
