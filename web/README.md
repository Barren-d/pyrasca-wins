# pyRasca web

The public site: Next.js 16 (App Router, Cache Components), TypeScript and Tailwind.
It replaces the Streamlit dashboard (`app.py`) once it reaches parity.

## Setup

```bash
cd web
npm install
cp .env.example .env.local   # then fill in SUPABASE_URL and SUPABASE_ANON_KEY
npm run dev                  # http://localhost:3000
```

Use Supabase's **public** (anon / publishable) key. The site only reads, through
row-level security; never give it the service_role key.

## How it works

- **Data:** server-side reads of the read-only views from `migrations/006_site_views.sql`
  (`game_overview`, `prize_table`, `recent_wins`), in `src/lib/data.ts`, cached for
  10 minutes. The scraper keeps writing the tables; the site never writes.
- **Languages:** every page lives under `/ca`, `/en` or `/es` (`src/app/[lang]`).
  `src/proxy.ts` sends other paths to the visitor's last-used or browser language.
  Strings are in `src/i18n/dictionaries/*.json`; numbers and dates are formatted per
  language in `src/lib/format.ts`.
