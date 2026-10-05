# Valuation Frequency Architecture

## Pipeline modes

`python run_pipeline.py TICKER --mode rebuild` loads existing raw source families into canonical tables, recalculates dependent fundamental outputs and snapshots, then loads daily prices and writes daily status. For an existing active projection, rebuild derives a candidate and only reuses the active scenario if every stored numeric forecast value, unit, display value/source kind, and base metadata match; reuse is read-only and preserves the workbook scenario's existing hash/provenance. A mismatch fails closed. It deliberately does **not** upload or ingest missing raw data as a hidden API fallback. Missing Storage objects must be reported and resolved explicitly.

`--mode fundamental` loads identity and fundamental raw families, recalculates growth/quality, projection, classification, and intrinsic values, then refreshes daily status. `--mode daily` loads daily prices and invokes only the daily comparison engine. `--mode backtest` invokes only `run_backtest.py`; it is independent of page views and routine daily-price ingestion. `rebuild` is an explicit operator action, not a scheduled daily action.

## Formula ownership and dependencies

`valuation_engine.calculate_valuation_snapshot` owns intrinsic values. Its versioned fundamental snapshot contains financial periods/facts, projection scenario/hash, stock type/sector, parameters/methodology/risk-free reference, and the exact historical period-end price observations used for P/E and P/BV, capped at the projection financial cutoff. Latest/current daily price is excluded from the snapshot hash and does not change an intrinsic value.

`calculate_daily_valuation_status` owns quote-sensitive calculations: per-method gap ratio and MoS, verdict, consensus, Based Method, Based MoS, and configured threshold verdict. It reads one immutable fundamental snapshot plus one latest daily quote. The browser only formats stored values; no valuation formulas, method-choice rules, MoS, verdict, or consensus are duplicated there.

## Triggers and idempotency

- Relevant annual/quarter facts, dividends, projection, classification/type, reference parameters, methodology/code, risk-free input, or a required historical price observation change: run fundamental dependencies, hash the complete snapshot, and insert/reuse by `calculation_runs.input_hash` / `idempotency_key`.
- New daily close: store canonical price and insert/reuse the daily run keyed by fundamental snapshot ID/hash, date, close, and daily policy parameters. Do not run growth, projection, classification, intrinsic valuation or backtest.
- Backtest: operator/manual or an explicit event scheduler only; never tied to frontend requests.

## Storage-only rebuild, dry-run and rollback

Raw source of truth is private Supabase Storage bucket `stocklens_raw`, layout `sectors/{TICKER}/{category}/{name}`. Canonical loaders default to Storage and validate SHA-256 `ingestion_files` provenance. Rebuild must preflight all required object families before writing and fail closed if any are missing; it must not call Sectors API. Run individual loaders without write/apply options where supported to review planned inserts/conflicts. Preserve an export/manifest of existing RPC outputs and row/run counts before any write.

The new tables are additive; legacy valuation rows and RPCs remain available for comparison. Rollback consists of switching readers back to the legacy RPC and stopping the new modes; do not drop tables or truncate data. Any cleanup requires completed reconciliation and a verified backup.

## Validation

See `D:\Stock Analyzer\docs\REBUILD_FROM_STORAGE_RUNBOOK.md` for commands and the complete acceptance checklist. The 2026-10-03 canary/rebuild evidence and four-ticker reconciliation are recorded in `D:\Stock Analyzer\docs\VALUATION_FREQUENCY_AUDIT.md` and the local backup manifest under `D:\Stock Analyzer\backups\valuation_frequency_20261003\`.

## Safe rollout compatibility

Migrations `0033`–`0035` add the new private result tables and bounded reader. Before verified backfill, the RPC returns null fundamental/daily sections; the frontend explicitly falls back to the legacy summary RPC. This temporary branch preserves current screens but means the final formula-ownership target is not reached until the new tables are populated and four-ticker reconciliation passes. Remove the legacy branch only after that acceptance gate.