# StockLens

StockLens is a beginner-friendly **Indonesian stock market intelligence** application.
It turns raw Sectors.app data into derived insight — valuation signals, margin-of-safety
verdicts, financial health and growth classifications, and stock-specific historical
evidence — so a non-professional investor can judge a company without reading a
professional trading terminal.

**Track:** Market Intelligence (Sectors Hackathon Indonesia 2026).

StockLens does not give investment recommendations and does not place orders. It
presents information, analysis, and historical outcomes; the decision stays with the user.

---

## 1. What it does

The product answers one question at a time, in this order:

```text
Market
  -> pick a stock
  -> current condition
  -> financial history
  -> business health & growth
  -> current valuation
  -> historical evidence
  -> the user makes their own judgment
```

### Market Overview (`/market`)

A screener over every IDX instrument stored in the research database. Each row is a
derived verdict, not a raw quote:

| Field | How it is derived |
|---|---|
| **Signal** | Agreement between two independent "cheap" rules: the method consensus (at least 3 valid intrinsic-value methods above price) and the MoS rule (based MoS >= 30%). Both cheap -> `Undervalued`, both expensive -> `Overvalued`, disagree -> `Mixed` |
| **MoS** | Stored margin of safety of the based method, as a percentage |
| **Methods** | `undervalued_method_count / valid_method_count`, e.g. `3 / 4` |
| **Historical Evidence** | `WIN + RECOVERED` cases over total cases in the newest succeeded backtest run for that stock |
| **Stock Type** | Resolved by the valuation engine (bank, cyclical, stalwart, asset play, ...) |

Filters and sorting are applied in the database, so they range over the whole
instrument set rather than only the rows on the current page.

### Stock Research (`/market/[ticker]`)

| Tab | Content |
|---|---|
| Overview | Current price, key metrics, valuation summary, company profile |
| Financials | Annual and quarterly history with derived ratios (EPS, BVPS, ROE, margins) |
| Health & Growth | Growth quality metrics and margin / cash-conversion classifications |
| Valuation | Per-method intrinsic value, gap, MoS, verdict, and a consensus verdict |
| Backtest | Historical cases: for each past valuation state, what happened to the price next |

---

## 2. How Sectors data becomes an insight

Sectors is the **origin of every number in the product**. Removing it removes the
product: there is no second market-data source and no hand-entered fallback.

```text
   Sectors.app REST API  (https://api.sectors.app/v2)
   info · annual · quarterly · quarterly-dates · dividend · daily
                |
                |  scripts/data_pipeline/01_download_sectors.py
                |  stores every response AS-IS as JSON + keeps a manifest
                v
   Supabase Storage  bucket `stocklens_raw`
   object key  sectors/{TICKER}/{family}/...
   provenance in `ingestion_files` with a SHA-256 checksum per file
                |
                |  supabase/load_*.py  (canonical loaders)
                v
   Postgres canonical tables
   instruments · financial_periods · financial_facts · prices_daily · dividend_facts
                |
                |  supabase/valuation_engine.py, run_backtest.py,
                |  populate_growth_quality.py, populate_metrics_classification.py
                v
   Derived result tables
   calc_valuation_methods · calc_valuation_daily_status ·
   calc_valuation_fundamental_snapshots · calc_annual_ratios ·
   calc_annual_growth_quality · calc_backtest_cases · calc_backtest_methods
                |
                |  read-only RPCs (security definer, bounded)
                v
   Next.js server components  ->  UI
```

Read-only RPCs exposed to the browser:

```text
get_market_overview_page(p_page, p_page_size, p_sector, p_stock_type, p_sort)
get_stock_research_data(p_ticker)
get_stock_backtest(p_ticker)
get_stock_valuation_summary(p_ticker)
get_stock_valuation_frequency(p_ticker)
```

The browser never recomputes a business number. Every displayed metric either comes
from the database or is a presentation-only transform (rounding, locale, unit label,
colour). The rationale and the storage/display boundary are written up in
[`docs/BACKEND_SINGLE_SOURCE_OF_TRUTH.md`](docs/BACKEND_SINGLE_SOURCE_OF_TRUTH.md).

---

## 3. Run it locally

Prerequisites: **Node.js 20+**, **Python 3.11+**, and a Supabase project that has
been migrated with `supabase/migrations/`.

### 3.1 Frontend

```powershell
Set-Location 'D:\Stock Analyzer\frontend'
Copy-Item .env.example .env.local
# then edit .env.local and fill in the two values
npm install
npm run dev            # http://localhost:3000
```

`frontend/.env.example` lists the two variables the server-only data layer reads:

| Variable | Where it comes from | Notes |
|---|---|---|
| `SUPABASE_URL` | Supabase -> Project Settings -> API | Public project URL |
| `SUPABASE_PUBLISHABLE_KEY` | Supabase -> Project Settings -> API keys | Publishable (`sb_publishable_...`) or legacy `anon` key |

Both are read through `import "server-only"` in `frontend/src/lib/stock-data.ts`, so
they are never bundled into the browser. **The service-role key must never be placed
in the frontend.** The RPCs are the only database surface the app uses, and they are
granted to `anon`/`authenticated` explicitly.

### 3.2 Data pipeline (only needed to add or refresh a ticker)

The pipeline reads and writes Supabase, so it needs server-side credentials. Set them
in the local shell only — never in a file that is committed.

```powershell
Set-Location 'D:\Stock Analyzer'
$env:SECTORS_API_KEY            = '<sectors api key>'
$env:SUPABASE_URL               = '<https://PROJECT_REF.supabase.co>'
$env:SUPABASE_SERVICE_ROLE_KEY  = '<service role key>'

python .\scripts\data_pipeline\01_download_sectors.py AUTO --task all
python .\run_pipeline.py AUTO --mode daily --dry-run
python .\run_pipeline.py AUTO --mode daily
```

`--dry-run` prints the commands the orchestrator would call without touching the
database. The full ingest/recalculate/verify procedure is in
[`docs/SUPABASE_MANUAL_RUNBOOK.md`](docs/SUPABASE_MANUAL_RUNBOOK.md).

### 3.3 Tests

```powershell
Set-Location 'D:\Stock Analyzer'
python -m unittest discover -s tests -t . -v
```

The suite is offline: it checks migration contracts, calculation modules, and the
frontend data adapters against fixtures. It needs no credentials and no network.

---

## 4. Repository map

```text
README.md                    Start here
docs/                        Guides, audits, and archived references
  PRODUCT_CONTEXT.md         What the product is meant to do
  DATA_RULES.md              Agreed data rules and open questions
  RAW_DATA_MAP.md            Sectors JSON family -> canonical table map
  SUPABASE_MANUAL_RUNBOOK.md Ingest / recalculate / verify procedure
scripts/data_pipeline/       Sectors API collector and JSON-to-CSV converter
supabase/                    Migrations, canonical loaders, calculation code
  migrations/                Applied in order; never rewritten
  valuation_engine.py        Multi-method intrinsic value + MoS
  run_backtest.py            Historical evidence generation
run_pipeline.py              Orchestrator: daily / fundamental / rebuild / backtest
tests/                       Offline regression tests and fixtures
frontend/                    Next.js application
Data/                        Local raw JSON and CSV (ignored by Git)
backups/                     Pre-rebuild database exports (ignored by Git)
Testing/                     Legacy scratch experiments (ignored by Git)
```

---

## 5. Safety notes

- Local data under `Data/` and exports under `backups/` are deliberately not committed.
- Never put the Supabase `service_role` key in the frontend or commit it to Git.
- Do not delete or rewrite a migration that has already been applied. Add a new one.
- The database holds real IDX data. A script that writes to Supabase is not a harmless
  cleanup command; read it before running it.

---

## 6. Current limitations

Stated plainly, because they matter when reading the numbers:

- The research database currently covers **23 IDX tickers** out of roughly 900 listed
  companies. Adding a ticker is a supported pipeline run, not a code change.
- **20 of 23** tickers have a valuation snapshot. The rest have no classified stock
  type yet, so their valuation rows are intentionally empty rather than guessed.
- `report_date` / `available_date` on financial periods are still empty, so historical
  backtests use the period end date as the point-in-time boundary.
- Quarterly shares and annual average volume are intentionally not ingested yet.
- Backtest outcomes are **historical evidence, not a prediction**, and the UI labels
  them as such.

---

## 7. Disclaimer

StockLens is an information and analysis tool. It does not provide investment advice,
recommendations, or trading signals, and it cannot place orders on any account.
Historical outcomes shown in the product are evidence about the past, not a forecast.
All investment decisions and their consequences are the user's own.