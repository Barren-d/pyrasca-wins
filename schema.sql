-- pyRasca database schema
-- Run once in Supabase SQL editor: https://supabase.com/dashboard/project/_/sql

CREATE TABLE games (
    game_id     TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    url         TEXT NOT NULL,
    img_url     TEXT,
    game_start  TIMESTAMPTZ,             -- from span.ocu[data-fecha]
    max_payout  TEXT,
    prices      NUMERIC[],
    multi_price BOOLEAN DEFAULT FALSE,
    active      BOOLEAN DEFAULT TRUE,
    first_seen  TIMESTAMPTZ DEFAULT NOW(),
    last_seen   TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE scrape_runs (
    run_id        UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    run_type      TEXT CHECK (run_type IN ('full', 'claimed')) NOT NULL,
    started_at    TIMESTAMPTZ DEFAULT NOW(),
    completed_at  TIMESTAMPTZ,
    games_scraped INTEGER,
    status        TEXT CHECK (status IN ('running', 'success', 'partial', 'failed'))
);

CREATE TABLE game_snapshots (
    snapshot_id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id                       UUID REFERENCES scrape_runs(run_id),
    game_id                      TEXT REFERENCES games(game_id),
    scraped_at                   TIMESTAMPTZ DEFAULT NOW(),
    price                        NUMERIC NOT NULL,
    max_payout                   TEXT,
    total_scenarios              INTEGER,
    winning_scenarios            INTEGER,
    losing_scenarios             INTEGER,
    expected_return              NUMERIC,
    expected_return_per_euro     NUMERIC,
    adj_expected_return          NUMERIC,
    adj_expected_return_per_euro NUMERIC,
    sell_through                 NUMERIC,
    sell_through_se              NUMERIC,
    low_confidence               BOOLEAN DEFAULT FALSE,
    retention_calibrated         BOOLEAN DEFAULT FALSE,
    ev_recomputed_at             TIMESTAMPTZ,    -- bumped by claimed scrape; chart x-axis source
    html_path                    TEXT
);

CREATE TABLE prize_tiers (
    tier_id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    snapshot_id            UUID REFERENCES game_snapshots(snapshot_id),
    occurrences            INTEGER NOT NULL,
    prize_amount           NUMERIC NOT NULL,
    is_annuity             BOOLEAN DEFAULT FALSE,
    annuity_years          INTEGER,
    annuity_annual_payment NUMERIC
);

CREATE TABLE claimed_prizes (
    claim_id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    first_run_id      UUID REFERENCES scrape_runs(run_id),
    last_run_id       UUID REFERENCES scrape_runs(run_id),
    game_id           TEXT REFERENCES games(game_id),
    game_name         TEXT NOT NULL,
    game_url          TEXT,
    winner            TEXT,
    prize_amount      NUMERIC NOT NULL,
    prize_amount_raw  TEXT NOT NULL,
    claimed_at        TIMESTAMPTZ NOT NULL,
    first_seen        TIMESTAMPTZ DEFAULT NOW(),
    last_seen         TIMESTAMPTZ DEFAULT NOW(),
    prize_tier_id     UUID REFERENCES prize_tiers(tier_id),
    UNIQUE (game_name, winner, prize_amount, claimed_at)
);

-- Indexes for common dashboard queries
CREATE INDEX idx_game_snapshots_game_scraped ON game_snapshots (game_id, scraped_at DESC);
CREATE INDEX idx_claimed_prizes_game_claimed ON claimed_prizes (game_id, claimed_at DESC);
CREATE INDEX idx_claimed_prizes_tier ON claimed_prizes (prize_tier_id) WHERE prize_tier_id IS NOT NULL;

-- ─── Trigger: preserve first_seen / first_run_id and bump last_seen on conflict ─────
--
-- The carousel scrape upserts every row it sees. On INSERT the payload values are kept.
-- On UPDATE we want first_seen and first_run_id to stay frozen (they record when WE
-- first observed the claim) while last_seen tracks when we last saw it in the carousel.
-- last_seen − claimed_at is the empirical retention measurement.

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

-- ─── retention_curve(): empirical retention per prize_amount bucket ─────────────────
--
-- 90th-percentile of (last_seen − claimed_at), excluding entries still visible in the
-- carousel (last_seen ≥ NOW() − 1h means the prize is still on display, so we don't
-- yet know its true exit time). Buckets with < 50 supporting claims are excluded.
--
-- Called by src/analysis/retention.py via supabase rpc().

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
