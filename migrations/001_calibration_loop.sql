-- Migration 001 — wire up the empirical calibration loop
--
-- Apply once in Supabase SQL editor on existing deployments.
-- New deployments get all of this from schema.sql; this file is idempotent so it's
-- also safe to re-run.
--
-- Changes:
--   1. Add game_snapshots.ev_recomputed_at (timestamp of most recent claimed-scrape EV update)
--   2. Add trigger preserving claimed_prizes.first_seen / first_run_id and bumping last_seen
--   3. Add retention_curve() RPC consumed by src/analysis/retention.py

-- ─── 1. ev_recomputed_at ────────────────────────────────────────────────────────────
ALTER TABLE game_snapshots
    ADD COLUMN IF NOT EXISTS ev_recomputed_at TIMESTAMPTZ;

-- ─── 2. claimed_prizes preserve trigger ────────────────────────────────────────────
CREATE OR REPLACE FUNCTION claimed_prizes_preserve_first_seen()
RETURNS TRIGGER AS $$
BEGIN
    NEW.first_seen   = OLD.first_seen;
    NEW.first_run_id = OLD.first_run_id;
    NEW.last_seen    = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS claimed_prizes_first_seen_preserve ON claimed_prizes;
CREATE TRIGGER claimed_prizes_first_seen_preserve
BEFORE UPDATE ON claimed_prizes
FOR EACH ROW EXECUTE FUNCTION claimed_prizes_preserve_first_seen();

-- ─── 3. retention_curve() RPC ──────────────────────────────────────────────────────
CREATE OR REPLACE FUNCTION retention_curve()
RETURNS TABLE(prize_amount NUMERIC, retention_days FLOAT) AS $$
    SELECT prize_amount,
           EXTRACT(EPOCH FROM percentile_disc(0.9) WITHIN GROUP (
               ORDER BY last_seen - claimed_at
           )) / 86400.0 AS retention_days
    FROM claimed_prizes
    WHERE last_seen < NOW() - INTERVAL '1 hour'
    GROUP BY prize_amount
    HAVING COUNT(*) >= 50;
$$ LANGUAGE SQL STABLE;
