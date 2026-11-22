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

-- ─── Row Level Security (migration 004): public read, service_role write ─────────

ALTER TABLE games           ENABLE ROW LEVEL SECURITY;
ALTER TABLE scrape_runs     ENABLE ROW LEVEL SECURITY;
ALTER TABLE game_snapshots  ENABLE ROW LEVEL SECURITY;
ALTER TABLE prize_tiers     ENABLE ROW LEVEL SECURITY;
ALTER TABLE claimed_prizes  ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "public read" ON games;
DROP POLICY IF EXISTS "public read" ON scrape_runs;
DROP POLICY IF EXISTS "public read" ON game_snapshots;
DROP POLICY IF EXISTS "public read" ON prize_tiers;
DROP POLICY IF EXISTS "public read" ON claimed_prizes;
CREATE POLICY "public read" ON games          FOR SELECT TO anon, authenticated USING (true);
CREATE POLICY "public read" ON scrape_runs    FOR SELECT TO anon, authenticated USING (true);
CREATE POLICY "public read" ON game_snapshots FOR SELECT TO anon, authenticated USING (true);
CREATE POLICY "public read" ON prize_tiers    FOR SELECT TO anon, authenticated USING (true);
CREATE POLICY "public read" ON claimed_prizes FOR SELECT TO anon, authenticated USING (true);

-- retention_curve() reads claimed_prizes. It is SECURITY INVOKER (the default), so
-- callers get the read policy above; make that explicit so it can't drift.
ALTER FUNCTION retention_curve() SECURITY INVOKER;

-- ─── Official product data (migration 003, written only by enrich.py) ──────────────
--
-- Enriches the scraped data; scrape.py never touches these. See
-- migrations/003_product_dates.sql for the background.

-- What each game's page and listing card say about the product (website facts,
-- collected by enrich.py, kept out of the scraper's games table)
CREATE TABLE IF NOT EXISTS game_product_info (
    game_id        TEXT PRIMARY KEY REFERENCES games(game_id),
    listing_label  TEXT,          -- card badge, e.g. '¡Últimos días!', '¡Nuevo!'
    product_name   TEXT,          -- internal name stated on the page, e.g. 'Importes iguales 6'
    product_key    TEXT,          -- normalised product_name, for matching
    appendix       TEXT,          -- regulation appendix stated on the page, e.g. 'E-2022-01'
    page_read_at   TIMESTAMPTZ,   -- when product_name / appendix were last read
    label_seen_at  TIMESTAMPTZ    -- when listing_label was last refreshed
);

-- Regulation PDFs already read, so each is fetched once. doc_id hashes URL + listing
-- text: ONCE has reused a PDF file name for a different agreement.
CREATE TABLE IF NOT EXISTS notice_documents (
    doc_id          TEXT PRIMARY KEY,
    url             TEXT NOT NULL,
    kind            TEXT NOT NULL CHECK (kind IN ('launch', 'end')),
    label           TEXT,          -- short reference, e.g. 'Resolución 98/2026'
    title           TEXT,          -- listing text on /reglamentos
    products_found  INTEGER,
    fetched_at      TIMESTAMPTZ DEFAULT NOW()
);

-- One row per product named in a launch or end-of-sale document (official facts)
CREATE TABLE IF NOT EXISTS products (
    product_key   TEXT PRIMARY KEY,
    product_name  TEXT NOT NULL,
    appendix      TEXT,          -- E-… electronic, F-… physical
    sale_start    DATE,          -- first day of sale
    sale_end      DATE,          -- last day of sale
    start_source  TEXT REFERENCES notice_documents(doc_id),
    end_source    TEXT REFERENCES notice_documents(doc_id),
    updated_at    TIMESTAMPTZ DEFAULT NOW()
);

-- The join between a website game and an official product, with its audit trail.
-- enrich.py creates and refreshes 'auto' links; rows with matched_by = 'manual'
-- are corrections and are never overwritten.
CREATE TABLE IF NOT EXISTS game_product_links (
    game_id      TEXT PRIMARY KEY REFERENCES games(game_id),
    product_key  TEXT NOT NULL REFERENCES products(product_key),
    matched_by   TEXT NOT NULL CHECK (matched_by IN ('product_name', 'appendix', 'manual')),
    status       TEXT NOT NULL CHECK (status IN ('auto', 'confirmed', 'rejected')),
    check_notes  TEXT,           -- why a link was rejected, or warnings on an accepted one
    updated_at   TIMESTAMPTZ DEFAULT NOW()
);

-- Row Level Security: everyone may read (the data is public: ONCE's own website and
-- regulation documents); only the service_role key used by enrich.py may write,
-- because service_role bypasses RLS and no write policy exists for anyone else.
ALTER TABLE game_product_info   ENABLE ROW LEVEL SECURITY;
ALTER TABLE notice_documents    ENABLE ROW LEVEL SECURITY;
ALTER TABLE products            ENABLE ROW LEVEL SECURITY;
ALTER TABLE game_product_links  ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "public read" ON game_product_info;
DROP POLICY IF EXISTS "public read" ON notice_documents;
DROP POLICY IF EXISTS "public read" ON products;
DROP POLICY IF EXISTS "public read" ON game_product_links;
CREATE POLICY "public read" ON game_product_info  FOR SELECT TO anon, authenticated USING (true);
CREATE POLICY "public read" ON notice_documents   FOR SELECT TO anon, authenticated USING (true);
CREATE POLICY "public read" ON products           FOR SELECT TO anon, authenticated USING (true);
CREATE POLICY "public read" ON game_product_links FOR SELECT TO anon, authenticated USING (true);

-- What the dashboard and site read: website facts joined to official facts through
-- accepted links only. Games without a link still appear, with their listing label.
-- security_invoker: the view applies the reader's RLS instead of its owner's rights.
CREATE OR REPLACE VIEW game_dates WITH (security_invoker = true) AS
SELECT i.game_id,
       i.listing_label,
       l.product_key,
       p.product_name,
       p.appendix,
       p.sale_start,
       p.sale_end,
       ds.label  AS start_source,
       de.label  AS end_source,
       de.url    AS end_source_url,
       l.matched_by,
       l.status,
       l.check_notes
FROM game_product_info i
LEFT JOIN game_product_links l ON l.game_id = i.game_id AND l.status <> 'rejected'
LEFT JOIN products p           ON p.product_key = l.product_key
LEFT JOIN notice_documents ds  ON ds.doc_id = p.start_source
LEFT JOIN notice_documents de  ON de.doc_id = p.end_source;

-- ─── Listing label history (migration 005, written only by enrich.py) ─────────────

CREATE TABLE IF NOT EXISTS listing_label_history (
    id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    game_id     TEXT NOT NULL REFERENCES games(game_id),
    label       TEXT,                      -- NULL = no badge on the card
    first_seen  TIMESTAMPTZ NOT NULL,      -- first run that saw this label
    last_seen   TIMESTAMPTZ NOT NULL       -- latest run that still saw it
);
CREATE INDEX IF NOT EXISTS idx_label_history_game ON listing_label_history (game_id, first_seen DESC);

ALTER TABLE listing_label_history ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "public read" ON listing_label_history;
CREATE POLICY "public read" ON listing_label_history FOR SELECT TO anon, authenticated USING (true);

-- ─── Site views (migration 006, read only, used by web/) ──────────────────────────
--
-- See migrations/006_site_views.sql for what each view is for.

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
