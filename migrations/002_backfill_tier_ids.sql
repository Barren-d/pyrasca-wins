-- Migration 002 — backfill claimed_prizes.prize_tier_id
--
-- Earlier versions of match_prize_tier_ids relied on an embedded-join filter that
-- supabase-py couldn't translate reliably; the result was that historical claims
-- got prize_tier_id = NULL even when an unambiguous match existed.
--
-- This migration retroactively matches NULL claims against the LATEST prize_tier per
-- (game_id, price). If the prize amount is unique to one price tier of the game,
-- prize_tier_id is set; if it appears in multiple price tiers, it stays NULL
-- (genuine ambiguity per condition (b) of the observable tier set in PLAN.md).
--
-- Idempotent — re-running has no effect once all unambiguous claims are matched.

WITH latest_snapshots AS (
    SELECT DISTINCT ON (game_id, price)
           snapshot_id, game_id, price
    FROM   game_snapshots
    ORDER  BY game_id, price, scraped_at DESC
),
candidate_tiers AS (
    SELECT ls.game_id,
           pt.prize_amount,
           pt.tier_id
    FROM   latest_snapshots ls
    JOIN   prize_tiers pt ON pt.snapshot_id = ls.snapshot_id
),
unambiguous_tiers AS (
    -- Exactly one (game_id, prize_amount, tier_id) row across the game's latest
    -- snapshots → the prize amount lives in only one price tier.
    -- (array_agg + subscript: MIN() doesn't support uuid in Postgres.)
    SELECT game_id, prize_amount, (array_agg(tier_id))[1] AS tier_id
    FROM   candidate_tiers
    GROUP  BY game_id, prize_amount
    HAVING COUNT(*) = 1
)
UPDATE claimed_prizes cp
SET    prize_tier_id = ut.tier_id
FROM   unambiguous_tiers ut
WHERE  cp.prize_tier_id IS NULL
AND    cp.game_id      = ut.game_id
AND    cp.prize_amount = ut.prize_amount;

-- Optional sanity check (read-only): for each unmatched claim, count how many
-- distinct price tiers contain that prize amount. > 1 = genuine ambiguity; 0 =
-- prize doesn't exist in any tier (parser issue or game changed).
--
-- WITH latest_snapshots AS (
--     SELECT DISTINCT ON (game_id, price) snapshot_id, game_id, price
--     FROM   game_snapshots ORDER BY game_id, price, scraped_at DESC
-- )
-- SELECT cp.game_id, cp.prize_amount, COUNT(DISTINCT cp.claim_id) AS unmatched,
--        (SELECT COUNT(DISTINCT ls.price)
--         FROM   latest_snapshots ls
--         JOIN   prize_tiers pt ON pt.snapshot_id = ls.snapshot_id
--         WHERE  ls.game_id = cp.game_id AND pt.prize_amount = cp.prize_amount
--        ) AS price_tiers_with_this_amount
-- FROM   claimed_prizes cp
-- WHERE  cp.prize_tier_id IS NULL
-- GROUP  BY cp.game_id, cp.prize_amount;
