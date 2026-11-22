-- Migration 005 — history of the listing card labels
--
-- The listing shows a badge on each game card: '¡Nuevo!', '¡Novedad!',
-- '¡Últimos días!', '¡Web y App!' or none. game_product_info keeps only the current
-- one; this table keeps every period a game showed a given label, so we can learn
-- what each label means and how long it lasts (e.g. '¡Nuevo!' for brand-new
-- products vs '¡Novedad!' for re-releases of existing ones).
--
-- One row per period: enrich.py inserts a row when a game's label changes and
-- moves last_seen forward while it stays the same. label NULL = no badge.
-- Written only by enrich.py (service_role); public read, like the other tables.
--
-- Run once in the Supabase SQL editor. Idempotent.

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
