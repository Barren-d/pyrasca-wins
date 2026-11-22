-- Migration 003 — official product data from ONCE's regulation documents
--
-- ONCE publishes the end of sale of each electronic instant-lottery product at least
-- 30 days ahead (Reglamento Lotería Instantánea, art. 19.4), in PDFs linked from
-- https://www.juegosonce.es/reglamentos. Those documents name products by their
-- internal regulatory name ("Importes iguales 6"); each game's page also states it
-- ("RascaCash (Importes iguales 6) es el juego…").
--
-- These tables ENRICH the scraped data and are written only by enrich.py. The
-- scraper (scrape.py) never reads or writes them, and the games table is unchanged:
-- website facts and official facts stay separate and are joined in the game_dates
-- view. A wrong link is one row in game_product_links, fixed by marking it rejected.
--
-- Run once in the Supabase SQL editor. Idempotent.

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
