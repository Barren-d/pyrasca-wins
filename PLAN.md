# pyRasca — Project Plan

## What It Does

Scrapes the ONCE website to collect scratch card (rasca) prize tables and recently claimed prizes, stores a time-series history in Supabase, and surfaces the analysis in a Streamlit dashboard. The core metric is **expected return per euro** (EV), adjusted over time as grand prizes are claimed and the prize pool depletes.

---

## Stack

| Layer | Tool | Notes |
|-------|------|-------|
| Scraping | `requests` + `beautifulsoup4` | Server-rendered HTML, no JS rendering needed; `game_start` from `span.ocu[data-fecha]` |
| Storage | Supabase (PostgreSQL + Storage) | Free tier, persists across Streamlit Cloud deploys |
| Analysis | `pandas` | EV calculation, depletion adjustment |
| Dashboard | Streamlit | Read-only, connects to Supabase |
| Scheduling | GitHub Actions | Two cron workflows |

---

## Database Schema

```sql
-- Static game metadata, upserted on each full scrape
CREATE TABLE games (
    game_id     TEXT PRIMARY KEY,        -- e.g. "EI6" (from banner image URL)
    name        TEXT NOT NULL,
    url         TEXT NOT NULL,
    img_url     TEXT,
    game_start  TIMESTAMPTZ,             -- ONCE launch date; scraped from span.ocu[data-fecha]
    max_payout  TEXT,                    -- headline prize from listing page
    prices      NUMERIC[],               -- e.g. {1, 2, 5}
    multi_price BOOLEAN DEFAULT FALSE,
    active      BOOLEAN DEFAULT TRUE,
    first_seen  TIMESTAMPTZ DEFAULT NOW(),
    last_seen   TIMESTAMPTZ DEFAULT NOW()
);

-- Log of every scrape execution
CREATE TABLE scrape_runs (
    run_id        UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    run_type      TEXT CHECK (run_type IN ('full', 'claimed')) NOT NULL,
    started_at    TIMESTAMPTZ DEFAULT NOW(),
    completed_at  TIMESTAMPTZ,
    games_scraped INTEGER,
    status        TEXT CHECK (status IN ('running', 'success', 'partial', 'failed'))
);

-- One row per game × price tier × scrape run
CREATE TABLE game_snapshots (
    snapshot_id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id                   UUID REFERENCES scrape_runs(run_id),
    game_id                  TEXT REFERENCES games(game_id),
    scraped_at               TIMESTAMPTZ DEFAULT NOW(),
    price                    NUMERIC NOT NULL,
    max_payout               TEXT,                -- per price tier (differs from games.max_payout)
    total_scenarios          INTEGER,
    winning_scenarios        INTEGER,
    losing_scenarios         INTEGER,
    expected_return          NUMERIC,             -- baseline EV (never changes after creation)
    expected_return_per_euro NUMERIC,             -- baseline EV per euro
    adj_expected_return      NUMERIC,             -- depletion-adjusted EV (recomputed each claimed scrape)
    adj_expected_return_per_euro NUMERIC,         -- depletion-adjusted EV per euro
    sell_through             NUMERIC,             -- p̂ from rate extrapolation, range [0, 1]
    sell_through_se          NUMERIC,             -- Poisson standard error of p̂ (NULL in fallback)
    low_confidence           BOOLEAN DEFAULT FALSE,-- TRUE when fallback prior was used (sparse obs)
    retention_calibrated     BOOLEAN DEFAULT FALSE,-- TRUE iff empirical retention curve was used
    html_path                TEXT                 -- pointer to raw HTML in Supabase Storage
);

-- Individual prize tiers within each snapshot
CREATE TABLE prize_tiers (
    tier_id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    snapshot_id            UUID REFERENCES game_snapshots(snapshot_id),
    occurrences            INTEGER NOT NULL,
    prize_amount           NUMERIC NOT NULL,      -- present value (annuities already discounted)
    is_annuity             BOOLEAN DEFAULT FALSE,
    annuity_years          INTEGER,
    annuity_annual_payment NUMERIC                -- raw annual amount, used for claim matching
);

-- Claimed prizes from the "Últimos premios de rascas" carousel.
-- One row per unique claim; first_seen / last_seen accumulate across scrapes
-- so retention(prize) can be estimated as last_seen − claimed_at.
CREATE TABLE claimed_prizes (
    claim_id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    first_run_id      UUID REFERENCES scrape_runs(run_id),    -- run that first saw this claim
    last_run_id       UUID REFERENCES scrape_runs(run_id),    -- most recent run that saw it
    game_id           TEXT REFERENCES games(game_id),
    game_name         TEXT NOT NULL,
    game_url          TEXT,
    winner            TEXT,                       -- anonymised initials only e.g. "V.L.M."
    prize_amount      NUMERIC NOT NULL,           -- parsed amount
    prize_amount_raw  TEXT NOT NULL,              -- raw text e.g. "96.000 € al año"
    claimed_at        TIMESTAMPTZ NOT NULL,       -- from carousel, minute precision
    first_seen        TIMESTAMPTZ DEFAULT NOW(),  -- our first scrape that saw this claim
    last_seen         TIMESTAMPTZ DEFAULT NOW(),  -- last scrape that still showed it; bumped each run
    prize_tier_id     UUID REFERENCES prize_tiers(tier_id),  -- nullable, matched where unambiguous
    UNIQUE (game_name, winner, prize_amount, claimed_at)     -- deduplication across runs
);
```

### Linking claimed prizes to prize tiers

- Match on `game_id + prize_amount` for regular prizes
- Match on `game_id + annuity_annual_payment` for annuity prizes
- `prize_tier_id` is populated where the match is unambiguous (grand prizes are almost always unique per game)
- Small prizes that appear across multiple price tiers are left as `NULL`

### Upsert behaviour for `claimed_prizes`

Each carousel scrape iterates the displayed entries and for each:

```sql
INSERT INTO claimed_prizes (...) VALUES (...)
ON CONFLICT (game_name, winner, prize_amount, claimed_at)
DO UPDATE SET last_seen = NOW(), last_run_id = excluded.last_run_id;
```

This keeps one row per unique claim, with `first_seen` set on insertion and `last_seen`
bumped on every subsequent scrape that still shows the claim.

### Empirical retention measurement

`retention(prize)` is estimated from the accumulated `claimed_prizes` table:

```sql
-- per prize-amount bucket, the high-percentile time the carousel held the entry
SELECT prize_amount, percentile_disc(0.9) WITHIN GROUP (ORDER BY last_seen − claimed_at)
FROM claimed_prizes
WHERE last_seen < NOW() − INTERVAL '1 hour'   -- exclude entries still in the carousel
GROUP BY prize_amount;
```

The 90th percentile is used (not the max) to be robust to claims that disappear faster
than expected due to slot exhaustion. Until the database accumulates ≥ 1 month of data,
the EV pipeline uses a step-function default: `retention(prize) = 7 days if prize ≥ €50,
else 0`.

---

## Known Logic Bugs (to fix in scraper rewrite)

1. **Price matching false positives** — `f"{price}0 €"` causes `price="1"` to match `"10 €"` headers. Fix: only apply the `0`-suffix match when price contains a decimal (i.e. `","` in price string).
2. **No break after price match** — loop overwrites with the last match rather than the first. Fix: `break` after finding the correct section.
3. **`int()` on annuity payment** — should be `float()` to handle decimal annual amounts.
4. **`discount_rate` dead parameter** — `extract_scenario_pairs` accepts it but never passes it to `extract_annuity_scenario`. Fix: pass it through.
5. **Multi-price average bias** — games with multiple price tiers appear multiple times in the average EV calculation. Fix: group by game when computing averages.

---

## Project Structure

```
pyRasca/
│
├── src/
│   ├── scraper/
│   │   ├── __init__.py
│   │   ├── session.py        # shared requests.Session with UA rotation + polite sleep
│   │   ├── games.py          # scrapes listing page → games table
│   │   ├── prizes.py         # scrapes each game page → game_snapshots + prize_tiers
│   │   └── claimed.py        # scrapes "Últimos premios" carousel → claimed_prizes
│   │
│   ├── db/
│   │   ├── __init__.py
│   │   ├── client.py         # Supabase client initialisation
│   │   └── write.py          # insert / upsert for each table
│   │
│   └── analysis/
│       ├── __init__.py
│       ├── ev.py             # EV calculation (fixed from notebook)
│       └── depletion.py      # adjusts EV using claimed prizes
│
├── app.py                    # Streamlit entry point
├── scrape.py                 # pipeline entry point (--mode full | claimed)
│
├── data/                     # local HTML cache for dev (gitignored, flat)
│
├── .env                      # local credentials (gitignored)
├── .streamlit/
│   └── secrets.toml          # Streamlit Cloud credentials
├── requirements.txt
└── .github/
    └── workflows/
        ├── scrape_full.yml   # daily
        └── scrape_claimed.yml # hourly
```

---

## Pipeline

### Full scrape (daily)

```
scrape.py --mode full
    │
    ├── 1. open scrape_run  (run_type='full', status='running')
    ├── 2. scraper/games.py     → upsert games
    ├── 3. scraper/prizes.py    → insert game_snapshots + prize_tiers (per game × price)
    ├── 4. scraper/claimed.py   → upsert claimed_prizes + match prize_tier_id
    ├── 5. analysis/depletion.py → recalculate EV, update game_snapshots
    └── 6. close scrape_run     (status='success' | 'partial' | 'failed')
```

### Claimed scrape (hourly)

```
scrape.py --mode claimed
    │
    ├── 1. open scrape_run  (run_type='claimed', status='running')
    ├── 2. scraper/claimed.py   → upsert claimed_prizes + match prize_tier_id
    ├── 3. analysis/depletion.py → recalculate EV, UPDATE latest game_snapshots row
    └── 4. close scrape_run     (status='success' | 'failed')
```

### `game_snapshots` update semantics

The full scrape **inserts** one new `game_snapshots` row per game × price (with child
`prize_tiers` rows). The claimed scrape **updates** the `adj_*` and `sell_through` fields
on the most recent snapshot row for each game × price — it does **not** insert new rows.

```sql
-- depletion.py identifies the target row as:
SELECT snapshot_id FROM game_snapshots
WHERE game_id = :game_id AND price = :price
ORDER BY scraped_at DESC
LIMIT 1;

-- then updates in-place:
UPDATE game_snapshots
SET adj_expected_return          = :ev_adj,
    adj_expected_return_per_euro = :ev_adj_per_euro,
    sell_through                 = :p_hat,
    sell_through_se              = :se,
    low_confidence               = :low_confidence,
    retention_calibrated         = :retention_calibrated
WHERE snapshot_id = :snapshot_id;
```

Consequence for the EV chart: time-series resolution is **daily** (one point per full
scrape). The chart shows `EV_adj` as it stood at the end of each calendar day, not at
each hourly claimed run. This is sufficient — prize depletion signals are meaningful over
days, not hours.

The `run_id` on each snapshot always points to the full scrape run that created the row,
not the most recent claimed run. If the provenance of the latest claimed update matters,
use `scrape_runs` joined via the most recent `claimed` run timestamp.

---

## Scheduling & Anti-Detection

### GitHub Actions workflows

```yaml
# scrape_full.yml — daily at 6am UTC + random offset up to 2 hours
on:
  schedule:
    - cron: '0 6 * * *'
steps:
  - name: Random delay
    run: sleep $((RANDOM % 7200))
  - run: python scrape.py --mode full

# scrape_claimed.yml — top of every hour + random offset up to 20 mins
on:
  schedule:
    - cron: '0 * * * *'
steps:
  - name: Random delay
    run: sleep $((RANDOM % 1200))
  - run: python scrape.py --mode claimed
```

### Local HTML cache (`DEV_CACHE`)

When `DEV_CACHE=true` in `.env`, `session.py` serves pages from `data/` instead of
fetching live. Cache filenames are deterministic so the same URL always maps to the same
file:

```
data/rascas.html                  ← listing page
data/EI6.html                     ← per-game prize page (slug from URL)
data/ultimos-premios-rascas.html  ← carousel page
```

Behaviour:
- **Cache hit**: return stored HTML, skip the HTTP request and polite sleep entirely.
- **Cache miss**: fetch live, write response to the cache file, then return it.
- **`DEV_CACHE` unset or `false`**: always fetch live; never read or write the cache.

GitHub Actions workflows never set `DEV_CACHE`, so production always fetches fresh pages.

```python
DEV_CACHE = os.getenv("DEV_CACHE", "false").lower() == "true"

def _cache_path(url: str) -> Path:
    slug = url.rstrip("/").split("/")[-1] or "index"
    return Path("data") / (slug + ".html")

def get(url: str) -> str:
    path = _cache_path(url)
    if DEV_CACHE and path.exists():
        return path.read_text(encoding="utf-8")
    html = _session.get(url).text
    if DEV_CACHE:
        path.write_text(html, encoding="utf-8")
    return html
```

Caching is fully transparent to callers — `games.py`, `prizes.py`, and `claimed.py` all
call `session.get(url)` with no knowledge of the cache.

---

### Request-level anti-detection (`src/scraper/session.py`)

- Rotate between 4 realistic browser User-Agent strings
- Set `Accept-Language: es-ES`, `Referer: https://www.juegosonce.es/`
- Random sleep between requests: `uniform(1.5, 4.5)` seconds
- Use `requests.Session` to maintain cookies across requests

---

## EV Calculation

All EVs represent **expected net return per ticket purchased** — the expected gain or loss
in euros after paying the ticket price. A value of −0.30 means an expected loss of €0.30
per ticket.

---

### Notation

| Symbol | Meaning |
|---|---|
| `T` | Total tickets in the print run (`total_scenarios`) |
| `Wᵢ` | Winning tickets at prize tier i (`prize_tier.occurrences`) |
| `W` | `Σᵢ Wᵢ`, total winning tickets |
| `L` | `T − W`, total losing tickets |
| `prizeᵢ` | Gross prize value at tier i (PV for annuities) |
| `c` | Ticket price |
| `t_launch` | Game launch date (from listing page) |
| `t_start` | Date of first scrape that included this game |
| `t_now` | Current date |
| `elapsed_days` | `t_now − t_launch` |
| `scraping_days` | `t_now − t_start` |
| `Cᵢ` | Tier-i claims observed in the carousel during `[t_start, t_now]` |
| `retention(p)` | Empirical carousel retention duration for prize amount `p` (days) |
| `scrape_interval` | Cron period for the claimed-scrape job (1 hour) |
| `O` | Observable tier set — see "Observable tier set" section for definition |
| `W_eff(i)` | Effective observation window in days (per tier) |
| `Ĉᵢ_lifetime` | Estimated cumulative claims at tier i since launch |
| `p` | True current sell-through fraction (unknown) |
| `p̂` | Estimated sell-through fraction |

---

### Probability model

Spanish lottery regulation requires winning tickets to be uniformly distributed at random
throughout the print run. Under this **uniform distribution assumption** every ticket is
independently a tier-i winner with probability `Wᵢ/T` (sampling-without-replacement
corrections are negligible since `Wᵢ ≪ T`).

We assume tickets are sold at a roughly constant rate `r` tickets/day from launch:
`S(t) = r × (t − t_launch)`. Under uniform distribution + constant rate, claims at each
tier follow an independent Poisson process:

```
Cᵢ(window)  ~  Poisson(Wᵢ × r × |window| / T)
```

These two assumptions — uniform distribution and constant sales rate — are the foundation
of everything that follows. The first is regulator-enforced. The second is approximate;
its limitations are addressed at the end of this section.

---

### Baseline EV (from prize table)

```
EV_base = Σᵢ (Wᵢ / T) × prizeᵢ  −  c
```

Derivation: the expected return per ticket is `Σᵢ (Wᵢ/T) × prizeᵢ` (gross winnings) minus
the cost `c`. The losing-scenario term `(L/T) × (−c)` cancels into the constant `−c`
because `Σᵢ Wᵢ + L = T`. `losing_scenarios` is still stored in `game_snapshots` for the
dashboard.

#### Annuity prizes

ONCE awards some prizes as annual payments rather than a lump sum. `prizeᵢ` for an annuity
is the present value of the payment stream:

```
PV = PMT × (1 − (1 + r)^−n) / r,    r = DISCOUNT_RATE = 0.03
```

Assumption: end-of-year payments (ordinary annuity). If ONCE pays at start-of-year
(annuity-due), multiply by `(1 + r)`. Raw `annuity_years` and `annuity_annual_payment`
are preserved in `prize_tiers` so PV can be recomputed if `DISCOUNT_RATE` changes.

---

### Observation model — size-dependent carousel retention

The "Últimos premios de rascas" carousel is a fixed-capacity (~75 slot) display showing
recent winners. **Retention scales strongly with prize size**: small prizes are FIFO'd
within minutes; grand prizes persist for weeks. Empirical data from a single scrape
(2026-05-02 14:06) confirms this:

| Prize amount | Oldest entry visible | Min retention |
|---|---:|---:|
| €0.50–€4 | minutes ago | ~1 min |
| €5–€15 | ~10–15 min ago | 10–15 min |
| €20–€30 | ~20–30 min ago | 20–30 min |
| €50–€100 | 2–3 hours ago | 2–3 hours |
| €250–€500 | 4 days ago | ≥ 4 days |

The carousel reserves slots for noteworthy prizes — older €500 entries persist through
the constant flood of small claims. The implication is that **there is no single
threshold τ above which all claims are observed**; observability is governed by a
continuous `retention(prize)` curve.

#### Empirical retention measurement

Retention is directly measurable from our own scrape history. Each scrape records the
full carousel snapshot. Every claim observed has a `first_seen` and `last_seen` across
scrapes. After a few weeks of hourly scraping, `last_seen − claimed_at` per claim gives
an unbiased estimate of `retention(prizeᵢ)` for any tier seen in the carousel.

Initial implementation, before empirical data accumulates, uses a tiered default
calibrated against the observed retention curve:

```
retention(prize) = {
    30 days  if  prize ≥ €10000      (grand prizes)
     7 days  if  €1000 ≤ prize < €10000
     1 day   if  €100  ≤ prize < €1000
     0       otherwise
}
```

This is more conservative than a flat `7 days for prize ≥ €50` — the empirical 2–3 hour
retention for €50–€100 tier means treating them as having 7 days of observation depth
would massively overstate `W_eff` and bias `p̂` downward. The €100 floor matches the
4-hour safety margin for hourly scraping. Refine after ≥ 1 month of empirical data.

#### Bootstrap-period bias (operational caveat)

During the first month of operation, `EV_adj` is computed against **uncalibrated**
default retention values. The defaults are deliberately conservative but they are
guesses, and the bias is one-directional:

- Defaults that overstate true retention → `W_eff` too long → `p̂` underestimated →
  `EV_adj` skewed *toward* `EV_base` (the depletion signal is muted).
- Defaults that understate true retention → `W_eff` too short → `p̂` overestimated →
  `EV_adj` skewed *away from* `EV_base` (the depletion signal is amplified).

The bias is most pronounced for **mid-tier prizes (€100–€1000)** where retention
varies most across games and our prior is least informative.

Implementation requirement: every `game_snapshots` row carries
`retention_calibrated BOOLEAN`:
- `FALSE` — bootstrap period; default tiered retention used
- `TRUE` — empirical retention curve from `claimed_prizes` history was used

The retention pipeline switches the flag from `FALSE` to `TRUE` automatically once the
SQL percentile query (line 128) returns a row with at least 50 supporting claims for
the relevant prize bucket. Until then, the dashboard must surface the bootstrap state
visibly (see Streamlit Dashboard section).

#### Effective observation window per tier

For each tier i, our first scrape captures claims from up to `retention(prizeᵢ)` days
before scraping started — but never further back than the game itself launched:

```
W_eff(i) = min( elapsed_days,  scraping_days + retention(prizeᵢ) )
```

The `min(elapsed_days, …)` clamp is critical for new games. Without it, a 2-day-old game
with `retention(grand) = 30 days` would have `W_eff = 32 > elapsed_days = 2`, claiming
observation history before the game existed and producing `Ĉᵢ_lifetime < Cᵢ` (logically
impossible).

For grand prizes with multi-week retention on long-running games, the first scrape alone
provides weeks of historical observation — a real informational advantage the model
exploits, not just tolerates.

#### Observable tier set

A tier is **observable** iff three conditions hold:

```
O = { i :   retention(prizeᵢ) ≥ k × scrape_interval     (a) retention sufficient
        ∧   prize_amountᵢ is unique within the game     (b) claims match unambiguously
        ∧   Cᵢ is matched (prize_tier_id non-NULL)      (c) data is usable
}      with k ≥ 4
```

Condition (a) ensures we capture essentially every claim between scrapes. With hourly
scraping and `k = 4`, retention must be ≥ 4 hours.

Condition (b) ensures a carousel entry can be attributed to a specific (game, price)
snapshot. If a €100 prize appears in both the €1 and €5 price tiers of the same game, a
€100 carousel claim is ambiguous and `prize_tier_id` is NULL. Such tiers are excluded
from `O` regardless of retention.

Condition (c) is the operational version of (b) — the join from `claimed_prizes` to
`prize_tiers` must succeed.

For tiers outside `O`, expected remaining occurrences are computed from the model
(`Wᵢ × (1 − p̂)`), not from `Cᵢ`.

#### Implementing condition (b) — cross-price-tier uniqueness check

Condition (b) requires knowing whether a given `prize_amount` appears in more than one
price tier **for the same game**. This is a cross-snapshot check. The correct query runs
once per full scrape after all `prize_tiers` rows are inserted, and sets
`prize_tier_id = NULL` on any `claimed_prizes` row where the amount is ambiguous:

```sql
-- Step 1: identify ambiguous prize amounts (appear in > 1 price tier for same game)
WITH ambiguous AS (
    SELECT pt.game_id, pt.prize_amount
    FROM   prize_tiers pt
    JOIN   game_snapshots gs ON pt.snapshot_id = gs.snapshot_id
    WHERE  gs.scraped_at = (                         -- latest snapshot per game × price
               SELECT MAX(gs2.scraped_at) FROM game_snapshots gs2
               WHERE gs2.game_id = gs.game_id AND gs2.price = gs.price
           )
    GROUP  BY pt.game_id, pt.prize_amount
    HAVING COUNT(DISTINCT gs.price) > 1              -- same amount in multiple price tiers
)
-- Step 2: null out prize_tier_id on affected claimed_prizes
UPDATE claimed_prizes cp
SET    prize_tier_id = NULL
FROM   ambiguous a
WHERE  cp.game_id    = a.game_id
AND    cp.prize_amount = a.prize_amount;
```

This runs as part of the full scrape pipeline (step 4, after prize_tiers are written).
The hourly claimed scrape also re-runs the UPDATE so that newly inserted claims for
ambiguous amounts are immediately nulled out before depletion.py reads them.

---

### Sell-through estimation — rate extrapolation with per-tier windows

For each observable tier, the rate model gives:

```
Cᵢ  ~  Poisson( Wᵢ × r × W_eff(i) / T ),    i ∈ O
```

Note `W_eff(i)` differs across tiers — grand prizes have longer effective windows than
medium prizes. The MLE for the global daily sales rate `r` weights each tier by its
window:

```
r̂ = (Σ_{i∈O} Cᵢ × T) / (Σ_{i∈O} Wᵢ × W_eff(i))
```

Extrapolating to current sell-through fraction:

```
p̂ = min(1, r̂ × elapsed_days / T)
   = min(1, (Σ_{i∈O} Cᵢ × elapsed_days) / (Σ_{i∈O} Wᵢ × W_eff(i)))
```

#### Why this is the right form

- Eliminates carousel selection bias: only tiers we can reliably observe contribute.
- Eliminates the hand-tuned `μ_lifetime`: the observed claim rate IS the rate estimator.
- Correctly weights tiers by their observation depth: grand prizes contribute more
  evidence per claim because `W_eff(grand) >> W_eff(medium)`, and that's exactly what
  the denominator reflects.
- For new games where `t_start ≈ t_launch` and `retention << scraping_days`,
  `W_eff(i) ≈ scraping_days` for all tiers and the formula reduces to
  `(Σ Cᵢ / Σ Wᵢ) × (elapsed_days / scraping_days)`.

#### Standard error of `p̂`

`Σ_{i∈O} Cᵢ` is a sum of independent Poissons and is itself Poisson, so
`Var(Σ Cᵢ) = E[Σ Cᵢ] ≈ Σ Cᵢ`. Treating `Wᵢ` and `W_eff(i)` as known constants:

```
D     = Σ_{i∈O} Wᵢ × W_eff(i)              (known)
p̂     = Σ_{i∈O} Cᵢ × elapsed_days / D
SE(p̂) = √(Σ_{i∈O} Cᵢ) × elapsed_days / D
```

Stored alongside `p̂` so the dashboard can display confidence bands.

#### Fallback for sparse observations

If `Σ_{i∈O} Cᵢ < 5` or `scraping_days < 14`, the rate estimator is too noisy to trust.
In this case:

1. Compute `p̂ = min(1, elapsed_days / 1825)` (weakly informative age prior; median
   lifetime ≈ 5 years, refined as retired games accumulate). Store this in
   `sell_through` for display purposes only.
2. **Set `EV_adj = EV_base` and `adj_expected_return_per_euro = expected_return_per_euro`** —
   no reliable depletion signal is available, so return the baseline. Do NOT mix observed
   `Cᵢ` (window-bounded) with the prior `p̂` (lifetime-extrapolated); they are on different
   scales and the result would be incoherent.
3. Set `low_confidence = TRUE`.

Once enough observations accumulate (`Σ Cᵢ ≥ 5` and `scraping_days ≥ 14`), the rate
estimator takes over and `EV_adj` begins to deviate from `EV_base`.

---

### Depletion-adjusted EV

Compute the expected return for a ticket bought today from the remaining pool. Tiers split
by observability.

**Observable tiers (i ∈ O)**: extrapolate observed claims to a lifetime estimate, capped
at the tier's total occurrences:

```
Ĉᵢ_lifetime = min( Wᵢ,  Cᵢ × elapsed_days / W_eff(i) )
```

The extrapolation `Cᵢ × elapsed/W_eff` converts our window-bounded observation into the
model-based estimate of cumulative claims since launch — unbiased under the constant-rate
assumption when `Cᵢ << Wᵢ`. The `min(Wᵢ, …)` cap prevents nonsense for low-occurrence
tiers (e.g. a single grand prize where one observation extrapolates above 1).

**Non-observable tiers (i ∉ O)**: model-based estimate.

```
Expected remaining: Wᵢ × (1 − p̂)
```

**Remaining pool**: `remaining_T = T × (1 − p̂)`.

```
EV_adj = Σ_{i∈O}  (Wᵢ − Ĉᵢ_lifetime) / (T(1 − p̂)) × prizeᵢ
       + Σ_{i∉O}  Wᵢ / T × prizeᵢ
       −  c
```

For non-observable tiers the `(1 − p̂)` factors cancel: their contribution to `EV_adj`
equals their contribution to `EV_base`. **All depletion signal lives in the observable
tiers** — and within each, the signal is the per-tier observed claim rate vs the global
average.

#### Why splitting tiers by observability matters

If we naively used `remaining_Wᵢ = Wᵢ − Cᵢ` for all tiers (including unobservable
ones), small tiers would have `Cᵢ = 0` (carousel doesn't see them in time), giving
`Wᵢ / (T(1 − p̂)) × prizeᵢ` = `1/(1 − p̂) × baseline_contributionᵢ`. As `p̂` grows, the
unobservable-tier contributions inflate, and since small prizes dominate the value of
most prize tables, `EV_adj` would drift *above* `EV_base` as the game depletes — the
opposite of the intended signal. Splitting by observability fixes this.

If we used `Cᵢ` directly (not extrapolated) for observable tiers, we would underestimate
depletion for old games whose true cumulative claims dwarf our observation window.
`Ĉᵢ_lifetime = Cᵢ × elapsed_days / W_eff(i)` fixes this.

---

### Differential depletion decomposition

The deviation from baseline simplifies cleanly:

```
EV_adj − EV_base = Σ_{i∈O} (Wᵢ × p̂ − Ĉᵢ_lifetime) / (T(1 − p̂)) × prizeᵢ
```

Per observable tier:
- `Ĉᵢ_lifetime ≈ Wᵢ × p̂` (depleting at the global average rate): zero contribution.
- `Ĉᵢ_lifetime > Wᵢ × p̂` (faster than average): negative → EV worsens.
- `Ĉᵢ_lifetime < Wᵢ × p̂` (slower than average): positive → EV improves.

Equivalently, tier i is anomalously depleted iff its per-tier rate
`Cᵢ × T / (Wᵢ × W_eff(i))` exceeds the global rate `r̂`. The MLE for `r̂` averages all
observable tiers exactly, so the decomposition is mean-zero across `O` only when all
tiers deplete uniformly.

In words: **EV deviates from baseline only when prize tiers deplete differentially**.
Grand prizes (small `Wᵢ`, large `prizeᵢ`) being claimed disproportionately fast is the
canonical bad-news signal, and propagates strongly because `prizeᵢ` is large.

---

### EV per euro

```
EV_per_euro = EV / c
```

Normalises for ticket price so games at different price points are directly comparable.
Baseline stored in `game_snapshots.expected_return_per_euro`; depletion-adjusted in
`game_snapshots.adj_expected_return_per_euro`.

---

### Implementation notes

- **Numerical safety**: clamp `p̂` to `[0, 0.9999]` before any division by `(1 − p̂)`.
  An estimated sell-through of exactly 1.0 is meaningless (game over) and would crash
  the formula. If `p̂ = 1.0` after extrapolation, store it but skip `EV_adj` and set
  `low_confidence = TRUE`.
- **Order of operations**: compute `W_eff(i)` first (with the `min(elapsed_days, …)`
  clamp), then `Ĉᵢ_lifetime` (with the `min(Wᵢ, …)` clamp), then `EV_adj`. The two
  clamps are not redundant — `W_eff` clamp protects against impossible windows for new
  games; `Ĉᵢ_lifetime` clamp protects against extrapolation overshoot for low-`Wᵢ` tiers.
- **Multi-price games and shared prize amounts**: if a game has multiple price tiers and
  the same `prize_amount` appears in more than one of them, claims for that amount have
  `prize_tier_id = NULL` and are excluded from `O` for *every* snapshot of that game.
  This loses statistical evidence but biases conservatively (toward `EV_adj = EV_base`).
  Future improvement: pro-rate ambiguous claims across price tiers by `Wᵢ` weight.
- **Fallback SE**: when `low_confidence = TRUE`, store `sell_through_se = NULL`. The
  age-prior `p̂` has no Poisson sampling distribution.
- **`claimed_at` is redemption time**: the carousel timestamp is when the prize was
  redeemed, not when the ticket was sold. For instant scratch cards the lag is small
  (minutes to hours); the constant-rate model treats them as equivalent. Documented in
  the limitations table.

---

### Limitations

| Assumption | Risk if violated | Mitigation |
|---|---|---|
| Constant sales rate | If sales decline as game ages, `p̂` overestimates current sell-through | Test rate stability across the scraping window; fit non-constant rate later if needed |
| Uniform prize distribution | Regulator-enforced; should hold | None needed |
| `retention(prize)` is correctly calibrated | If retention is overestimated, `W_eff(i)` is too long, `p̂` underestimated; if underestimated, `O` includes tiers we actually miss | Measure retention empirically from `last_seen − claimed_at` per claim across scrape history |
| Scrape interval < retention for `i ∈ O` | If we scrape less often than retention for any tier in `O`, claims fall through the gap | Hourly scraping with `O` filtered to `retention ≥ 4h` gives 4× safety margin |
| Claim-to-sale lag is short | If winners delay claiming for weeks, `p̂` is biased downward | Probably small for scratch cards (instant win) |
| `Cᵢ` matched correctly | Ambiguous matches → `prize_tier_id = NULL`; excluded from `Σ Cᵢ` | `O` is chosen so all tiers in `O` have unambiguous prize amounts |
| Carousel slot capacity not exceeded for `i ∈ O` | A burst of grand-prize wins could displace older grand-prize entries before we scrape them | Empirically bounded — the observed carousel reserves slots for noteworthy prizes; monitor for evidence of grand-tier gaps |

---

## Streamlit Dashboard (`app.py`)

The dashboard answers one primary question for the end user: **"Which rasca should I buy right now?"**
Everything is organised around that goal.

---

### Layout overview

```
┌─────────────────────────────────────────────────────┐
│  [Bootstrap banner — shown only during first month]  │
│  "EV adjustments calibrating — ~30 days remaining"   │
├──────────┬──────────────────────────────────────────-┤
│  Nav     │  Today's Picks  |  All Games  |  [game]   │
│  sidebar │                                            │
│  (price  │                                            │
│  filter) │         Main content area                  │
└──────────┴────────────────────────────────────────────┘
Footer: last scrape time · status · Recent Wins feed
```

---

### View 1 — Today's Picks (landing page)

**Purpose**: answer "I have €X — what should I buy?" in one screen.

**Price filter** (sidebar): buttons for each available ticket price (€0.50 / €1 / €2 / €3 / €5 / All). Filters the cards below.

**Top 3–5 game cards**, ranked by `adj_expected_return_per_euro` descending. Each card shows:

```
┌───────────────────────────────────────────────────┐
│  [game thumbnail]   El Millón · €2                │
│                                                   │
│  Return per €1:  €0.84  ←  was €0.82 (↑ 2.4%)   │
│                  ▓▓▓▓▓▓▓▓▓▓▓▓░░░░░░  42% sold    │
│                                                   │
│  ✦ Grand prize (€1,000,000) still in play         │  ← green if available
│  ✦ 2nd prize (€50,000): 2 of 3 remaining         │  ← or "CLAIMED" in red
│                                                   │
│  [Confidence badge: Healthy / Calibrating / Sparse]│
└───────────────────────────────────────────────────┘
```

**Top-prize status logic** (for the card's prize lines):
- Identify the top 2 `prize_tiers` rows for this game × price, ordered by `prize_amount` DESC.
- For each: join `claimed_prizes` on `(game_id, prize_amount)` and count distinct claims vs `occurrences`.
  - `claims = 0` → "still in play" (green)
  - `0 < claims < occurrences` → "N of M remaining" (amber)
  - `claims >= occurrences` → "CLAIMED" (red, strikethrough)
- For observable tiers use `Ĉᵢ_lifetime` (rounded down) instead of raw `COUNT(*)` to avoid undercount
  from the observation window.

**ΔEV arrow**: compare `adj_expected_return_per_euro` in the latest snapshot vs 7 days prior.

**Sell-through bar**: fill width = `sell_through`; shade the last `± sell_through_se` range in lighter
colour to show uncertainty. Do not display the numeric SE — the shaded bar conveys it intuitively.

---

### View 2 — All Games table

**Purpose**: power users who want to compare all games and sort by what matters to them.

Columns (sortable):

| Column | Source | Notes |
|---|---|---|
| Game | `games.name` + thumbnail | Link to View 3 |
| Price | `game_snapshots.price` | |
| EV base | `expected_return_per_euro` | Greyed out — static reference |
| EV adj | `adj_expected_return_per_euro` | **Primary sort** |
| ΔEV (7d) | Latest vs 7-days-prior snapshot | Arrow + % |
| Sold | `sell_through` as % | Progress mini-bar |
| Top prize | Status of the single highest-value tier | "Available" / "N of M left" / "CLAIMED" |
| Confidence | Badge | Healthy / Calibrating / Sparse |

**Row colour coding** by `adj_expected_return_per_euro`:
- `≥ 0.85` → green background
- `0.70–0.85` → yellow
- `< 0.70` → red

Default sort: `adj_expected_return_per_euro` DESC, with `low_confidence` games pushed to the bottom.

---

### View 3 — Game Detail (click-through from either view above)

Accessed by clicking any game name. Shows the full picture for one game.

#### Header strip

Game name · price · thumbnail · last scraped · confidence badge · sell-through gauge (speedometer
0–100% with shaded ±SE band).

#### Prize tier table

Full breakdown of every prize tier. This is where claimed prizes are fully documented:

| Prize | Tickets (Wᵢ) | Est. Claimed | Status | Remaining odds | Contribution to EV_adj |
|---|---|---|---|---|---|
| €1,000,000 | 1 | 0 | **Available** | 1 in 5,000,000 | €0.20 |
| €50,000 | 3 | 1 | **2 of 3 remaining** | 2 in 5,000,000 | €0.02 |
| €500 | 25 | 12 | **13 of 25 remaining** | … | … |
| €5 | 120,000 | — | (unobservable) | … | … |

- "Est. Claimed" = `Ĉᵢ_lifetime` for observable tiers; "—" for unobservable (model-only).
- "Status" is coloured: green (available), amber (partially claimed), red (fully claimed).
- Fully-claimed rows are greyed out and struck through.
- Hovering a row shows the raw `Cᵢ` (window-bounded observations) vs `Ĉᵢ_lifetime`
  (extrapolated) so the user can see how much of the estimate is extrapolation.

#### EV over time chart

Line chart with two series: `EV_base` (flat reference line) and `EV_adj` (evolving).
X-axis: date of snapshot. Y-axis: EV per €1.

The gap between the two lines is the depletion signal. If they diverge downward, the prize
pool is depleting faster than average. If they are flat together, either no depletion signal
has accumulated yet (`low_confidence`) or the game is depleting uniformly.

#### Claimed prizes log (this game only)

Table of all `claimed_prizes` rows for this `game_id`, sorted by `claimed_at` DESC:

| Prize | Date claimed | Days ago | Winner (initials) |
|---|---|---|---|
| €50,000 | 2026-04-15 | 17 days ago | J.M.R. |
| €500 | 2026-04-29 | 3 days ago | V.L. |

Highlight rows where `prize_amount` matches the top 2 prize tiers in bold.

---

### View 4 — Recent Wins feed (sidebar / footer panel)

All `claimed_prizes` across all games, `claimed_at` DESC. Filterable by minimum prize amount
(slider: €0 → €10,000). Default filter: ≥ €500 so the feed shows notable wins, not the constant
flood of small prizes.

Each entry: `[Game name] · €[prize_amount] · [N days ago]`

Wins ≥ €1,000 shown in bold. Wins ≥ €10,000 shown with a coloured highlight.

---

### Confidence indicators

Every game row / card displays a state badge driven by two flags:

| State | Condition | Badge | Meaning |
|---|---|---|---|
| Healthy | `low_confidence = FALSE ∧ retention_calibrated = TRUE` | (none) | Trust the `EV_adj` value |
| Calibrating | `retention_calibrated = FALSE` | `retention calibrating` | Bootstrap period; `EV_adj` may be biased for mid-tier prizes |
| Sparse data | `low_confidence = TRUE` | `insufficient data` | `EV_adj = EV_base`; no depletion signal yet |

**Site-wide bootstrap banner** (shown until `retention_calibrated = TRUE` for ≥ 80% of active games):

> "EV adjustments are calibrating — the retention model will be empirically fitted after ~30 days
> of carousel observation. Grand-prize depletion signals are reliable now; mid-tier signals
> may be biased."

---

### Data health footer

Collapsed by default. Shows:
- Last full scrape: timestamp + status
- Last claimed scrape: timestamp + status
- Games active / inactive
- Link to `scrape_runs` table (admin view, hidden by default, toggled by env flag)

---

## Build Order

1. Supabase — create project, run schema SQL, create `html-cache` storage bucket
2. `src/db/client.py` + `src/db/write.py` — database layer
3. `src/scraper/session.py` — shared HTTP session
4. `src/scraper/games.py` — listing page scraper
5. `src/scraper/prizes.py` — game page scraper (with bug fixes)
6. `src/scraper/claimed.py` — carousel scraper with first_seen/last_seen upsert
7. `src/analysis/ev.py` — baseline EV calculation
8. `src/analysis/retention.py` — retention curve estimator (step-function default until ≥ 1 month of data)
9. `src/analysis/depletion.py` — depletion-adjusted EV using `W_eff(i)` and rate extrapolation
10. `scrape.py` — pipeline orchestrator with `--mode` flag
11. `.github/workflows/` — GitHub Actions cron jobs
12. `app.py` — Streamlit dashboard
