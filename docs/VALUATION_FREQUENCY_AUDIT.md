# Valuation Frequency and Dependency Audit

**Repository:** `D:\Stock Analyzer`
**Audit date:** 2026-10-03
**Scope:** Read-only dependency, pipeline, Storage, schema/RPC, frontend, and live baseline audit before refactor.

## Execution plan

1. Read the complete source-of-truth plan at `D:\Stock Analyzer\docs\TEMP_VALUATION_PIPELINE_REFACTOR_PLAN.md`.
2. Trace each valuation input, method output, persistence contract, and data frequency before proposing a schema.
3. Inspect orchestrator modes, Storage-backed canonical loaders, current migrations/RPCs, and frontend ownership.
4. Capture live migration history, table row counts, representative RPC outputs for AUTO/GEMA/BIRD/ITMG, and advisor findings without changing the database.
5. Only after this audit, implement additive database/pipeline changes, migrate frontend reads, and validate.

No application or database state was changed during this audit.

## Repository state and caveats

The working tree was already dirty before this task. In particular, user/local modifications existed in `D:\Stock Analyzer\run_pipeline.py`, `D:\Stock Analyzer\supabase\valuation_engine.py`, `D:\Stock Analyzer\supabase\calculate_valuation.py`, `D:\Stock Analyzer\supabase\calculation_v1_common.py`, multiple loaders, frontend research/valuation files, tests, documentation, and migrations `0029`–`0032`. These files must be preserved; their current contents are the audited starting state and cannot be treated as clean upstream baselines.

The live migration listing contains the deployed valuation-summary RPC migration (`stock_valuation_summary_rpc`, version `20261003100806`) in addition to earlier deployed schema versions. Migrations `0033_valuation_frequency_snapshots`, `0034_stock_valuation_frequency_rpc`, and `0035_stock_valuation_frequency_service_role` have subsequently been applied transactionally (live versions `20261003114803`, `20261003114830`, and `20261003120014`).

## Existing orchestrator and frequency

`D:\Stock Analyzer\run_pipeline.py` currently accepts one required ticker and no pipeline mode or batch `--all`. Its one ordered sequence is:

```text
upload-raw -> ingest-raw -> identity -> annual -> quarterly -> dividend -> prices
-> growth-quality -> projection -> classification -> valuation -> backtest
```

Thus the daily price loader does not itself calculate intrinsic value, but invoking the full orchestrator after a daily load also invokes growth/quality, projection, classification, intrinsic valuation, and backtest. The orchestrator’s raw-upload step consults local `Data\Raw` rather than Storage coverage; its ingestion step can call the API when a raw object and local file are both absent. It is therefore not yet a safe Storage-only rebuild entry point for all available objects.

`D:\Stock Analyzer\supabase\run_backtest.py` is a separate executable and supports a ticker or `--all`, but the orchestrator currently includes it in every full run. The frontend fetches existing backtest output through `get_stock_backtest`; opening a page does not itself execute the Python backtest engine.

## Valuation dependency audit

### Inputs and provenance

`D:\Stock Analyzer\supabase\calculate_valuation.py` reads:

- `instruments`: ticker, sector, instrument identity;
- `financial_periods`: annual and quarterly periods through the active scenario’s financial cutoff;
- `financial_facts`: values/revisions for those periods (including earnings, equity, shares, revenue, assets/liabilities and dividends-related inputs as applicable);
- `projection_scenarios` and `projection_values`: active scenario, projected earnings/equity/shares and other projected metrics;
- `prices_daily`: all rows needed for historical period-end observations and current price;
- `calc_metrics_classification`: latest valid final stock type and asset-play rule flag;
- `valuation_sector_weights`, `valuation_type_weights`, `valuation_type_thresholds`;
- `methodology_versions` (`VALUATION_CURRENT`), its parameter specification, code/reference version;
- `risk_free_rate_reference` when `--risk-free-from-reference` is selected.

The valuation input snapshot in `D:\Stock Analyzer\supabase\valuation_engine.py` includes ticker/sector/type, valuation date and current-price date, financial and projection references, annual/quarter IDs and fact values, methodology parameters, historical period-end close observations, **and current price**. Its `input_hash` hashes that complete snapshot. `_store` in `D:\Stock Analyzer\supabase\calculate_valuation.py` derives a `calculation_runs` contract with methodology ID, code version, valuation-date cutoff, snapshot hash, and idempotency key; it preserves an existing successful run on an identical key, but the lookup currently happens only during persistence, after calculation.

### Method-level frequency classification

| Layer / output | Consumed inputs | Existing result/provenance | Correct trigger |
|---|---|---|---|
| Identity and canonical annual/quarter/dividend facts | Storage raw families, source checksums, `ingestion_files` provenance | Canonical tables and source payload/file IDs | Initial load or changed source bytes/facts |
| Daily prices | Storage daily objects, dates/close and other quote fields | `prices_daily` and ingestion provenance | New/changed trading-date row |
| Annual growth/quality and annual ratios | Annual/quarter periods and facts, dividends/prices/shares as relevant, methodology/parameters | `calculation_runs`; growth/ratio result tables | Relevant financial-period/input change, methodology, parameter or code change |
| Quarterly quality/growth | Quarterly/annual facts, periods and applicable shares/inputs | `calculation_runs`; quarterly result tables | Relevant quarterly/annual input or methodology/parameter/code change |
| Projection | Annual/quarter facts, periods, dividends, projection rules/scenario parameters | `projection_scenarios`, `projection_values`, scenario `input_hash` and writer validation | Projection-relevant fundamental input or projection methodology/parameter/code change |
| Classification | Stored growth outputs plus direct canonical classifier inputs, sector, classification parameters and code/methodology | `calculation_runs`; `calc_metrics_classification` | Classification input, parameter, methodology or code change |
| Peter Lynch intrinsic value | Financial facts/periods; projection; stock type/sector; PER targets and growth rules | Current valuation run/input/method result | Relevant fundamental, projection, classifier, parameter, methodology/code, or included historical-price observation changes |
| Type/sector weighted intrinsic value | Financial/projection inputs, stock type/sector, historical PER/PBV, weights | Current valuation run/input/method result | Same fundamental and historical-price-window triggers |
| Mean reversion PBV intrinsic value | Equity/shares and period history plus period-end prices/PBV window and comparison period/parameters | Current valuation run/input/method result | Relevant financial/projection/parameter/methodology change or historical window observation change |
| DDM / discounted earnings intrinsic value | Dividend/earnings projection, risk-free-rate reference, methodology parameters | Current valuation run/input/method result | Relevant fundamental/projection/rate/parameter/methodology/code change |
| Daily gap, MoS, method verdict, consensus, Based Method/Based MoS | Stored intrinsic method results, latest daily close, configured valid-method/MoS rules | Currently colocated on `calc_valuation_methods` and RPC aggregation | New daily price or changed fundamental snapshot/parameter |
| Backtest | Historical case financial/projection/classification inputs, historical prices through outcome horizons, backtest methodology/parameters | `calc_backtest_cases`, `calc_backtest_methods`, calculation provenance | Explicit/manual request, newly mature/changed cases or backtest engine/methodology change; never page-load or every daily update |

### Current-price versus historical-price finding

The existing engine **does consume current price**. In `calculate_valuation_snapshot`, eligible `prices_daily` at or before the valuation date produce `current_price` and `current_price_date`; each current method output also calculates price-dependent `gap_ratio`, verdict, and MoS. These are daily-frequency results and must move to a separate daily layer.

The engine also consumes historical prices in intrinsic valuation: `_year_end_price` is called for each annual EPS and BVPS observation to build `pe_history` and `pbv_history`; `pe_average`, `pbv_average`, and `pbv_compare` feed projected/fair values and valuation methods. Therefore the intrinsic value is not wholly price-independent. Retain historical price observations in the fundamental snapshot/hash, with explicit financial-period/window dates and cutoff. A new daily close after the last required historical cutoff must not invalidate/recalculate those intrinsic values; a changed/missing/added close within the dependency window must invalidate the snapshot. Do not put the latest current quote into the intrinsic-method contract.

Formula ownership after refactor: fundamental method/intrinsic-value and required historical-price-window derivation remain server-side in the Python valuation engine; current-price comparisons, verdict/consensus selection and configured MoS threshold are server/database-side daily outputs/RPCs. Browser components may format/label data, but must not derive valuation, gap, MoS, verdict, consensus or main-method choice.

## Storage and canonical loaders

`D:\Stock Analyzer\supabase\raw_storage_source.py` defines the private `stocklens_raw` bucket and object layout `sectors/{TICKER}/{category}/{name}`. `RawStorageSource` lazily creates a Storage client only when needed; it reads stored bytes and validates provenance using `ProvenanceIndex` / `ingestion_files` checksums.

The audited canonical loaders default to `--source storage`; local-file paths are explicitly debug/verification modes. The audited loader set is:

- `D:\Stock Analyzer\supabase\load_identity_to_supabase.py`
- `D:\Stock Analyzer\supabase\load_annual_financials_to_supabase.py`
- `D:\Stock Analyzer\supabase\load_quarterly_financials_to_supabase.py`
- `D:\Stock Analyzer\supabase\load_dividend_to_supabase.py`
- `D:\Stock Analyzer\supabase\load_daily_prices_to_supabase.py`
- provenance/source helpers: `D:\Stock Analyzer\supabase\raw_storage_source.py`, `D:\Stock Analyzer\supabase\upload_raw_storage_only.py`, and `D:\Stock Analyzer\supabase\ingest_raw_history.py`.

Existing plan-reported Storage coverage is about 1,224 objects and core `info`, `annual`, `quarterly`, `dividend`, `daily` families for 20 tickers (`AMRT ARII AUTO BIRD DSSA ERAA GEMA GOLD INDF INDS INKP IPOL ITMG JSMR MIDI PTBA SIDO TLKM UNTR WIFI`). Coverage must be re-enumerated at execution time per ticker/family. `ingest_raw_history.py` behavior is Storage-safe when an object already exists (repair/register history without API); its missing-object branch is capable of Sectors API calls. The rebuild orchestrator must explicitly preflight/require Storage families and must not reach that branch for covered objects.

## Existing migration, table and RPC boundaries

The repository uses numbered imperative migrations; the live migration list ends in version `20261003100806` (`stock_valuation_summary_rpc`). Valuation-related existing structures include `calculation_runs`, `methodology_versions`, `calculation_parameters`, `calc_valuation_inputs`, and `calc_valuation_methods`, plus canonical projection/classification and backtest tables.

`D:\Stock Analyzer\supabase\migrations\0014_valuation_reference_and_results.sql` enables RLS on raw valuation tables and revokes browser-role grants. `D:\Stock Analyzer\supabase\migrations\0016_frontend_market_data_rpc.sql` and subsequent research RPC migrations expose bounded per-ticker payloads. `D:\Stock Analyzer\supabase\migrations\0031_stock_research_annual_ratios_and_mos.sql` returns the latest valuation-method rows but those rows still combine intrinsic and current-price-derived fields. `D:\Stock Analyzer\supabase\migrations\0032_stock_valuation_summary_rpc.sql` calculates consensus/main MoS summary from those legacy method rows and a configured method-count/MoS threshold.

Live database verification detail: after `0034` deployed, metadata privilege checks reported `anon` and `authenticated` can execute the RPC, but a request authenticated with the configured service-role key failed with HTTP 403 `permission denied for function get_stock_valuation_frequency`. Thus an effective-execution verification defect exists and the frontend must not be cut over until actual role execution succeeds. See final task report; migration cannot be considered accepted based solely on catalog grant checks.

Design implication: preserve legacy tables and RPC fields during the additive migration. Add separated snapshot and daily status/summary records (or an equivalently explicit safe extension), with a stable reference from daily status to the exact fundamental snapshot. Add bounded read RPC(s) that return the latest snapshot plus latest daily status. Keep all raw/new result tables unavailable to `anon`/`authenticated`; expose only RPC results. Avoid duplicate business formula implementations and select Based Method from stored daily summary.

## Frontend audit

`D:\Stock Analyzer\frontend\src\lib\stock-data.ts` already reads market/research/backtest and valuation-summary data through Supabase RPCs. The mapper currently treats the method rows in `get_stock_research_data` as the current quote/valuation source and separately calls `get_stock_valuation_summary` for overview consensus/MoS.

`D:\Stock Analyzer\frontend\src\lib\stock-detail-adapter.ts` still chooses the main method using stock type plus intrinsic-value positivity and calls shared analysis helpers for method preference; current-valutation fields therefore still contain browser-side method-selection logic. `D:\Stock Analyzer\frontend\src\components\stock-research\current-valuation-card.tsx` derives a display comparison bar ratio from current price / IV (presentation geometry only). `D:\Stock Analyzer\frontend\src\components\stock-research\valuation-tab-content.tsx` contains presentational formatting/layout, but must be checked for and removed from any gap/MoS/verdict/main-method business derivation. Runtime stock data is intended to come from RPC; `frontend/src/data/mock-stock-details.ts` is a separate sample/demo source and must not be a production fallback for AUTO.

## Live baseline (read-only, 2026-10-03)

### Row counts

| Table | Live rows |
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

### Representative live RPC outputs

Read using `get_stock_research_data(ticker)` and `get_stock_valuation_summary(ticker)`; no writes were made. Method codes below are ordered by code for compactness; values are current legacy stored results, not post-refactor results.

| Ticker | Valuation date / price | Intrinsic value by method (IDR/share) | Method verdict; valid/undervalued | Based MoS code/value/verdict; threshold |
|---|---|---|---|---|
| AUTO | 2026-09-24 / 3,340 | DDM 1,423.2893; DISCOUNTED_EARNINGS 2,304.4027; MEAN_REVERSION_PBV 1,740.1380; PETER_LYNCH 3,567.4274; TYPE_SECTOR_WEIGHTED 2,536.2641 | OVERVALUED; 5/1 | PETER_LYNCH / 0.0637511 / OVERVALUED; 0.30 |
| GEMA | 2026-09-11 / 93 | DDM -16.2206; DISCOUNTED_EARNINGS 0; MEAN_REVERSION_PBV 136.2210; PETER_LYNCH -22.0308; TYPE_SECTOR_WEIGHTED 32.7376 | N/A; 2/1 | TYPE_SECTOR_WEIGHTED / -1.8407693 / OVERVALUED; 0.30 |
| BIRD | 2026-09-09 / 1,625 | DDM 961.3445; DISCOUNTED_EARNINGS 1,851.8399; MEAN_REVERSION_PBV 1,552.2182; PETER_LYNCH 2,489.6083; TYPE_SECTOR_WEIGHTED 1,794.3314 | UNDERVALUED; 5/3 | PETER_LYNCH / 0.3472869 / UNDERVALUED; 0.30 |
| ITMG | 2026-09-11 / 26,100 | DDM 29,402.1609; DISCOUNTED_EARNINGS 11,213.7226; MEAN_REVERSION_PBV 25,200.1501; PETER_LYNCH 30,261.9469; TYPE_SECTOR_WEIGHTED 33,062.1524 | UNDERVALUED; 5/3 | PETER_LYNCH / 0.1375307 / OVERVALUED; 0.30 |

**Capture limitation:** the four-ticker query captured every stored method value, price, gap, MoS, verdict, method status and summary. It did not capture growth, annual ratios, projection details, full backtest rows, or other complete RPC sections. Before rebuild, persist a complete machine-readable baseline for those remaining sections through bounded RPC/read queries; confirm backups/manifest and verify the exported artifact before any writes.

### Migration history

Live migration listing includes the deployed sequence through version `20261003100806`, with historical resync/backtest names and deployed `annual_ratios`, `valuation_method_mos`, `stock_research_annual_ratios_and_mos`, and `stock_valuation_summary_rpc`. The live migration registry is not identical to the local filename/version history in all historical entries; reconcile migration history before applying any new migration.

### Advisors

- Security advisor initially reported 12, then 16 `RLS Enabled No Policy` INFO findings after the four private result tables were added. This is expected for the new tables because browser roles have no table grants and reads use the RPC. The advisor also reports callable `SECURITY DEFINER` read RPCs, including the new intentionally public bounded reader, and `rls_auto_enable`. Remediation reference: [Supabase database linter security rules](https://supabase.com/docs/guides/database/database-linter).
- Performance advisor initially reported 29, then 39 unindexed foreign-key INFO findings after additions, and 6 then 8 unused indexes (new indexes are unused before data/backfill). New FK columns/indexes must be reviewed once safely populated; avoid unrelated destructive index changes. Remediation reference: [Supabase database linter performance rules](https://supabase.com/docs/guides/database/database-linter).

## Safe implementation and rebuild gates

1. Preserve current dirty working-tree edits. Do not overwrite, reset, truncate, or drop legacy results.
2. Add fundamental snapshot fields for instrument/run/methodology, financial cutoff, projection/classifier/parameter/code references, required historical-price cutoff/window observations, complete input snapshot/hash, idempotency key, method IV/status/flags/details, and provenance.
3. Add daily status/summary fields for snapshot reference, trading date/price, per-method gap/MoS/verdict/status, configured consensus/minimum, Based Method/Based MoS and flags, daily snapshot/hash/idempotency/run provenance.
4. Split Python intrinsic computation from current quote comparison only after pinning historical-window dependency behavior in tests. Preflight a succeeded identical run by canonical hash before expensive work where safe; retain writer-side idempotency guard.
5. Add rebuild/fundamental/daily/backtest modes. `daily` must not invoke growth, projection, classification, intrinsic calculation, or backtest. `backtest` is independent/manual/event-driven. Rebuild must require/verify Storage for raw families and fail closed for missing data rather than calling Sectors API.
6. Before any live rebuild, save migration list, row counts, `calculation_runs` counts and duplicate-key checks; complete the full four-ticker RPC/result baseline; enumerate Storage coverage; dry-run each canonical loader; export/preserve legacy outputs.
7. Reconcile all required fields for AUTO/GEMA/BIRD/ITMG and classify every change before accepting a rebuild. No destructive cleanup until reconciliation and recovery are proven.
8. Run Python tests, TypeScript check, production build, SQL migration/RPC/security checks/advisors, and `git diff --check`.

## Audit decision

The safest compatible first schema change is additive separated fundamental and daily result tables (with no deletion/backfill of legacy results in that first migration), followed by a bounded RPC that prefers the new snapshot/status pair and can report unavailable when absent. The valuation engine must stop taking current price as an intrinsic-method dependency while retaining explicitly hashed historical price observations for PER/PBV. Any difference from this shape must be documented and justified against the source-of-truth plan.

Implementation-specific note: legacy `calculate_valuation.py` behavior is retained as the default CLI path for compatibility and comparison; the new orchestrated fundamental mode explicitly passes `--frequency-snapshot`. That mode excludes current quote-derived fields from new method rows/hashes and persists separated tables; daily status has its own orchestrator step and `calculation_type`. This opt-in is a transitional safety decision because existing consumers and persisted legacy run contracts must continue working while the additive reader/reconciliation is deployed. Frontend reads the new frequency RPC first and has an explicit temporary legacy-RPC fallback while the new tables are empty. The fallback is a known temporary deviation from the final browser formula-ownership target; remove it after the verified migration/backfill and reconciliation.

Post-migration live state (2026-10-03): the new bounded RPC executed successfully via service-role for all four tickers and returned the correct selected ticker with `fundamental=null`, `daily=null`. The four new tables have zero rows; legacy `calc_valuation_methods` remains at 120, `calculation_runs` at 224 SUCCEEDED, and duplicate idempotency keys remain zero. Raw-table SELECT is false for both browser roles on all four tables; RPC EXECUTE is granted to anon/authenticated/service_role. No rebuild/backfill was performed.

Validation status at handoff: 452 Python tests passed; `tsc --noEmit`, `npm run build`, and `py_compile` passed. Targeted `git diff --check` on task implementation files passed. Repository-wide `git diff --check` is blocked by pre-existing dirty content in `D:\Stock Analyzer\docs\BACKEND_SINGLE_SOURCE_OF_TRUTH.md` (extra blank line at EOF); this unrelated user change was not modified. Required full loader dry-runs, immutable complete result exports, rebuild, and before/after reconciliation for AUTO/GEMA/BIRD/ITMG are still outstanding; task acceptance is therefore incomplete.