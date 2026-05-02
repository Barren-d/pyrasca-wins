# pyRasca

Tracks Spanish ONCE scratch cards (rascas) and surfaces the **best ones to buy right now** in a Streamlit dashboard. Scrapes the live ONCE site for game listings, prize tables, and the public "recent winners" carousel; stores time-series snapshots in Supabase; computes a depletion-adjusted expected return per euro for each game × price.

> **Disclaimer:** none of these games are profitable on average. The point is to find the **least unprofitable** ones at a given moment — i.e., games where the published prize structure plus claimed-prize evidence suggest more than usual remains to be won.

---

## What it computes

For each game × price snapshot, two numbers:

- `EV_base` — expected return per €1 from the prize table alone:
  `Σ (Wᵢ / T) × prizeᵢ / c` where T is total tickets, Wᵢ is winning tickets at tier i, prizeᵢ is the prize value (annuities discounted to PV), c is the ticket price.
- `EV_adj` — same calculation but conditioned on the prizes that have **already been claimed**. If the carousel evidence shows the grand prizes have been won faster than average for this game's age, EV_adj drifts below EV_base. If high-value prizes are over-represented in what's still unclaimed, EV_adj rises.

The depletion model is a Poisson rate estimator over the *observable* tier set — tiers whose carousel retention is long enough (relative to the scrape interval) to be reliably observed. See [PLAN.md](PLAN.md) for the full math.

---

## Architecture

```
                ┌──────────────────────────┐
                │  GitHub Actions          │
                │  • full scrape  (daily)  │
                │  • claimed scrape (72m)  │
                └────────────┬─────────────┘
                             │
                             ▼
   ┌──────────────────────────────────────────────┐
   │  scrape.py --mode {full|claimed}             │
   │    src/scraper/  → games, prizes, carousel    │
   │    src/analysis/ → baseline EV, depletion EV │
   │    src/db/       → upsert into Supabase      │
   └────────────┬─────────────────────────────────┘
                │
                ▼
        ┌──────────────────┐         ┌────────────────┐
        │  Supabase (PG)   │ ◄────── │  Streamlit app │
        │  games           │         │  (app.py)      │
        │  game_snapshots  │         │   • Picks      │
        │  prize_tiers     │         │   • All Games  │
        │  claimed_prizes  │         │   • Detail     │
        │  scrape_runs     │         │   • Recent Wins│
        └──────────────────┘         └────────────────┘
```

The full scrape inserts new `game_snapshots` rows daily. The claimed scrape only **updates** the latest snapshot's `adj_expected_return*`, `sell_through*`, and `ev_recomputed_at` fields — so the EV-over-time chart resolution is daily, but each point reflects the most recent claimed-scrape recomputation.

---

## Setup

### 1. Supabase

1. Create a project at [supabase.com](https://supabase.com).
2. In the SQL editor, run [`schema.sql`](schema.sql).
3. Grab the project URL and **service_role** key (Settings → API). Use service_role for the scraper; if you publicly host the dashboard, switch to anon + RLS policies.

### 2. Local environment

```powershell
py -3.12 -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Create `.env` from [`.env.example`](.env.example):

```
SUPABASE_URL=https://your-project-ref.supabase.co
SUPABASE_KEY=your-service-role-key
DEV_CACHE=true        # cache HTML in data/ during local dev
```

For Streamlit, also create `.streamlit/secrets.toml` from [`.streamlit/secrets.toml.example`](.streamlit/secrets.toml.example) with the same values. Both files are gitignored.

### 3. Run the scraper once

```powershell
python scrape.py --mode full
```

This populates games, snapshots, prize tiers, and an initial set of claimed prizes.

### 4. Launch the dashboard

```powershell
streamlit run app.py
```

---

## Usage

```powershell
python scrape.py --mode full      # full pipeline (games + prizes + claimed + EV)
python scrape.py --mode claimed   # claimed scrape + EV recompute only (cheap, frequent)
streamlit run app.py              # dashboard
pytest tests/                     # unit tests for EV/depletion math
```

### Dashboard pages

- **Today's Picks** — top-5 cards ranked by `EV_adj`, filterable by price tier.
- **All Games** — sortable table; click a row to open the game detail.
- **Game Detail** — prize tier breakdown, sell-through gauge, EV-over-time chart, claimed-prizes log. Dropdown in the sidebar to pick a different game.
- **Recent Wins** — global feed across all games, filterable by minimum prize. Includes a "Run Scraper" button for triggering a claimed scrape from the UI (local dev only).

---

## Scheduling

Two GitHub Actions workflows run the scraper:

- [`scrape_full.yml`](.github/workflows/scrape_full.yml) — daily at 06:00 UTC + ≤5 min jitter.
- [`scrape_claimed.yml`](.github/workflows/scrape_claimed.yml) — every 72 minutes (20 runs/day, evenly spaced) + ≤5 min jitter.

Set `SUPABASE_URL` and `SUPABASE_KEY` as repo secrets in **Settings → Secrets and variables → Actions** before pushing. Workflows can also be triggered manually via `workflow_dispatch`.

---

## Calibration

The depletion EV depends on a `retention(prize)` curve — how long, on average, a claim of a given prize size stays visible in the carousel. Until the database has accumulated enough historical observations, the system uses a conservative step-function default:

| Prize amount | Default retention |
|---|---|
| ≥ €10,000 | 30 days |
| ≥ €1,000  | 7 days  |
| ≥ €100    | 1 day   |
| else      | 0       |

Once each prize-amount bucket accumulates ≥50 claims with a non-current `last_seen` (claim has cycled out of the carousel), the [`retention_curve()`](schema.sql#L83) Postgres function takes over and `retention_calibrated` flips to `TRUE`. The dashboard displays a calibration banner until ≥80% of active games are calibrated.

Per-claim observation continues through a database trigger that bumps `last_seen` on every upsert of an existing claim while preserving `first_seen` and `first_run_id`. This is the mechanism that makes empirical retention measurable.

---

## Project structure

```
pyrasca/
├── src/
│   ├── scraper/         games, prizes, carousel parsers + shared HTTP session
│   ├── db/              Supabase client + table writes
│   └── analysis/        EV, retention, depletion math
├── app.py               Streamlit dashboard
├── scrape.py            Pipeline orchestrator (--mode full|claimed)
├── schema.sql           Database DDL — run once on a fresh Supabase project
├── migrations/          Idempotent SQL changes for existing deployments
├── tests/               pytest unit tests for the analysis layer
├── .github/workflows/   Cron-driven scrapes
└── PLAN.md              Detailed design doc (math + implementation notes)
```

---

## Limitations

- **EV_adj is a model estimate, not a measurement.** It assumes uniform random distribution of prizes (regulator-enforced) and approximately constant sales rate (close enough for short windows; biased for games near end-of-life).
- **Carousel retention varies by prize size.** Small wins fall off in minutes; grand prizes persist for weeks. Tiers below the retention floor for our scrape interval are excluded from the depletion signal.
- **Bootstrap period.** Default retention values are guesses; the dashboard surfaces this with a "Calibrating" badge until empirical retention is fitted (~30 days minimum).
- **Sparse-data fallback.** Games with fewer than 5 matched claims or 14 days of scraping history fall back to `EV_adj = EV_base` with `low_confidence = TRUE`.

---

## License

MIT
