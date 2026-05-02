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
