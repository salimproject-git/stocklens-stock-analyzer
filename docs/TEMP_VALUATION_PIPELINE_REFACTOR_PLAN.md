# Temporary Plan: Split Fundamental Valuation from Daily Status

**Repository:** `D:\Stock Analyzer`
**Purpose:** Source-of-truth execution plan for a new coding-agent chat. Read this file completely before making changes.

## Goal

Separate calculations by how frequently their inputs change:

```text
Fundamental inputs change -> calculate intrinsic values and save a snapshot
Daily price changes       -> update price comparison, MoS, verdicts and consensus only
Backtest                  -> run independently, not on every daily update/page load
```

The frontend reads stored results from Supabase RPCs and does not calculate valuation business logic. Rebuild uses existing Supabase Storage raw files and avoids Sectors API calls for files already present.

## Guardrails

1. Start with a read-only audit and report a short plan before editing.
2. Do not edit code or database until valuation dependencies are audited.
3. Use absolute paths in reports.
4. Never use mock/sample valuation as a runtime source.
5. Never call Sectors API when the needed raw object exists in Storage.
6. First migrations are additive and transactional; do not drop or truncate legacy tables.
7. Before rebuild, capture migration list, row counts, calculation-run counts, and representative RPC outputs.
8. Preserve provenance, methodology versions, `calculation_runs`, input snapshots, `input_hash`, and `idempotency_key` semantics.
9. Do not expose raw calculation tables to browser roles. Use bounded read-only RPCs.
10. Re-read edited files and run database, Python, TypeScript, and build validation before completion.

## Audit facts

Current orchestrator:

```text
D:\Stock Analyzer\run_pipeline.py
```

Current full ticker pipeline:

1. upload-raw
2. ingest-raw
3. load-identity
4. load-annual
5. load-quarterly
6. load-dividend
7. load-prices
8. growth-quality
9. projection
10. classification
11. valuation
12. backtest

Loading daily prices alone does not calculate valuation, but running the full pipeline after daily ingestion currently invokes growth, projection, classification, valuation, and backtest too.

Important files to inspect:

```text
D:\Stock Analyzer\supabase\valuation_engine.py
D:\Stock Analyzer\supabase\calculate_valuation.py
D:\Stock Analyzer\supabase\calculation_v1_common.py
D:\Stock Analyzer\supabase\calculation_registry.py
D:\Stock Analyzer\supabase\populate_growth_quality.py
D:\Stock Analyzer\supabase\derive_projection_scenario.py
D:\Stock Analyzer\supabase\populate_metrics_classification.py
D:\Stock Analyzer\supabase\run_backtest.py
D:\Stock Analyzer\supabase\raw_storage_source.py
D:\Stock Analyzer\supabase\ingest_raw_history.py
```

Approximate database row counts from audit:

| Table | Rows |
|---|---:|
| `instruments` | 20 |
| `prices_daily` | 32,002 |
| `financial_periods` | 658 |
| `financial_facts` | 6,864 |
| `dividend_facts` | 101 |
| `projection_scenarios` | 20 |
| `projection_values` | 199 |
| `calc_annual_growth_quality` | 9,940 |
| `calc_annual_ratios` | 2,556 |
| `calc_quarterly_quality` | 8,256 |
| `calc_metrics_classification` | 180 |
| `calc_valuation_inputs` | 912 |
| `calc_valuation_methods` | 120 |
| `calc_backtest_cases` | 1,797 |
| `calc_backtest_methods` | 7,150 |
| `calculation_runs` | 224 |

The database already has `calculation_runs`, methodology references, input snapshots, `input_hash`, and `idempotency_key`. The valuation writer checks idempotency during persistence after calculation; add preflight skip behavior where safe but retain the writer-side guard.

Supabase Storage bucket `stocklens_raw` has about 1,224 objects. Audited core families (`info`, `annual`, `quarterly`, `dividend`, `daily`) exist for:

```text
AMRT ARII AUTO BIRD DSSA ERAA GEMA GOLD INDF INDS INKP IPOL
ITMG JSMR MIDI PTBA SIDO TLKM UNTR WIFI
```

Storage-first support exists in `raw_storage_source.py` and canonical loaders. Recheck coverage at execution time and prove the lazy Sectors client is not initialized when Storage has the source. Workflow is documented as manual/not scheduled; do not infer valuation is automatically calculated when a price row is inserted.

## Phase 0: dependency audit (mandatory)

Before schema design, inspect the files above and create:

```text
D:\Stock Analyzer\docs\VALUATION_FREQUENCY_AUDIT.md
```

For each calculation, record consumed input tables/columns, outputs, provenance, and frequency. Explicitly determine whether any method uses current price or historical price windows as inputs (for example historical PBV). Do not assume intrinsic value is price-independent. Preserve any required historical price cutoff/window in the snapshot contract.

Classify each layer:

| Layer | Trigger |
|---|---|
| Identity/canonical financials | Initial load or source-data change |
| Daily prices | Daily |
| Growth/quality/annual ratios | Financial-period/input change |
| Projection | Financial/projection input change |
| Classification | Classification input/parameter change |
| Intrinsic value | Fundamental, required price-window, methodology, parameter, or code change |
| Daily MoS/gap/verdict/consensus | Daily price or fundamental snapshot change |
| Backtest | New mature cases/snapshot, engine change, or explicit request |

Do not implement schema changes until this audit is complete.

## Target pipeline modes

Refactor `D:\Stock Analyzer\run_pipeline.py` with behavior equivalent to:

```powershell
python run_pipeline.py AUTO --mode rebuild
python run_pipeline.py AUTO --mode fundamental
python run_pipeline.py AUTO --mode daily
python run_pipeline.py AUTO --mode backtest
```

Add batch support if safe:

```powershell
python run_pipeline.py --all --mode daily
python run_pipeline.py --all --mode rebuild
```

**Rebuild mode:** reconstruct canonical and derived state from Storage; no Sectors API for complete families.
**Fundamental mode:** load changed fundamental sources, then run dependent growth/ratios, projection, classification, and intrinsic valuation snapshot. Reuse an identical successful snapshot and skip expensive calculation when safely possible.
**Daily mode:** load daily prices, use latest fundamental snapshot, calculate/store only daily market status. Must not run growth, projection, classification, full intrinsic engine, or full backtest.
**Backtest mode:** run independently for mature cases, new snapshots, engine changes, or explicit request.

Every mode should report mode, ticker(s), steps, source, rows inserted/skipped, runs created/reused, and validation.

## Mandatory database design review

First decide whether existing tables can be safely extended; do not create duplicate tables without documenting why. If separation is needed, consider additive structures equivalent to:

```text
calc_valuation_fundamental_snapshots
calc_valuation_fundamental_methods
calc_valuation_daily_status
calc_valuation_daily_summary
```

Names may differ after the dependency audit.

Fundamental snapshots/method rows should preserve instrument, run, methodology, financial cutoff, projection reference, required historical-price cutoff/window if any, input hash, intrinsic value per method, stock type, status, flags/details, provenance, and timestamps.

Daily status/summary should preserve instrument, snapshot reference, trading date, daily price, method code, intrinsic reference, gap ratio, MoS, method verdict, valid/undervalued counts, Based Method, MoS method, threshold, Based MoS verdict, flags, daily input hash, run, and timestamp.

For positive intrinsic value:

```text
gap_ratio = (intrinsic_value - current_price) / current_price
mos       = (intrinsic_value - current_price) / intrinsic_value
```

Preserve existing null/status/flag semantics for unavailable or non-positive values; never silently convert them to overvalued.

Consensus:

```text
valid methods below configured minimum -> N/A
undervalued count strictly greater than half -> UNDERVALUED
otherwise -> OVERVALUED
```

MoS classification reads the canonical database parameter; null MoS -> N/A. Do not duplicate thresholds in React.

Fundamental idempotency: same fundamental inputs, projection, parameters, methodology, and code version must reuse the snapshot and, where possible, skip calculation preflight.
Daily idempotency: key includes instrument, trading date, fundamental snapshot, and method/code version. Same input must not duplicate daily status/summary rows.

Migrations must be additive, transactional, RLS-protected, indexed, verified in SQL, tested, and reviewed with Supabase advisors. Do not remove old results in the first migration.

## RPC/frontend target

RPC returns latest fundamental snapshot plus latest daily status/summary. Frontend may format values/dates and show unavailable states; it must not calculate intrinsic value, gap ratio, MoS, verdict, consensus, Based Method, or Based MoS.

Review as required:

```text
D:\Stock Analyzer\frontend\src\lib\stock-data.ts
D:\Stock Analyzer\frontend\src\lib\stock-detail-adapter.ts
D:\Stock Analyzer\frontend\src\components\stock-research\current-valuation-card.tsx
D:\Stock Analyzer\frontend\src\components\stock-research\valuation-tab-content.tsx
```

AUTO must not use mock runtime fallback.

## Safe rebuild procedure

Before rebuild:

1. Record migrations, row counts, run counts, and Storage coverage.
2. Save current RPC/valuation outputs for `AUTO`, `GEMA`, `BIRD`, `ITMG`.
3. Prove Storage is selected and Sectors client is not initialized for covered families.
4. Dry-run canonical loaders and inspect planned writes.
5. Preserve/export old results until reconciliation passes.
6. Apply only reviewed additive migrations; no destructive reset without verified recovery.

Rebuild dependency order:

```text
identity -> annual -> quarterly -> dividends -> daily prices
-> growth/quality and annual ratios -> projection -> classification
-> fundamental valuation snapshots -> daily valuation status/summary
-> backtest -> RPC verification -> frontend verification
```

Use Storage for every available raw family. Report gaps and any justified API fallback before using it.

## Reconciliation and acceptance

Compare before/after for `AUTO`, `GEMA`, `BIRD`, `ITMG`:

- intrinsic value per method;
- price/date;
- gap ratio and MoS;
- method verdict;
- Based Method and Based MoS;
- stock type;
- growth, annual ratios, projection;
- backtest output.

Classify each difference as expected input change, architecture change, intentional fix, or regression. Unexplained regression blocks completion.

Run:

```powershell
Set-Location 'D:\Stock Analyzer\frontend'
npx tsc --noEmit --pretty false
npm run build

Set-Location 'D:\Stock Analyzer'
python -m unittest discover -s tests -v
git diff --check
```

Verify Supabase migrations, row counts, duplicate idempotency keys, latest snapshots/status per ticker, RPC output for the four tickers, and security/performance advisors.

## Documentation deliverables

Create/update:

```text
D:\Stock Analyzer\docs\VALUATION_FREQUENCY_ARCHITECTURE.md
D:\Stock Analyzer\docs\REBUILD_FROM_STORAGE_RUNBOOK.md
```

Explain pipeline modes, formula ownership, triggers, Storage-only rebuild, dry-run, validation, rollback, and exact commands.

## Definition of done

- Daily mode does not run intrinsic engine, growth, projection, classification, or full backtest.
- Fundamental mode creates/reuses snapshots based on audited dependencies and hashes.
- Backtest is independent and event-driven/manual.
- Daily and fundamental runs are idempotent.
- Storage-only rebuild works for covered data without Sectors API calls.
- New schema/RPCs are RLS-protected, bounded, and verified.
- Frontend reads stored results and has no duplicate valuation formulas or mock AUTO fallback.
- Reconciliation passes for AUTO, GEMA, BIRD, ITMG.
- Python tests, TypeScript check, production build, SQL verification, advisors, and `git diff --check` pass.
- Final report lists files, migrations, commands, test results, reconciliation, source used, and limitations.
