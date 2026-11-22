-- Migration 004 — Row Level Security on the scraper's tables
--
-- The original schema created these tables without RLS, so Supabase shows them as
-- "Unrestricted": anyone holding the project URL and the anon (public) key could
-- read, insert, update or delete rows through the REST API. The anon key is meant
-- to be public (any browser app ships it), so this must be closed before a public
-- site goes live.
--
-- After this migration: everyone may READ (the data is public: ONCE's own website);
-- only the service_role key may WRITE, because service_role bypasses RLS and no
-- write policy exists for anyone else. The scraper (scrape.py), enrich.py and the
-- current Streamlit dashboard all use the service_role key, so none of them is
-- affected.
--
-- Run once in the Supabase SQL editor. Idempotent.

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


-- ─── Checks: run after the migration; every row should say ok ───────────────────
--
-- SELECT c.relname,
--        CASE WHEN c.relkind = 'v'
--             THEN CASE WHEN 'security_invoker=true' = ANY(c.reloptions) THEN 'ok (view, invoker)'
--                       ELSE 'VIEW BYPASSES RLS' END
--             WHEN c.relrowsecurity THEN 'ok (rls on)'
--             ELSE 'RLS OFF' END AS status
-- FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
-- WHERE n.nspname = 'public' AND c.relkind IN ('r', 'v')
-- ORDER BY 2 DESC, 1;
--
-- SELECT tablename, policyname, roles, cmd FROM pg_policies WHERE schemaname = 'public' ORDER BY 1;
