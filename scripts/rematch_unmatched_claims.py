"""One-off: re-match claims that have no prize_tier_id.

Claims scraped right after a full run that saved empty snapshots (no prize table)
could not be matched to a tier, because matching only looked at the latest
snapshot. Matching now skips empty snapshots; this script retries the claims left
unmatched, then recomputes EV.

Only fills prize_tier_id where it is NULL; nothing is deleted or overwritten.
Claims whose amount is ambiguous (in more than one price tier) or not in the prize
table stay NULL, exactly as matching would leave them.

Usage (from the repo root):
    python scripts/rematch_unmatched_claims.py           # dry run: report only
    python scripts/rematch_unmatched_claims.py --apply   # write matches + recompute EV
"""
from __future__ import annotations

import argparse
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.stdout.reconfigure(encoding="utf-8")

from src.db.client import get_client
from src.scraper.claimed import match_prize_tier_ids

PAGE = 1000
UPDATE_CHUNK = 200


def load_unmatched() -> list[dict]:
    client = get_client()
    rows: list[dict] = []
    offset = 0
    while True:
        page = (
            client.table("claimed_prizes")
            .select("claim_id, game_id, game_name, prize_amount")
            .is_("prize_tier_id", "null")
            .not_.is_("game_id", "null")
            .order("claim_id")
            .range(offset, offset + PAGE - 1)
            .execute()
            .data
        )
        rows.extend(page)
        if len(page) < PAGE:
            break
        offset += PAGE
    return rows


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="write the matches and recompute EV")
    args = parser.parse_args()

    unmatched = load_unmatched()
    print(f"Unmatched claims: {len(unmatched)}")

    # Match one game at a time so the snapshot lookup stays well under the
    # Supabase 1000-row response limit.
    by_game: dict[str, list[dict]] = defaultdict(list)
    for row in unmatched:
        by_game[row["game_id"]].append(
            {"claim_id": row["claim_id"], "game_id": row["game_id"],
             "game_name": row["game_name"], "prize_amount": float(row["prize_amount"])}
        )

    matches: dict[str, list[str]] = defaultdict(list)  # tier_id -> claim_ids
    per_game: Counter = Counter()
    names: dict[str, str] = {}
    for game_id, claims in by_game.items():
        for claim in match_prize_tier_ids(claims):
            if claim.get("prize_tier_id"):
                matches[claim["prize_tier_id"]].append(claim["claim_id"])
                per_game[game_id] += 1
                names[game_id] = claim["game_name"]

    total = sum(per_game.values())
    print(f"Newly matchable: {total} claims across {len(per_game)} games")
    for game_id, n in per_game.most_common():
        print(f"  {game_id:8} {names[game_id]:32} +{n}")

    if not args.apply:
        print("Dry run — nothing written. Re-run with --apply to save.")
        return

    client = get_client()
    for tier_id, claim_ids in matches.items():
        for i in range(0, len(claim_ids), UPDATE_CHUNK):
            (
                client.table("claimed_prizes")
                .update({"prize_tier_id": tier_id})
                .in_("claim_id", claim_ids[i:i + UPDATE_CHUNK])
                .is_("prize_tier_id", "null")  # never overwrite an existing match
                .execute()
            )
    print(f"Wrote {total} matches. Recomputing EV…")

    import scrape
    from src.analysis import retention as ret_module
    scrape._recalculate_ev(ret_module.load_empirical_retention())
    print("Done.")


if __name__ == "__main__":
    main()
