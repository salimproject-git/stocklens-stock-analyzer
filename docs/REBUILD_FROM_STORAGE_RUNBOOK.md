# Rebuild from Supabase Storage Runbook

## Safety rules

- Never run a rebuild against production until a verified pre-run manifest/export, loader dry-runs, Storage family coverage, and four-ticker reconciliation baseline exist.
- Never drop/truncate legacy tables. First migration is additive; stop new readers/modes to roll back.
- Required raw inputs must be present in `stocklens_raw`; a missing input is an explicit failure, not permission to call Sectors API or invent data.
- Run one ticker at a time and retain console output / run IDs.

## Preflight and baseline

1. Review `D:\Stock Analyzer\docs\VALUATION_FREQUENCY_AUDIT.md` and current `git status --short`.
2. Record migration list, row counts for canonical/calculation tables, `calculation_runs` total/status counts, and duplicate `idempotency_key` count.
3. Export full `get_stock_research_data`, valuation summary, backtest, classification, annual ratios, projection, and per-method legacy output for `AUTO`, `GEMA`, `BIRD`, `ITMG`. Save immutable copies outside the rebuild output folder and verify all four tickers/all rows exist.
4. Enumerate Storage objects in `stocklens_raw` per ticker and required family (`info`, `annual`, `quarterly`, `dividend`, `daily`, including quarterly date index). Verify provenance status/checksum and compare with required loader targets.
5. Dry-run the canonical loaders for each ticker; review planned insert/skip/conflict counts. Any conflict or missing object blocks rebuild.

## Execute modes

```powershell
Set-Location 'D:\Stock Analyzer'
python .\run_pipeline.py AUTO --mode rebuild --dry-run
python .\run_pipeline.py AUTO --mode rebuild --offline --dry-run
```

The rebuild implementation must validate Storage coverage before execution. Do not use `--offline` to bypass missing-object checks. After reviewing the dry run and obtaining an approved maintenance window, execute one ticker at a time. The `projection-reuse` step compares all forecast values and relevant metadata to the existing active scenario; mismatch stops without incrementing a scenario version or mutating the active scenario.

```powershell
python .\run_pipeline.py AUTO --mode rebuild --offline
python .\run_pipeline.py GEMA --mode rebuild --offline
python .\run_pipeline.py BIRD --mode rebuild --offline
python .\run_pipeline.py ITMG --mode rebuild --offline
```

Routine independent execution:

```powershell
python .\run_pipeline.py AUTO --mode daily --dry-run
python .\run_pipeline.py AUTO --mode daily
python .\run_pipeline.py AUTO --mode fundamental --dry-run
python .\run_pipeline.py AUTO --mode backtest --dry-run
python .\run_pipeline.py AUTO --mode backtest
```

`daily` must not run intrinsic valuation, growth, projection, classification, or backtest. A page view only invokes bounded read RPCs. Rebuild uses `--reuse-equivalent-active`: it must prove exact projected-value equivalence and reuse the existing active scenario without mutation, otherwise stop and investigate rather than auto-versioning it.

## Reconciliation and validation

Compare before/after for each of `AUTO`, `GEMA`, `BIRD`, `ITMG`:

- intrinsic value per method and method status;
- daily price/date, gap ratio, MoS, method verdict;
- consensus/verdict, Based Method and Based MoS;
- stock type, growth, annual ratios, projection, and backtest output;
- input hashes, calculation-run IDs, methodology versions, provenance and idempotency keys.

Classify every difference as expected input change, architecture-only move from joined legacy row to separated output, intentional fix, or regression. Any unexplained regression blocks acceptance. Check for duplicate idempotency keys and orphan snapshot references.

```powershell
Set-Location 'D:\Stock Analyzer\frontend'
npx tsc --noEmit --pretty false
npm run build

Set-Location 'D:\Stock Analyzer'
python -m unittest discover -s tests -v
git diff --check
```

Verify migrations, new RPC results, raw-table privileges, RLS state, and Supabase security/performance advisors. Preserve all baseline exports, dry-run logs, and reconciliation output with the deployment record.