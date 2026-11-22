-- Migration 006 — read-only views for the web site (web/)
--
-- The Streamlit dashboard works these numbers out in Python after downloading the
-- raw rows. The Next.js site reads with the public anon key instead, so the views
-- below return each page's numbers ready-made, in one small query per page:
--
--   latest_snapshots  the latest snapshot with a prize table, per game × ticket price
--   game_overview     one row per game × ticket price: return, odds, sell-through,
--                     top prize and how many we saw claimed, official dates
--                     (Home, All games, Inactive games, game page header)
--   prize_table       each price's prize tiers with the claims seen per tier
--                     (game page)
--   recent_wins       every claim with its ticket price and prize multiple
--                     (Recent wins, Home carousel)
--
-- Read only: nothing here writes, and scrape.py, enrich.py and app.py don't use these
-- views. security_invoker: each view applies the reader's RLS (public read).
--
-- Returns are given both ways: *_return_per_euro as stored (net, e.g. -0.26) and
-- *_payback_per_euro as the site shows it (what €1 pays back on average, e.g. 0.74).
--
-- Run once in the Supabase SQL editor. Idempotent.

-- ─── Indexes for the views ────────────────────────────────────────────────────────

-- latest_snapshots: newest non-empty snapshot per game × price
CREATE INDEX IF NOT EXISTS idx_snapshots_latest
    ON game_snapshots (game_id, price, scraped_at DESC) WHERE total_scenarios IS NOT NULL;
-- claims seen per prize amount (prize_table, game_overview)
CREATE INDEX IF NOT EXISTS idx_claimed_prizes_game_amount
    ON claimed_prizes (game_id, prize_amount);
-- newest claims across every game (recent_wins)
CREATE INDEX IF NOT EXISTS idx_claimed_prizes_claimed_at
    ON claimed_prizes (claimed_at DESC);

-- ─── latest_snapshots ─────────────────────────────────────────────────────────────
-- Same rule as the dashboard and the claim matcher: skip empty snapshots left by
-- runs whose prize page failed to parse.

CREATE OR REPLACE VIEW latest_snapshots WITH (security_invoker = true) AS
SELECT DISTINCT ON (s.game_id, s.price) s.*
FROM game_snapshots s
WHERE s.total_scenarios IS NOT NULL
ORDER BY s.game_id, s.price, s.scraped_at DESC;

-- ─── prize_table ──────────────────────────────────────────────────────────────────
-- claims_seen counts claims for this game and prize amount. A claim matched to a
-- tier of another ticket price of the same game is not counted here; an unmatched
-- claim (amount shared by several prices) counts for every price with that amount,
-- as in the dashboard.

CREATE OR REPLACE VIEW prize_table WITH (security_invoker = true) AS
SELECT s.game_id,
       s.price,
       s.snapshot_id,
       t.tier_id,
       t.prize_amount,
       t.occurrences,
       t.is_annuity,
       t.annuity_years,
       t.annuity_annual_payment,
       (SELECT count(*)
          FROM claimed_prizes c
          LEFT JOIN prize_tiers    ct ON ct.tier_id = c.prize_tier_id
          LEFT JOIN game_snapshots cs ON cs.snapshot_id = ct.snapshot_id
         WHERE c.game_id = s.game_id
           AND c.prize_amount = t.prize_amount
           AND (cs.price IS NULL OR cs.price = s.price)) AS claims_seen
FROM latest_snapshots s
JOIN prize_tiers t ON t.snapshot_id = s.snapshot_id;

-- ─── game_overview ────────────────────────────────────────────────────────────────
-- One row per game × ticket price, active and inactive (filter on active).
-- Official dates come from game_dates (migration 003) and may be empty.

CREATE OR REPLACE VIEW game_overview WITH (security_invoker = true) AS
WITH top AS (
    -- the top tier only, so claims are counted for one tier per price, not all
    SELECT DISTINCT ON (t.snapshot_id)
           t.snapshot_id, t.prize_amount, t.occurrences, t.is_annuity
    FROM latest_snapshots s
    JOIN prize_tiers t ON t.snapshot_id = s.snapshot_id
    ORDER BY t.snapshot_id, t.prize_amount DESC
)
SELECT g.game_id,
       g.name,
       g.url,
       g.img_url,
       g.active,
       g.game_start,                       -- start shown on ONCE's site
       g.first_seen,                       -- first seen by our scraper
       g.last_seen,                        -- last seen on sale (end, for inactive games)
       cardinality(g.prices) AS price_count,
       s.price,
       s.snapshot_id,
       s.scraped_at,
       COALESCE(s.ev_recomputed_at, s.scraped_at) AS ev_as_of,
       s.total_scenarios                   AS series_size,
       s.winning_scenarios,
       s.winning_scenarios::numeric / NULLIF(s.total_scenarios, 0) AS win_chance,
       s.expected_return_per_euro          AS return_per_euro,
       s.adj_expected_return_per_euro      AS adj_return_per_euro,
       1 + s.expected_return_per_euro      AS payback_per_euro,
       1 + s.adj_expected_return_per_euro  AS adj_payback_per_euro,
       s.sell_through,
       s.sell_through_se,
       s.low_confidence,
       s.retention_calibrated,
       top.prize_amount                    AS top_prize,
       top.is_annuity                      AS top_prize_is_annuity,
       top.occurrences                     AS top_prizes_printed,
       (SELECT count(*)                    -- same rule as prize_table.claims_seen
          FROM claimed_prizes c
          LEFT JOIN prize_tiers    ct ON ct.tier_id = c.prize_tier_id
          LEFT JOIN game_snapshots cs ON cs.snapshot_id = ct.snapshot_id
         WHERE c.game_id = g.game_id
           AND c.prize_amount = top.prize_amount
           AND (cs.price IS NULL OR cs.price = s.price)) AS top_prizes_claimed,
       d.listing_label,
       d.sale_start,
       d.sale_end,
       d.end_source,
       d.end_source_url
FROM games g
JOIN latest_snapshots s  ON s.game_id = g.game_id
LEFT JOIN top            ON top.snapshot_id = s.snapshot_id
LEFT JOIN game_dates d   ON d.game_id = g.game_id;

-- ─── recent_wins ──────────────────────────────────────────────────────────────────
-- Claims don't record the ticket price. It comes from the matched prize tier, or from
-- the game when it has a single price. For a multi-price game whose claim couldn't be
-- matched, ticket_price is NULL and the multiple is taken against the game's highest
-- price, so a "5× or more" filter never shows a win that isn't.

CREATE OR REPLACE VIEW recent_wins WITH (security_invoker = true) AS
SELECT c.claim_id,
       c.game_id,
       c.game_name,
       g.active                AS game_active,
       c.winner,
       c.prize_amount,
       c.prize_amount_raw,
       c.claimed_at,
       COALESCE(cs.price, CASE WHEN cardinality(g.prices) = 1 THEN g.prices[1] END) AS ticket_price,
       c.prize_amount / NULLIF(COALESCE(cs.price,
                                        (SELECT max(p) FROM unnest(g.prices) AS p)), 0) AS prize_multiple
FROM claimed_prizes c
LEFT JOIN games          g  ON g.game_id = c.game_id
LEFT JOIN prize_tiers    ct ON ct.tier_id = c.prize_tier_id
LEFT JOIN game_snapshots cs ON cs.snapshot_id = ct.snapshot_id;

-- ─── Checks (run after the migration) ─────────────────────────────────────────────
-- SELECT count(*), count(*) FILTER (WHERE active) FROM game_overview;   -- one row per game × price
-- SELECT * FROM recent_wins WHERE prize_multiple >= 5 ORDER BY claimed_at DESC LIMIT 10;
-- SELECT * FROM prize_table WHERE game_id = (SELECT game_id FROM games WHERE name = 'X50') ORDER BY price, prize_amount DESC;
