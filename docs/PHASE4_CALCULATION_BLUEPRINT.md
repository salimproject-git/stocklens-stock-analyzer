# StockLens Phase 4 — Calculation Engine Blueprint

**Phase:** 4 (discovery / specification only)
**Status:** BLUEPRINT — no implementation, no migration, no frontend change
**Reference workbook:** `Template\Stock Analyzer [Dev].xlsm` (1.519.519 B, 15 sheets)
**Reference ticker:** `AUTO`
**Canonical source:** `stocklens_raw` (Storage) → `public.*` (PostgreSQL)

> This document **specifies** how to move the Excel model into an implementable
> StockLens calculation engine. It contains **no implementation code**, creates
> **no** `calc_*` tables, and **modifies no** calculation, frontend, or migration
> file. Every value quoted as an "AUTO example" was read from the live database
> or from the cached workbook, not estimated.

---

## 1. Scope and Principles

### 1.1 Scope

In scope for Phase 4 (specification):

1. Inventory every Excel calculation that produces a user-visible or
   dependency-relevant value.
2. Inventory every existing web-app calculation.
3. Map each metric to canonical PostgreSQL columns, or classify it as a gap.
4. Define units, as-of-date semantics, and historical-series requirements.
5. Define the dependency graph and a recommended implementation order.
6. Define the validation strategy that proves parity with the workbook.

Out of scope for Phase 4:

- Writing Python/SQL calculation code.
- Creating `calc_*` tables or any migration.
- Changing the frontend, mock data, or `lib/analysis`.
- Changing canonical/raw data or storage.

### 1.2 Principles (binding)

| # | Principle | Consequence |
|---|---|---|
| P1 | **Canonical financial values are IDR.** Never store presentation units. | `financial_facts.value_numeric` stays in raw IDR. Unit conversion happens only at the presentation/export boundary. |
| P2 | **Excel presentation units are documented, not "fixed".** | The `(M Rp)` columns actually hold **billion IDR (×1e9)**. Replication must apply the same ×1e9 factor to match the workbook. The misleading label stays. |
| P3 | **Never silently repair the workbook.** | `Stock_Database!O` labelled "Avg Vol (3M)" actually returns `Close`. Documented in §5 and §6; the reference model keeps the defect. |
| P4 | **Point-in-time correctness is mandatory.** | Every price used by a calculation must be resolved against the requested as-of date (`close_price` on or before that date), never against "latest". |
| P5 | **Missing ≠ zero.** | If an input is absent, the result must be `UNAVAILABLE`/`NOT_CALCULABLE` with a flag — never coerced to `0`. |
| P6 | **Every derived result carries provenance.** | Result rows reference instrument, calculation run, methodology version, observation date, and input snapshot. |
| P7 | **Calculation lives server-side.** | The Next.js browser bundle must never contain the private formula set. |
| P8 | **Determinism and idempotency.** | Identical inputs + methodology version ⇒ identical output and identical idempotency key. |

### 1.3 Source authority

| Source | Authority | Notes |
|---|---|---|
| `financial_facts` / `financial_periods` | **Canonical** | Values are authoritative IDR. |
| `prices_daily` | **Canonical** | `close_price`/`volume` complete; `market_cap` partial. |
| `dividend_facts` | **Canonical** | Provider semantics differ from template semantics (§12.4). |
| `Template\Stock Analyzer [Dev].xlsm` | **Reference model** | Defines *what to compute*, not *what is true*. |
| `docs/EXCEL_POSTGRES_VALIDATION.md` | **Phase 3 audit** | Reconciliation basis; one correction recorded in §4.6. |
| `Testing\test_calculation_v1.py`, `Testing\test_run_calculation_v1.py` | **Forward spec (TDD)** | Encodes the intended calculation-engine contract. Currently **red** — target modules do not exist. |
| `frontend\src\data\mock-stock-details.ts` | **Temporary frontend source of truth** | Static copy of workbook output. Not canonical. |


---

## 2. Excel Calculation Inventory

### 2.1 Calculation sheets

| Sheet | Rows × Cols | Role |
|---|---:|---|
| `SUMMARY` | 204 × 19 | Dashboard: 5 IV methods, thesis validator, dividend, health, thresholds, quality, market mood, strategic panel |
| `DataInput` | 102 × 26 | Annual input + derived line items (`B20..B43`) |
| `DataInputProyeksi` | 89 × 14 | Quarterly input, projection engine (`Proj_*`), YoY thesis |
| `FinancialHealth` | 71 × 5 | DER, CR, ICR, forensic flags, health score |
| `MetricsClassification` | 130 × 10 | Growth/momentum/multiples/averages/percentile, stock-type engine |
| `ValuationCurrent` | 177 × 9 | 5 valuation methods, MoS |
| `Reference` | 143 × 19 | Sector weights, type weights, DER/CR thresholds |
| `Backtest_Result` | 19 × 27 | Historical evidence — **static values, 0 formulas** |

### 2.2 Excel formula reality (important)

The workbook is **not** formula-dense on the calculation sheets. Most logic lives
in **named ranges** (`Range_*`, `Metric_*`, `Proj_*`) and in **`_xlfn.LET` blocks
stored as dynamic array formulas**. A naive `cell.value.startswith("=")` scan
finds only ~150 formula cells.

Verified formula-bearing cells per sheet:

| Sheet | Notable formula cells |
|---|---|
| `FinancialHealth` | `B8` DER, `B9` CR, `B10` ICR, `B11` OCF, `B14`–`B18` forensic, `B23` clearance, `B26` health score, `B27` risk rating |
| `MetricsClassification` | `B5` years-compare, `B7`/`B8` CAGR, `B9` momentum, `B10` CoV, `B11` YoY, `B13`/`B14` EPS CAGR, `B15` momentum, `B17` CA growth, `B18` asset growth gap, `B19`/`B20` NWC, `B24`–`B30` price/multiples, `B32`–`B34` dividend, `B36`–`B39` history/percentile, `B43`–`B51` quality, `B55`–`B60` latest balance/flow, `B64`–`B69` forensic, `B72`–`B77` classification rules, `B80` classifier, `B83` confidence |
| `ValuationCurrent` | `B4`–`B8` PER bottom/top + liquidation/asset/cyclical, `B17`–`B22` weighted components, `B25`–`B29` five methods, `B44` target sell, `B45` hard floor, `B47` MoS |
| `DataInputProyeksi` | `B4` as-of quarter, `B6` payout, `B12`–`B25` quarterly + `F12`–`F25` projections, `B47`–`B52` YoY thesis |
| `DataInput` | `B5` as-of date, `B12`/`B15` years, `B14` market cap, `B19` year label, `B25`–`B43` derived |
| `SUMMARY` | `B13`–`B19`, `B22`–`B27`, `B40`–`B52`, `B56`–`B59`, `B63`–`B66`, `B69`–`B80`, `B83`, `B85`, `B89` |
| `Backtest_Result` | **0 formula cells** — the entire sheet is pasted values |

### 2.3 Broken / defective references (verified)

| Item | Status | Evidence |
|---|---|---|
| `Stock_Database!O` "Avg Vol (3M)" | **Defect** — returns `Close`, not `Volume` | `O15 = 2690` identical to `N15 = 2690` for AUTO 2025 |
| `Stock_Database_Quarter!O` "Avg Vol (3M)" | **Correct** | AUTO 2026-Q2 = `2449150.847` (volume scale) |
| `SUMMARY!B79` Dividend Safety | **`#REF!`** | Formula references named ranges `Param_Growth` / `Param_Price` |
| `Param_Growth`, `Param_Price`, `Proj_Mode`, `Calc_Method` | **`#REF!` defined names** | `dn.attr_text == '#REF!'` |
| `StockType_Threshold[Min ICR]` | **Column does not exist** | `Reference` defines only `Max DER` (`B31`) and `Min CR` (`C31`); `IFERROR(...,3)` silently defaults the ICR threshold to 3 |
| `SUMMARY!B56` liquidity labels | Text/unit inconsistency | Thresholds use `200000000000` (= 200 **billion** IDR) but labels read `> 200 M` |

**Rule P3 applies:** all of the above are **documented, not corrected**. The
reference model must reproduce them exactly, including the defect.


---

## 3. Web-App Calculation Inventory

### 3.1 What exists

`frontend\src\lib\analysis\` contains exactly 5 modules:

| Module | Exports | Nature |
|---|---|---|
| `valuation.ts` | `getMainValuationMethod`, `classifyFinancialMetric`, `financialMetricStatusLabel`, `FinancialMetricStatus` | **Classification / labelling only** |
| `growth.ts` | `analyzeHistoricalGrowth` | **Narrative insight strings only** |
| `backtest.ts` | `backtestMethodology`, `classifyIntrinsicValuesAbovePrice`, `classifyMethodsAbovePrice`, `classifyMosMain`, `classifyCurrentValuationMos`, `calculateSimulatedVerdict`, `calculateBacktestMetrics`, `closeAtBacktestHorizon`, `countMethodsAboveAnalysisPrice` | **Backtest outcome simulation** |
| `backtest-overview.ts` | `aggregateBacktestOverview`, `buildHistoricalBacktestReadout` | **Aggregation of outcomes** |
| `index.ts` | barrel re-export | — |

### 3.2 What the web app actually computes

| Function | Inputs | Real arithmetic | Notes |
|---|---|---|---|
| `getMainValuationMethod(stockType)` | string | none | `stalwart`/`fast grower` → `"Type & Sector Weighted"`, else `"Peter Lynch / Adaptive"` — mirrors `SUMMARY!B69` |
| `classifyMargin` | string table | `parseFinancialMetricValue` diff, ±0.5 threshold | Operates on **formatted strings** |
| `classifyCashConversion` | string | ratio ≥ 1 / ≥ 0.5 | Threshold-based label |
| `classifyFinancialMetric` (ROE) | string table | 5-value mean, compare latest | Label only |
| `analyzeHistoricalGrowth` | cards + table | parse + sort, no ratios | Produces prose |
| `classifyIntrinsicValuesAbovePrice` | `(number\|null)[]`, price | count `value > price` | Threshold `methodUndervaluedMinimum = 3` of 5 |
| `classifyMosMain` | number | `>= 0.3` | MoS verdict |
| `calculateSimulatedVerdict` | price path | `entry*(1±threshold)` vs `high`/`low` | Uses **High/Low**, not Close |
| `calculateBacktestMetrics` | price path | peak/trough, `price/analysisPrice − 1` | Horizons 3/6/9/12 months |
| `closeAtBacktestHorizon` | price path | last close ≤ horizon | — |
| `aggregateBacktestOverview` | cases | `WIN/total*100` | Success rate |
| `monthsBetween` | ISO dates | month arithmetic | UTC-based |

`backtestMethodology` is the only explicit parameter block in the frontend:

```text
observationMonths: 12
horizonsMonths: [3, 6, 9, 12]
undervalued:            { upsideThreshold: 0.20, downsideThreshold: -0.15 }
overvaluedOrMixed:      { upsideThreshold: 0.15, downsideThreshold: -0.10 }
valuationMethodCount: 5
classification:         { methodUndervaluedMinimum: 3, mosMainThreshold: 0.30 }
```

### 3.3 What the web app does **not** compute

Verified absent from `frontend/`:

- Gross Profit, EPS, BVPS, PER, PBV, DPR, Dividend Yield, Market Cap
- NWC, NWC/Revenue, DER, Current Ratio, ICR
- CAGR, CoV, growth series, historical averages, percentile
- PEG, any of the five intrinsic-value methods, IV consensus, MoS
  (it only *classifies* an already-supplied MoS)
- Health score, business quality, market mood, stock-type classifier
- Projections

**Root cause:** `frontend/src/data/mock-stock-details.ts` (43 KB) is the
temporary runtime source of truth. It is typed as **strings** for most metrics
(`value: string | number`, `marginOfSafety: string`, `potential: string`), and
`parseFinancialMetricValue` / `parseGrowthNumeric` / `parseNumericValue` exist
specifically to un-format those strings.

### 3.4 Mock data is a copy of workbook output (verified)

The mock valuation block reproduces the workbook to full precision:

| Method | Mock value | Workbook `SUMMARY!B13:B17` |
|---|---:|---:|
| `Peter Lynch / Adaptive` | 3567.704684 | 3567.7046840561493 |
| `Type & Sector Weighted` | 2536.600367 | 2536.6003665489575 |
| `Mean Reversion PBV` | 1740.273242 | 1740.2732423202715 |
| `Dividend Discount Model` | 1418.193101 | 1418.1931011077158 |
| `Discounted Earnings` | 2304.882793 | 2304.8827926499084 |

Mock also carries `mosMain` / `mosPeter` / `mosWeight`, `methodologyUrl`,
`evidenceWins` / `evidenceTotal` — i.e. it encodes the **presentation contract**
that Phase 4 must eventually satisfy from the database.

**Mock inconsistency (documented, not fixed):** mock `BVPS` = `2780` while the
workbook `Metric_BVPS_Fwd` = `3567.704684`. The mock mixes the pre-projection
BVPS scale with post-projection multiples.


### 3.5 Forward specification: the calculation test suite

`Testing\` contains **two test modules for a calculation engine that does not
exist**. All ten target modules are missing:

| Expected module | Expected symbols | Exists? |
|---|---|---|
| `supabase/calculation_v1_common.py` | `CalculationError`, `SupabaseRest`, `calculation_contract`, `canonical_json`, `growth_result`, `ratio_result`, `sha256_json` | **NO** |
| `supabase/calculation_v1_runner.py` | `input_hash`, `retry_contract`, `terminal_run_action`, `validate_queued_run` | **NO** |
| `supabase/run_calculation_v1.py` | `CODE_VERSION`, `INSTRUMENT_ID`, `CalculationV1Orchestrator` | **NO** |
| `supabase/calculate_quarterly_growth_quality.py` | `calculate_quarterly_outputs` | **NO** |
| `supabase/calculate_daily_liquidity.py` | `calculate_daily_outputs` | **NO** |
| `supabase/calculate_balance_sheet_liquidity.py` | `calculate_balance_outputs` | **NO** |
| `supabase/calculate_valuation_inputs.py` | `calculate_ttm_flows`, `calculate_valuation_outputs` | **NO** |
| `supabase/persist_valuation_methods.py` | `persistable_method_rows` | **NO** |
| `supabase/calculate_descriptive_classification.py` | `classify_descriptive`, `classify_from_calculation_results` | **NO** |
| `supabase/audit_calculation_availability.py` | `audit_availability`, `verify_ingestion_provenance` | **NO** |

**This test suite is the most precise Phase 4 requirement source in the
repository.** It defines contracts the blueprint must honour:

- `calculation_status` ∈ `{VALID, NOT_CALCULABLE, UNAVAILABLE}`
- Flags: `DENOMINATOR_ZERO`, `NEGATIVE_BASE`, `QUARTERLY_COMPARISON_MISSING`,
  `STATEMENT_SCOPE_UNKNOWN`, `INSUFFICIENT_ROLLING_WINDOW`, `MARKET_CAP_MISSING`,
  `PRICE_MISSING`, `INVENTORY_MISSING`, `NEGATIVE_DENOMINATOR`, `TTM_INCOMPLETE`,
  `POINT_IN_TIME_UNSAFE`, `DIVIDEND_EVENT_DATE_MISSING`
- Methodology codes: `QUARTERLY_GROWTH_QUALITY`, `DAILY_LIQUIDITY`,
  `BALANCE_SHEET_LIQUIDITY`, `VALUATION_INPUTS`, `VALUATION_MULTIPLES`,
  `VALUATION_METHOD_PERSISTENCE`, `CLASSIFICATION_DESCRIPTIVE`,
  `AVAILABILITY_REVISION`
- Metric codes: `VALUATION_INPUT_PRICE_CLOSE`, `VALUATION_INPUT_DIVIDEND_TTM`,
  `VALUATION_MULTIPLE_PE`, `VALUATION_MULTIPLE_P_S`, `VALUATION_MULTIPLE_P_FCF`,
  `LIQUIDITY_DAILY_TURNOVER_20D`, `LIQUIDITY_CURRENT_RATIO`,
  `LIQUIDITY_QUICK_RATIO`, `*_QOQ`
- `code_version` = `stocklens-calc-v1`; `input_vocabulary_version` =
  `canonical-financial-v1`
- Deterministic `input_hash` = SHA-256 of canonical JSON; `idempotency_key`
  derived from type + methodology + code version + cutoff + scope + input hash;
  retries append `retry_of_run_id`
- `calc_valuation_methods` must contain **11 unique method codes**, with `DCF`,
  `DDM`, `GRAHAM`, `RESIDUAL_INCOME` persisted as `value_numeric = NULL` and
  `method_status = 'UNAVAILABLE'`
- **20-day** rolling window for daily turnover
- Expected migration `supabase/migrations/0008_calculation_v1_batch.sql` must
  contain `METHODOLOGY_SEED_CONFLICT`, `existing.status is distinct from 'DRAFT'`,
  `financial_facts_supersedes_not_self`, `dividend_facts_supersedes_not_self`,
  `supersedes_fact_id is null or supersedes_fact_id <> id`,
  `supersedes_dividend_fact_id is null or supersedes_dividend_fact_id <> id`,
  and `Multi-row lineage cycles remain`

**Schema drift the tests already assume** (not yet present in the database):

| Test assumption | Live database | Gap |
|---|---|---|
| `financial_periods.source_ingestion_file_id` | `financial_periods.source_payload_id` | rename/add needed |
| `financial_periods.revision_key` | not present | column needed |
| `financial_facts.supersedes_fact_id` | not present | column needed |
| `dividend_facts.supersedes_dividend_fact_id` | not present | column needed |
| `prices_daily.available_date` | not present | column needed for PIT |
| `methodology_versions`, `calculation_runs` | not present | tables needed |
| `calc_valuation*`, `calc_quarterly_*`, `calc_liquidity_*`, `calc_classification`, `calc_availability_audit` | not present | tables needed |

### 3.6 Three engines, three vocabularies (unification note)

Phase 4 must reconcile **three** naming systems:

| Concept | Excel | Forward test spec | Frontend mock |
|---|---|---|---|
| Peter Lynch method | `Peter Lynch Algo IV` | — | `Peter Lynch / Adaptive` |
| Weighted method | `Type & Sector Weighted IV` | — | `Type & Sector Weighted` |
| PBV mean reversion | `Mean Reversion PBV IV` | — | `Mean Reversion PBV` |
| DDM | `Dividend Discount Model IV` | `DDM` | `Dividend Discount Model` |
| Discounted earnings | `Discounted Earnings Model IV` | `DCF` | `Discounted Earnings` |
| Liquidity | `Third Liner / Illiquid (< 10 M)` | `LIQUIDITY_DAILY_TURNOVER_20D` | — |

A single **method-code registry** is required before persistence so that
`calc_valuation_methods.method_code` is stable and the API contract does not
leak Excel prose.

---

## 4. PostgreSQL Source Mapping

### 4.1 Live schema (verified)

12 tables in `public`. Migrations applied: `0001_stocklens_mvp`, `0002_raw_storage`,
`0003_prices_source_ingestion_file`.

| Table | Rows | Grain |
|---|---:|---|
| `data_sources` | 1 | one provider |
| `ingestion_runs` | 62 | one execution |
| `raw_ingestion_payloads` | 0 | — |
| `companies` | 1 | one issuer |
| `instruments` | 1 | one listed security |
| `sectors` | 1 | one taxonomy node |
| `instrument_sector_classifications` | 1 | one instrument×sector |
| `financial_periods` | 33 | one instrument×period |
| `financial_facts` | 1.213 | one period×metric |
| `prices_daily` | 1.619 | one instrument×date |
| `dividend_facts` | 16 | one instrument×fact |
| `ingestion_files` | 60 | one archived object |

### 4.2 Column reference (calculation-relevant)

**`financial_periods`** — `id`, `instrument_id`, `period_type`
(`ANNUAL`/`QUARTER`), `period_label` (`2019`…`2025`, `2020-Q1`…`2026-Q2`),
`period_start`, `period_end`, `report_date`, `available_date`, `period_basis`,
`statement_scope`, `source_payload_id`.

**`financial_facts`** — `id`, `financial_period_id`, `metric_code`,
`value_numeric`, `unit_code`, `currency_code`, `source_field`, `revision_key`
(default `CURRENT`), `quality_status` (default `VALID`), `source_payload_id`.

**`prices_daily`** — `id`, `instrument_id`, `trading_date`, `open_price`,
`high_price`, `low_price`, `close_price`, `volume`, `market_cap`,
`currency_code` (default `IDR`), `source_payload_id`,
`source_ingestion_file_id`.

**`dividend_facts`** — `id`, `instrument_id`, `fact_type`, `period_year`,
`event_date`, `amount_per_share`, `yield_ratio`, `currency_code`,
`source_label`, `source_payload_id`.

**`instruments`** — `id`, `ticker`, `provider_symbol`, `currency_code`
(default `IDR`).

**`ingestion_files`** — `id`, `ingestion_run_id`, `source_file_type`,
`storage_bucket`, `storage_path`, `checksum_sha256`, `record_count`,
`first_record_date`, `last_record_date`, `status`, `created_at`.

### 4.3 Metric vocabulary actually present

`financial_facts` holds **48 distinct `metric_code` values**.

| Facts | Metric codes |
|---:|---|
| 33 (7 annual + 26 quarter) | `CAPITAL_EXPENDITURE`, `CASH_ONLY`, `COST_OF_REVENUE`, `CURRENT_LIABILITIES`, `EARNINGS`, `EARNINGS_BEFORE_TAX`, `EBIT`, `EBITDA`, `FINANCING_CASH_FLOW`, `FREE_CASH_FLOW`, `GROSS_PROFIT`, `INVESTING_CASH_FLOW`, `NET_CASH_FLOW`, `NON_OPERATING_INCOME_OR_LOSS`, `OPERATING_CASH_FLOW`, `OPERATING_EXPENSE`, `OPERATING_PNL`, `REVENUE`, `TAX`, `TOTAL_ASSETS`, `TOTAL_DEBT`, `TOTAL_EQUITY`, `TOTAL_LIABILITIES` |
| 26 (quarter only) | `CASH_AND_SHORT_TERM_INVESTMENTS`, `MINORITIES`, `NON_INTEREST_INCOME`, `STOCKHOLDERS_EQUITY`, `TOTAL_CURRENT_ASSET`, `TOTAL_NON_CURRENT_ASSETS`, `TOTAL_NON_CURRENT_LIABILITIES` |
| 7 (annual only) | `CASH_AND_EQUIVALENTS`, `CURRENT_ASSETS`, `FIXED_ASSETS`, `INVENTORIES`, `LONG_TERM_DEBT`, `NET_DEBT`, `NON_CURRENT_LIABILITIES`, `OUTSTANDING_SHARES`, `PREPAID_ASSETS`, `RETAINED_EARNINGS`, `SHORT_TERM_DEBT` |
| 6 (annual only) | `EPS` |
| present but **all NULL** | `NET_PREMIUM_INCOME`, `NON_INTEREST_BEARING_LIABILITIES`, `NON_LOAN_ASSETS`, `PREMIUM_EXPENSE`, `PREMIUM_INCOME`, `PROVISION` (bank/insurance vocabulary, 26 null rows each) |

**Unit codes:** `IDR` (1.200 facts), `IDR_PER_SHARE` (6 — all `EPS`),
`SHARES` (7 — all `OUTSTANDING_SHARES`, `currency_code = NULL`).

**Naming splits that matter (same concept, different period types):**

| Concept | ANNUAL metric | QUARTER metric |
|---|---|---|
| Current assets | `CURRENT_ASSETS` | `TOTAL_CURRENT_ASSET` |
| Cash | `CASH_AND_EQUIVALENTS` | `CASH_AND_SHORT_TERM_INVESTMENTS` |
| Current liabilities | `CURRENT_LIABILITIES` | `CURRENT_LIABILITIES` |
| Total equity | `TOTAL_EQUITY` | `TOTAL_EQUITY` |
| Inventory | `INVENTORIES` | **absent** |

A **metric-code alias layer** is therefore required, otherwise any query mixing
annual and quarterly data silently drops or duplicates rows.

### 4.4 Period coverage (verified)

| Period type | Count | Range | `period_basis` | `statement_scope` |
|---|---:|---|---|---|
| `ANNUAL` | 7 | `2019` → `2025` | `UNKNOWN` | `UNKNOWN` |
| `QUARTER` | 26 | `2020-Q1` → `2026-Q2` | `STANDALONE` | `UNKNOWN` |

Facts per period: annual 35–36; quarter 37.

### 4.5 `prices_daily` profile (verified)

| Property | Value |
|---|---|
| Rows | 1.619 |
| Range | `2020-01-02` → `2026-09-24` |
| `close_price` non-null | 1.619 (100%) |
| `volume` non-null | 1.619 (100%) |
| `high_price` / `low_price` non-null | 1.619 (100%) |
| `open_price` non-null | **422 (26%)** |
| `market_cap` non-null | **1.378 (85%)** |
| `source_ingestion_file_id` non-null | 1.619 (100%) |


### 4.6 ⚠️ Correction to the Phase 3 audit: COGS sign

`docs/EXCEL_POSTGRES_VALIDATION.md` §9.1 records COGS 2025 PostgreSQL as
`−16.540.549.000.000`. **The live database stores it positive:**

| Check | Result |
|---|---|
| `COST_OF_REVENUE` 2025 `value_numeric` | `+16.540.549.000.000` |
| `source_field` | `cost_of_revenue` |
| Facts with **negative** `COST_OF_REVENUE` | **0 of 33** |
| Facts with **positive** `COST_OF_REVENUE` | 31 of 33 (2 null) |
| `GROSS_PROFIT` 2025 (stored directly) | `+3.366.225.000.000` |
| Identity check | `19.906.774.000.000 − 16.540.549.000.000 = 3.366.225.000.000` ✅ |

**Consequence:** the Excel formula `Gross Profit = B20 + B21` relies on the
**Excel feed** carrying COGS negative. In canonical PostgreSQL COGS is positive,
so the correct implementation is **subtraction**:

```text
gross_profit = revenue - cost_of_revenue        # canonical (COGS positive)
gross_profit = revenue + cost_of_revenue_excel  # Excel (COGS negative)
```

Both yield the same number. `GROSS_PROFIT` is *also* stored directly in
`financial_facts`, so Phase 4 should prefer the **stored** value and use the
derived form only as a cross-check. This correction is recorded here and does
**not** modify the Phase 3 document or any data.

### 4.7 Point-in-time readiness (verified)

| Field | Populated? | Impact |
|---|---|---|
| `financial_periods.report_date` | **0 of 33** (all NULL) | PIT cannot be established from report date |
| `financial_periods.available_date` | **0 of 33** (all NULL) | PIT cannot be established from availability date |
| `financial_periods.statement_scope` | `UNKNOWN` for all 33 | Consolidation semantics unknown |
| `financial_periods.period_basis` | `UNKNOWN` (annual), `STANDALONE` (quarter) | Annual basis unknown |
| `prices_daily.trading_date` | 100% | Price PIT **is** reliable |
| `ingestion_files.first_record_date` / `last_record_date` | populated | Usable as a coarse availability proxy |

**This is the single largest structural blocker for a faithful PIT engine**
(§11, §16). The forward test suite already anticipates it by requiring a
`POINT_IN_TIME_UNSAFE` flag when `available_date` is NULL.

### 4.8 Dividend profile (verified)

| `fact_type` | Rows | `period_year` | `amount_per_share` | `yield_ratio` | `event_date` |
|---|---:|---|---:|---:|---|
| `ANNUAL_TOTAL` | 7 | 2020…2026 | 42, 26.5, 62, 128, 189, 192, 170 | — | **NULL** |
| `YIELD` | 7 | 2020…2026 | — | 0.04424…0.08566 | **NULL** |
| `PAYOUT_RATIO` | 1 | **NULL** | — | 0.456555896221244 | **NULL** |
| `TTM` | 1 | **NULL** | 229.0 | — | **NULL** |

All 16 rows have `source_label = CURRENT` and `currency_code = IDR`.
**`event_date` is NULL for every row** — so a TTM window cannot be derived from
event dates, and the test suite's `DIVIDEND_EVENT_DATE_MISSING` flag is expected
to fire on the current data. `PAYOUT_RATIO` and `TTM` also lack `period_year`,
so they are not addressable by year.

### 4.9 AUTO canonical values (verified — used throughout §5 and §8)

Annual, billion IDR unless noted:

| Year | Revenue | Gross Profit (stored) | Net Income | OCF | Total Equity | Shares (raw) | EPS | Int. Exp (raw) |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 2019 | 15444.775 | *null* | 739.672 | 1072.057 | 11650.534 | 4.819.733.000 | *null* | 83.117.000.000 |
| 2020 | 11869.221 | 1580.106 | −1.020 | 1148.276 | 11270.791 | 4.819.730.941 | −0.21163 | 68.579.000.000 |
| 2021 | 15151.663 | 1860.738 | 611.348 | 911.735 | 11845.631 | 4.813.763.780 | 126.83796 | 36.538.000.000 |
| 2022 | 18579.927 | 2689.343 | 1326.575 | 708.436 | 13051.565 | 4.823.909.091 | 275.23085 | 34.084.000.000 |
| 2023 | 18649.065 | 3079.001 | 1842.435 | 1836.306 | 14539.724 | 4.819.733.000 | 382.26910 | 37.246.000.000 |
| 2024 | 19073.703 | 3065.663 | 2033.641 | 1532.735 | 11106.547 | 4.819.733.000 | 421.94059 | 43.840.000.000 |
| 2025 | 19906.774 | 3366.225 | 2205.022 | 1944.258 | 16964.382 | 4.819.733.000 | 457.49879 | 43.486.000.000 |

Derived ratios (verified). `BVPS = TOTAL_EQUITY / OUTSTANDING_SHARES` in
**raw IDR per share** and it **matches Excel directly** (Excel `3,519.8`):

| Year | BVPS (Rp) | NWC (bn) | Current Ratio | DER |
|---:|---:|---:|---:|---:|
| 2020 | 2338.4689 | 2377.983 | 1.856730 | 0.346853 |
| 2021 | 2460.7836 | 2301.350 | 1.532676 | 0.430667 |
| 2022 | 2705.5993 | 3173.398 | 1.682129 | 0.419084 |
| 2023 | 3016.7074 | 3621.343 | 1.835151 | 0.348928 |
| 2024 | 2304.3905 | 4402.172 | 1.982282 | 0.893479 |
| 2025 | 3519.7763 | 5450.640 | 2.205002 | 0.333115 |

**Scaling clarification (important, verified):** Excel's `×1000` exists only
because Excel's `Shares` column is in **Juta** (millions). Canonical
`OUTSTANDING_SHARES` is in **raw units** (4.819.733.000), so
`TOTAL_EQUITY / OUTSTANDING_SHARES` already yields the correct IDR-per-share
figure with **no ×1000**. Equivalently: `IDR_per_share = (TOTAL_EQUITY/1e9) /
(OUTSTANDING_SHARES/1e6) × 1000`. Applying ×1000 to the raw division is a
**1.000× error** — this is the single most likely scaling bug in Phase 4.

The same applies to EPS: canonical `EPS` is stored at the correct scale
(2025 = `457.4987867585196`) and equals `EARNINGS / OUTSTANDING_SHARES`
(`2205022000000 / 4819733000 = 457.4987867`) with no extra factor.

Whole-series statistics (verified): `n = 7`, `AVG(revenue) = 16953.5897 bn`,
`STDEV.P/AVG = 0.15781626`, `RRI(6, min, max) = 0.09000823`.

### 4.10 Latest-quarter values (verified)

AUTO `2026-Q2`: Revenue `5595.855` bn, COGS `4749.754` bn, Net Income `592.486` bn,
OCF `339.738` bn, Total Equity `17195.384` bn, Total Current Asset `11056.363` bn,
Current Liabilities `5459.244` bn, Total Liabilities `6686.521` bn,
Interest Expense `9.224` bn, `OUTSTANDING_SHARES` **absent (NULL)**.

`OUTSTANDING_SHARES` exists **only for annual periods** (7 rows). Quarterly share
counts are not in `financial_facts` — see §8 (gap `G-SHARES-Q`).

### 4.11 Daily-price usage — which fields the workbook uses

`tblPriceHistory_DB` columns: `Ticker, Date, Open, High, Low, Close, Volume, Market Cap`.

Formula-reference scan across the whole workbook:

| Column | Formula references | Verdict |
|---|---:|---|
| `[Date]` | 1.066 | **USED** — as-of matching key |
| `[Close]` | 1.066 | **USED** — point-in-time price |
| `[Volume]` | 412 | **USED** — 3-month average |
| `[Open]` | **0** | **NOT USED** |
| `[High]` | **0** | **NOT USED** |
| `[Low]` | **0** | **NOT USED** |
| `[Market Cap]` | **0** | **NOT USED** |

**Confirmed NOT used by the workbook:** `Open`, `High`, `Low`, `Market Cap`.
This matches the database profile in §4.5, where `open_price` is only 26%
populated and `market_cap` 85%.

#### 4.11.1 What daily price is actually used for

| Purpose | Used? | Evidence |
|---|---|---|
| Chart / sparkline | **NO** | no chart series refs |
| Return (`Close/Close_prev − 1`) | **NO** | no such pattern |
| Moving average of price | **NO** | `AVERAGE` appears only over `Volume` |
| Mean reversion of **price** | **NO** | "Mean Reversion" is **PBV**-based (`ValuationCurrent!B27`) |
| Volatility of **price** | **NO** | volatility is over **Revenue** (`MetricsClassification!B10`) |
| **Liquidity** | **YES** | `SUMMARY!B56` = `AvgVol(3M) × Price` vs thresholds |
| Technical signal | **NO** | none |
| **Point-in-time valuation price** | **YES** | `Stock_Database!N`, `Stock_Database_Quarter!P` |

#### 4.11.2 Exact daily-price formulas

**Annual year-end price — `Stock_Database!N` (all rows):**

```text
LET(
  ticker,  [#This Row Ticker],
  asof,    DATE([#This Row Year], 12, 31),
  IFERROR(
    XLOOKUP(1,
      (tblPriceHistory_DB[Ticker]=ticker) * (tblPriceHistory_DB[Date]<=asof),
      tblPriceHistory_DB[Close], "", 0, -1),
    ""))
```

= last available `Close` on or before 31-Dec of that year (backward search `-1`).

**Quarterly 3M average volume — `Stock_Database_Quarter!O` (all rows):**

```text
LET(
  ticker,    [#This Row Ticker],
  asof,      [#This Row Data Available Date],
  startdate, EDATE(asof, -3),
  IFERROR(AVERAGEIFS(tblPriceHistory_DB[Volume],
      tblPriceHistory_DB[Ticker], ticker,
      tblPriceHistory_DB[Date], ">="&startdate,
      tblPriceHistory_DB[Date], "<="&asof), ""))
```

= **simple mean** of daily `Volume` over the 3 calendar months ending at the
`Data Available Date`. **Not** a 63-trading-day rolling window, and **not** adjusted
for missing days.

**Quarterly price — `Stock_Database_Quarter!P`:** identical to `N` but
`asof = Data Available Date`.

**Annual `Avg Vol (3M)` — `Stock_Database!O`:** **defective** — its formula is
identical to `N` and therefore returns `Close`, not `Volume`. Cached values confirm
it: AUTO 2025 `N15 = 2690` and `O15 = 2690`. **Documented, not fixed** (rule P3).

#### 4.11.3 Verified reproduction of `Avg Vol (3M)` (2026-Q2)

| Source | Value |
|---|---:|
| Excel `Stock_Database_Quarter!O`, AUTO 2026-Q2 | `2449150.8474576273` |
| PostgreSQL `AVG(volume)` over `2026-03-30 … 2026-06-30` | `2449150.847457627119` |
| PostgreSQL `AVG(volume)` over `EDATE('2026-06-30',-3) … '2026-06-30'` | `2449150.847457627119` |

**Exact match.** Because June has 30 days, `EDATE(asof,-3)` = `2026-03-30` coincides
with the interval form. Implementation should use the `EDATE` form to stay faithful
for 31-day months.

#### 4.11.4 Verified point-in-time price reproduction

| As-of | Excel (`Stock_Database!N`) | PostgreSQL last close ≤ as-of |
|---|---:|---|
| 2025-12-31 | 2690 | 2690 (`2025-12-30`) |
| 2024-12-31 | 2300 | 2300 (`2024-12-30`) |
| 2023-12-31 | 2360 | 2360 (`2023-12-29`) |
| 2022-12-31 | 1460 | 1460 (`2022-12-30`) |
| 2021-12-31 | 1155 | 1155 (`2021-12-30`) |
| 2020-12-31 | 1115 | 1115 (`2020-12-30`) |
| 2026-06-30 (workbook as-of) | 2350 | 2350 |
| latest available | — | **3340** (`2026-09-24`) |

**PIT rule (P4):** `current_price` must be resolved against the requested as-of date.
The workbook's `2350` is the 2026-Q2 close; the database's latest `3340` is a
*different date*, not a different value. Phase 4 must never substitute the latest
close for an as-of close.

---

## 5. Calculation-by-Calculation Mapping

Every metric uses the same 17-field structure. To keep the document readable,
each metric is a compact block; field order is identical throughout.

**Field legend**

| Field | Meaning |
|---|---|
| **Ref** | Excel worksheet/cell/formula reference |
| **Means** | What the metric means |
| **Web** | Web-app equivalent, if any |
| **Source** | PostgreSQL source table(s) |
| **Fields** | PostgreSQL field(s) |
| **Kind** | Direct / Derived |
| **Transform** | Required transformations |
| **Unit** | Output unit |
| **As-of** | As-of-date behaviour |
| **Hist** | Historical-series requirement |
| **Proj** | Projection requirement |
| **Params** | Parameters / thresholds / weights |
| **AUTO** | Current AUTO example value |
| **Valid** | Validation status |
| **Gap** | Gap class (A/B/C/D) |
| **Impl** | Implementation notes |

### 5.1 Metric index

| # | Metric | Gap | Excel sheet |
|---:|---|:--:|---|
| 1 | Gross Profit | **A** | `DataInput!B27` |
| 2 | EPS | **A** | `DataInput!B30` |
| 3 | BVPS | **B** | `DataInput!B42` |
| 4 | PER | **B** | `DataInput!B31` |
| 5 | PBV | **B** | `DataInput!B43` |
| 6 | DPR | **B** | `DataInput!B28` |
| 7 | Dividend Yield | **B** | `DataInput!B29` |
| 8 | Market Cap | **B** | `DataInput!B14` |
| 9 | NWC | **B** | `DataInput!B36` |
| 10 | NWC / Revenue | **B** | `DataInput!B36/B20` |
| 11 | DER | **B** / **C** | `FinancialHealth!B8` |
| 12 | Current Ratio | **B** | `FinancialHealth!B9` |
| 13 | ICR | **B** | `FinancialHealth!B10` |
| 14 | Revenue CAGR | **B** | `MetricsClassification!B7`,`B8` |
| 15 | Revenue CoV | **B** | `MetricsClassification!B10` |
| 16 | Revenue Growth YoY | **B** | `MetricsClassification!B11` |
| 17 | Asset Growth Gap | **B** | `MetricsClassification!B18` |
| 18 | NWC Intensity Change | **B** | `MetricsClassification!B20` |
| 19 | EPS Annualized | **B** | `MetricsClassification!B25` |
| 20 | PEG | **B** | `MetricsClassification!B30` |
| 21 | Dividend Yield Average | **B** | `MetricsClassification!B32` |
| 22 | Payout Average | **B** | `MetricsClassification!B34` |
| 23 | PER historical average | **B** | `MetricsClassification!B36` |
| 24 | PBV historical average | **B** | `MetricsClassification!B37` |
| 25 | PBV percentile | **B** | `MetricsClassification!B39` |
| 26 | Peter Lynch Algo IV | **B** | `ValuationCurrent!B25` |
| 27 | Type & Sector Weighted IV | **B** / **C** | `ValuationCurrent!B26` |
| 28 | Mean Reversion PBV IV | **B** | `ValuationCurrent!B27` |
| 29 | DDM IV | **B** / **C** | `ValuationCurrent!B28` |
| 30 | Discounted Earnings IV | **B** / **C** | `ValuationCurrent!B29` |
| 31 | IV Consensus | **B** | `SUMMARY!B19` |
| 32 | MoS | **B** | `SUMMARY!D13:D17`,`B75` |
| 33 | Liquidity Score | **B** | `SUMMARY!B56` |
| 34 | Total Health Score | **B** | `FinancialHealth!B26` |
| 35 | Business Quality | **B** / **C** | `SUMMARY!B57:B59` |
| 36 | Market Mood | **C** | `SUMMARY!B63:B66` |
| 37 | Strategic Target | **B** | `SUMMARY!B73` |
| 38 | Ideal Price | **B** | `SUMMARY!B80` |


### 5.2 Gross Profit

- **Ref** `DataInput!B27` = `IF(OR(B20="",B21=""),"",B20+B21)`; `Range_Gross_Profit` = `OFFSET(DataInput!$C$27,0,0,1,Years_Avail)`
- **Means** Revenue less cost of revenue for a period.
- **Web** none.
- **Source** `financial_facts` (ANNUAL + QUARTER), or derived.
- **Fields** `GROSS_PROFIT` (stored), or `REVENUE` − `COST_OF_REVENUE`.
- **Kind** **Direct** (stored `GROSS_PROFIT` exists for all 33 periods).
- **Transform** `÷ 1e9` for Excel parity; see §4.6 for the COGS sign correction.
- **Unit** IDR canonical; Excel column labelled `(M Rp)` but is billion IDR.
- **As-of** Per `financial_period_id`.
- **Hist** 7 annual values for `Range_Gross_Profit`; 26 quarterly.
- **Proj** none.
- **Params** none.
- **AUTO** 2025 = `3.366.225.000.000` IDR (`3366.225` bn), matches Excel `3,366.2` ✅. 2019 stored = `2188.244` bn but Excel shows `15,444.8` (Excel `B21` COGS blank for 2019 → falls back to Revenue) — **known Excel artifact, not fixed**.
- **Valid** ✅ reconciled (Phase 3 §9.4).
- **Gap** **A** — directly replicable.
- **Impl** Prefer stored `GROSS_PROFIT`; keep `revenue − cogs` as an assertion. Do **not** reproduce the Excel 2019 blank-COGS artifact unless bit-exact parity is required; document the divergence.

### 5.3 EPS

- **Ref** `DataInput!B30` = `IFERROR(B23/B41*1000,"No Data")`; `Range_EPS` = `OFFSET(DataInput!$C$30,0,0,1,Years_Avail)`
- **Means** Net income attributable per outstanding share.
- **Web** none (mock has `EPS (TTM) = 477.8` as a string).
- **Source** `financial_facts` (`EPS`) or `EARNINGS` ÷ `OUTSTANDING_SHARES`.
- **Fields** `EPS` (`unit_code = IDR_PER_SHARE`), `EARNINGS`, `OUTSTANDING_SHARES`.
- **Kind** **Direct** — `EPS` stored for 6 annual periods.
- **Transform** `EPS_canonical = EARNINGS / OUTSTANDING_SHARES` — **no ×1000 needed** (stored `EPS` confirms this, §4.9). Excel's `×1000` compensates only for its `Juta` share column.
- **Unit** IDR per share.
- **As-of** Per annual period; annual only.
- **Hist** 6 values (2019 missing → `Range_EPS` has a gap).
- **Proj** **YES** for forward EPS (`Metric_EPS_Fwd`), see §9.
- **Params** none.
- **AUTO** 2025 = `457.4987867585196` (Excel `457.5`) ✅
- **Valid** ✅ reconciled.
- **Gap** **A** (historical) / **C** (forward).
- **Impl** Store EPS at full `numeric` precision; never round-trip through display strings (the current frontend does, losing precision).

### 5.4 BVPS

- **Ref** `DataInput!B42` = `IFERROR(B40/B41*1000,"No Data")`, `B40 = Proj_Equity`, `B41 = Proj_Shares`; `Range_BVPS` = `OFFSET(DataInput!$C$42,...)`
- **Means** Book value per share.
- **Web** none (mock `BVPS = 2780`, inconsistent with workbook `3567.704684`).
- **Source** `financial_facts`.
- **Fields** `TOTAL_EQUITY`, `OUTSTANDING_SHARES`.
- **Kind** **Derived** (not stored).
- **Transform** `BVPS = TOTAL_EQUITY / OUTSTANDING_SHARES` → **no ×1000 needed** (see §4.9 scaling clarification). Excel's `×1000` exists only because its `Shares` column is in Juta.
- **Unit** IDR per share.
- **As-of** Period end.
- **Hist** 6 annual values (2019 has equity but no shares → excluded).
- **Proj** **YES** — `B40`/`B41` are `Proj_Equity`/`Proj_Shares`, so the workbook's headline BVPS is **forward-looking**.
- **Params** none.
- **AUTO** 2025 actual = `3519.7763` (Excel `3,519.8`) ✅; projected = `3567.7046840561493` (Excel `3,567.7`) ✅
- **Valid** ✅ both reconciled.
- **Gap** **B** (historical) / **C** (projected).
- **Impl** Two distinct outputs must not be conflated: `bvps_actual` (annual) and `bvps_fwd` (projection). The mock's `2780` matches neither.

### 5.5 PER

- **Ref** `DataInput!B31` = `IF(OR(B25="",B30=""),"",IFERROR(B25/B30,0))`; forward `MetricsClassification!B28 = IFERROR(Metric_Price_Current/Metric_EPS_Fwd,0)`
- **Means** Price-to-earnings multiple.
- **Web** none (mock `"P/E Ratio": "4,92x"` string).
- **Source** `prices_daily` + `financial_facts`.
- **Fields** `close_price`, `EPS` (or `EARNINGS`, `OUTSTANDING_SHARES`).
- **Kind** **Derived**.
- **Transform** `PER = price_asof / EPS_period`.
- **Unit** x.
- **As-of** **Critical** — numerator is the year-end/quarter-end PIT price, denominator the period EPS.
- **Hist** 6–7 values feeding `Range_Stock_Price/Range_EPS`.
- **Proj** **YES** for `PER (Proj)`.
- **Params** none.
- **AUTO** 2025 = `2690 / 457.4987867585196 = 5.879797` (Excel `5.9`) ✅; projected `4.918372530798526` (Excel `4.92x`) ✅
- **Valid** ✅ reconciled.
- **Gap** **B**.
- **Impl** Must guard `EPS <= 0` (Excel produces `−5,268.6` for 2020). The forward test spec expects `NOT_CALCULABLE` with `DENOMINATOR_ZERO` / `NEGATIVE_BASE` flags instead of a raw negative multiple — **decide and document** which behaviour wins.

### 5.6 PBV

- **Ref** `DataInput!B43` = `IF(OR(B25="",B42=""),"",IFERROR(B25/B42,0))`; forward `MetricsClassification!B29`
- **Means** Price-to-book multiple.
- **Web** none (mock `"P/BV Ratio": "0,66x"` string).
- **Source** `prices_daily` + `financial_facts`.
- **Fields** `close_price`, `TOTAL_EQUITY`, `OUTSTANDING_SHARES`.
- **Kind** **Derived**.
- **Transform** `PBV = price_asof / BVPS_period`.
- **Unit** x.
- **As-of** PIT price / period-end equity.
- **Hist** 6 annual values (feeds `Range_PBV`).
- **Proj** **YES** for `PBV (Proj)`.
- **Params** none.
- **AUTO** 2025 = `2690 / 3519.7763030 = 0.764253` (Excel `0.8`) ✅; projected `0.6586868051332847` (Excel `0.66x`) ✅
- **Valid** ✅ reconciled.
- **Gap** **B**.
- **Impl** The **quarterly** PBV series is what drives `Mean Reversion PBV IV` (§5.28) — see the verified reproduction there.

Supporting metrics required by the above are mapped in §5.40–§5.48.


### 5.7 DPR (Dividend Payout Ratio)

- **Ref** `DataInput!B28` = `B26/B30` (DPS ÷ EPS); `Range_DPR` = `OFFSET(DataInput!$C$28,...)`
- **Means** Share of earnings paid as dividends — **template definition**.
- **Web** none.
- **Source** `dividend_facts` + `financial_facts`.
- **Fields** `ANNUAL_TOTAL.amount_per_share`, `EPS`.
- **Kind** **Derived**.
- **Transform** `DPR = DPS / EPS`. Guard `EPS <= 0` (Excel 2020 = `−19846.0%`).
- **Unit** ratio (Excel displays %).
- **As-of** Per year.
- **Hist** 6 values (2020 negative EPS → `Range_DPR` outlier; `TRIMMEAN(...,0.2)` in §5.22 absorbs it).
- **Proj** **YES** (`Proj_Dividend_Payout_Ratio`).
- **Params** none.
- **AUTO** 2025 = `192 / 457.4987867585196 = 0.419673` (Excel `42.0%`) ✅
- **Valid** ✅ reconciled. Canonical provider `PAYOUT_RATIO = 0.456555896221244` is a **different definition**; both are correct.
- **Gap** **B**.
- **Impl** Expose as separate metric codes (`DPR_TEMPLATE`, `PAYOUT_RATIO_PROVIDER`) to avoid the ambiguity in Phase 3 §10.4.

### 5.8 Dividend Yield

- **Ref** `DataInput!B29` = `B26/B25` (DPS ÷ Price); forward `MetricsClassification!B33` = `IFERROR(Proj_DPS/Metric_Price_Current,0)`
- **Means** Cash dividend return on the point-in-time price.
- **Web** none (mock `"Dividend Yield": "4,83%"` string).
- **Source** `dividend_facts` + `prices_daily`.
- **Fields** `ANNUAL_TOTAL.amount_per_share`, `close_price` (as-of).
- **Kind** **Derived**.
- **Transform** `Yield = DPS_year / price_asof_year_end`.
- **Unit** ratio.
- **As-of** **Critical** — year-end PIT price, not latest.
- **Hist** 6 values.
- **Proj** **YES** (`Metric_Yield_Fwd`).
- **Params** Threshold `0.04` (4%) at `SUMMARY!B51`.
- **AUTO** 2025 = `192 / 2690 = 0.071375` (Excel `7.1%`) ✅; projected `0.04833694162122452` (Excel `4.83%`) ✅
- **Valid** ✅ reconciled.
- **Gap** **B**.
- **Impl** Provider `dividend_facts.YIELD` (2025 = `0.0856624320149422`) differs from the template's `0.071375` because of a different price basis. Keep both; label clearly.

### 5.9 Market Cap

- **Ref** `DataInput!B14` = `Current_Price*B13/1000`
- **Means** Equity market capitalisation.
- **Web** none.
- **Source** `prices_daily` + `financial_facts`.
- **Fields** `close_price` (as-of), `OUTSTANDING_SHARES`.
- **Kind** **Derived**.
- **Transform** `market_cap = price_asof × OUTSTANDING_SHARES / 1e9` for Excel `(M Rp)` parity.
- **Unit** IDR canonical (Excel: billion IDR).
- **As-of** **Critical** — must use the as-of price.
- **Hist** no (single current value in `DataInput`).
- **Proj** none.
- **Params** none.
- **AUTO** Excel = `11326.37255`; recompute `2350 × 4.819.733.000 ÷ 1e9 = 11326.372` ✅ (workbook 2026-Q2 price `2350`).
- **Valid** ✅ reconciled (with the as-of price).
- **Gap** **B**.
- **Impl** `prices_daily.market_cap` exists for 1.378 of 1.619 rows and is **not used by Excel**. Prefer computing from `price × shares`; treat the provider column as a cross-check. Provide a `MARKET_CAP_MISSING` flag path.

### 5.10 NWC (Net Working Capital)

- **Ref** `DataInput!B36` = `B37-B38` (Current Assets − Current Liabilities)
- **Means** Short-term operating liquidity buffer.
- **Web** none.
- **Source** `financial_facts`.
- **Fields** `CURRENT_ASSETS` (annual) / `TOTAL_CURRENT_ASSET` (quarter), `CURRENT_LIABILITIES`.
- **Kind** **Derived**.
- **Transform** subtraction, after applying the **period-type alias** from §4.3.
- **Unit** IDR (Excel billion).
- **As-of** Period end.
- **Hist** 6 annual; 26 quarterly.
- **Proj** **YES** (`Proj_Assets_Curr − Proj_Liab_Curr`).
- **Params** none.
- **AUTO** 2025 = `9973.987 − 4523.347 = 5450.640` bn (Excel `5,450.6`) ✅; projected `11056.363 − 5459.244 = 5597.119` (Excel `5,597.1`) ✅
- **Valid** ✅ reconciled.
- **Gap** **B**.
- **Impl** Alias resolution is mandatory: querying only `CURRENT_ASSETS` silently returns NULL for all quarterly periods.

### 5.11 NWC / Revenue

- **Ref** `DataInput!B35` = `B36/B20` (NWC ÷ Revenue)
- **Means** Working-capital intensity relative to revenue.
- **Web** none.
- **Source** `financial_facts`.
- **Fields** NWC inputs + `REVENUE`.
- **Kind** **Derived**.
- **Transform** division; guard `REVENUE = 0`.
- **Unit** ratio.
- **As-of** Period.
- **Hist** 6 values (feeds NWC intensity change).
- **Proj** **YES**.
- **Params** none.
- **AUTO** 2025 = `5450.640 / 19906.774 = 0.273808` (Excel `27.38%`) ✅
- **Valid** ✅ reconciled.
- **Gap** **B**.
- **Impl** Also produced at `MetricsClassification!B19` via `INDEX(Range_Curr_Assets,1)`. Index `1` = **latest** period, since `DataInput` columns run newest-first (`C` = latest, `I` = oldest).


### 5.12 DER (Debt-to-Equity Ratio)

- **Ref** `FinancialHealth!B8` = `IF(OR(Proj_Equity=0,Proj_Equity=""),"No Data", Metric_Liabilities_Total / Proj_Equity)`
- **Means** Leverage: total liabilities ÷ equity.
- **Web** none (mock has a `"Debt / Equity"` label in `financialHealth`).
- **Source** `financial_facts`.
- **Fields** `TOTAL_LIABILITIES`, `TOTAL_EQUITY`.
- **Kind** **Derived**.
- **Transform** division. **Two variants exist:**
  1. `der_actual = TOTAL_LIABILITIES / TOTAL_EQUITY` (same period)
  2. `der_template = Metric_Liabilities_Total / Proj_Equity` (**mixes** a current liability with a **projected** equity denominator)
- **Unit** x.
- **As-of** Latest balance sheet (annual) for liabilities; projection for equity.
- **Hist** 6 values for thresholds/trend.
- **Proj** **YES** for the template variant.
- **Params** `Reference!B32:C37` Max-DER by stock type: Slow Grower `0.5`, Stalwart `0.8`, Fast Grower `1.0`, Cyclical `0.3`, Turn Around `0.5`, Asset Play `0.4`. Overrides: Financials `15`, Properties `2`. Fallback `1`.
- **AUTO** Excel `0.32864034906112016`; `der_actual` 2025 = `5651.097/16964.382 = 0.333115` ⚠️
- **Valid** ⚠️ **intentional mismatch** (Phase 3 §10.2) — projected equity denominator, by design.
- **Gap** **B** (`der_actual`) / **C** (`der_template`, needs projection).
- **Impl** Persist **both** as separate metric codes (`DER_ACTUAL`, `DER_PROJECTED`) so the difference is auditable rather than looking like a data error.

### 5.13 Current Ratio

- **Ref** `FinancialHealth!B9` = `IF(OR(Metric_Assets_Current=0,Metric_Liabilities_Current=0),"No Data", Metric_Assets_Current / Metric_Liabilities_Current)`
- **Means** Short-term solvency.
- **Web** none.
- **Source** `financial_facts`.
- **Fields** `CURRENT_ASSETS` / `TOTAL_CURRENT_ASSET`, `CURRENT_LIABILITIES`.
- **Kind** **Derived**.
- **Transform** division; guard zero denominator (`NEGATIVE_DENOMINATOR` flag exists in the test spec).
- **Unit** x.
- **As-of** Latest period end.
- **Hist** optional.
- **Proj** no (Excel uses actual `Metric_*`).
- **Params** `Reference!C32:C37` Min-CR by type: Slow Grower `1.5`, Stalwart `1.3`, Fast Grower `1.2`, Cyclical `2.0`, Turn Around `1.5`, Asset Play `1.5`. Fallback `1`.
- **AUTO** Excel `2.2050015176814868`; recompute `9973.987/4523.347 = 2.205002` ✅
- **Valid** ✅ reconciled.
- **Gap** **B**.
- **Impl** The test spec also defines `LIQUIDITY_QUICK_RATIO`, which needs `INVENTORIES` — **absent for quarterly periods** → must emit `INVENTORY_MISSING` + `UNAVAILABLE` (the test asserts exactly this).

### 5.14 ICR (Interest Coverage Ratio)

- **Ref** `FinancialHealth!B10`:
  ```text
  LET(IsBank, ISNUMBER(SEARCH("Financials",Company_Sector)),
      InterestExp, Metric_Interest_Exp_Current,
      IF(IsBank, "N/A (Bank)",
        IF(InterestExp=0, "N/A (No Interest Expense)",
          (Metric_NetIncome_Current - InterestExp) / ABS(InterestExp))))
  ```
- **Means** Ability to cover interest from earnings. **The numerator is Net Income, not EBIT** — the label "Interest Coverage" is misleading.
- **Web** none.
- **Source** `financial_facts`.
- **Fields** `EARNINGS` (as `Metric_NetIncome_Current`), `INTEREST_EXPENSE_NON_OPERATING`.
- **Kind** **Derived**.
- **Transform** `(earnings − interest) / ABS(interest)`; bank bypass; zero-interest bypass.
- **Unit** x.
- **As-of** Latest period.
- **Hist** optional.
- **Proj** no.
- **Params** Type threshold via `Ref_Type_MinICR` → **column does not exist** → `IFERROR(...,3)` silently uses `3`.
- **AUTO** `(2205.022 − 43.486) / 43.486 = 49.706`.
- **Valid** ⚠️ formula semantics confirmed; the name is misleading.
- **Gap** **B**, with a **D** sub-gap for the missing `Min ICR` reference column.

### 5.15 Revenue CAGR

- **Ref** `MetricsClassification!B7` (full history) and `B8` (comparison window):
  ```text
  B7 = IFERROR(RRI(Years_Avail-1, INDEX(Range_Revenue,Years_Avail), INDEX(Range_Revenue,1)), 0)
  B8 = IFERROR(RRI(Years_Compare, INDEX(Range_Revenue,Years_Compare+1), INDEX(Range_Revenue,1)), 0)
  ```
- **Means** Compound annual growth rate of revenue.
- **Web** none (`growth.ts` consumes a pre-computed `cagrValue` string).
- **Source** `financial_facts.REVENUE` (ANNUAL).
- **Fields** `value_numeric` ordered by `period_end`.
- **Kind** **Derived** (time-series aggregate).
- **Transform** `RRI = (end/start)^(1/n) − 1`. Requires ascending-by-date ordering, then index from the **end** (Excel `INDEX(...,1)` = newest).
- **Unit** ratio.
- **As-of** Series ending at the latest audited year.
- **Hist** **YES** — needs the full ordered revenue series.
- **Proj** no.
- **Params** `Years_Avail` (7), `Years_Compare` (5); `B5 = IFS(Years_Avail>=7→5; >=5→3; >=3→2; TRUE→0)`.
- **AUTO** `B7 = 0.04320553666520399` (`4.32%`), `B8 = 0.10895962318518992` (`10.90%`). Whole-series `RRI(6, min, max) = 0.09000823` is **different** — Excel uses first/last **in series order**, not `min`/`max`.
- **Valid** ✅ verified via ordering semantics.
- **Gap** **B**.
- **Impl** Ordering is the trap: `INDEX(Range_Revenue,1)` = **newest**. Replicate with explicit `ORDER BY period_end DESC`.

### 5.16 Revenue CoV (Coefficient of Variation)

- **Ref** `MetricsClassification!B10` = `STDEV.P(Range_Revenue) / AVERAGE(Range_Revenue)`
- **Means** Revenue volatility — the workbook's only volatility metric, and it is on **revenue, not price**.
- **Web** none.
- **Source** `financial_facts.REVENUE`.
- **Kind** **Derived**.
- **Transform** **population** standard deviation (`STDEV.P`), not sample.
- **Unit** ratio.
- **As-of** Series to latest audited year.
- **Hist** **YES**.
- **Proj** no.
- **Params** none.
- **AUTO** `0.15781626002544882` (`15.78%`); verified `stddev_pop/avg = 0.15781626` ✅
- **Valid** ✅ reconciled (Phase 3 §9.4).
- **Gap** **B**.
- **Impl** Using `stddev_samp` instead of `stddev_pop` silently changes the number. This metric drives the Cyclical classifier (§5.46) — high impact.

### 5.17 Revenue Growth YoY

- **Ref** `MetricsClassification!B11` = `INDEX(Range_Revenue,1) / INDEX(Range_Revenue,2) - 1`
- **Means** Latest-year revenue growth versus prior year.
- **Web** none.
- **Source** `financial_facts.REVENUE`.
- **Kind** **Derived**.
- **Transform** `rev_latest / rev_prior − 1`; guard zero prior.
- **Unit** ratio.
- **As-of** Latest two annual periods.
- **Hist** 2 values.
- **Proj** no.
- **Params** none.
- **AUTO** `19906.774 / 19073.703 − 1 = 0.043676416687415065` (`4.37%`) ✅
- **Valid** ✅ reconciled.
- **Gap** **B**.
- **Impl** Trivial once ordering is correct.

### 5.18 Asset Growth Gap

- **Ref** `MetricsClassification!B18` = `IFERROR(Metric_Rev_Growth_Actual - Metric_Curr_Assets_Growth, "")`; feeds `FinancialHealth!B14`
- **Means** Forensic check: is the balance sheet growing faster than the business?
- **Web** none.
- **Source** `financial_facts`.
- **Fields** `REVENUE`, `CURRENT_ASSETS` / `TOTAL_CURRENT_ASSET`.
- **Kind** **Derived**.
- **Transform** two growth rates differenced. `B17` (current-asset growth) = `INDEX(Range_Curr_Assets,1)/INDEX(Range_Curr_Assets,2) − 1`.
- **Unit** ratio (ppt).
- **As-of** Latest two annual periods.
- **Hist** 2 values each series.
- **Proj** no.
- **Params** Flags at `FinancialHealth!D14`: `< −0.10` severe, `< −0.05` warning, `> 0.05` good, else neutral.
- **AUTO** `0.043676416687415065 − 0.12272273788915 = −0.07904632120173494` (Excel `−7.9%`) ✅
- **Valid** ✅ reconciled.
- **Gap** **B**.
- **Impl** Note the sign convention: **negative gap = healthy** (revenue growing faster than current assets). Easy to invert accidentally.

### 5.19 NWC Intensity Change

- **Ref** `MetricsClassification!B20`:
  ```text
  IFERROR(
    (INDEX(Range_Curr_Assets,1) - INDEX(Range_Curr_Liabilities,1)) / INDEX(Range_Revenue,1)
    -
    (INDEX(Range_Curr_Assets,2) - INDEX(Range_Curr_Liabilities,2)) / INDEX(Range_Revenue,2), "")
  ```
- **Means** Year-over-year change in working-capital intensity.
- **Web** none.
- **Source** `financial_facts`.
- **Kind** **Derived**.
- **Transform** difference of two NWC/Revenue ratios.
- **Unit** ppt (Excel labels `[ppt]` but the cached value `0.043010329117029594` is a **ratio**, i.e. `4.30` ppt).
- **As-of** Latest two annual periods.
- **Hist** 2 values each series.
- **Proj** no.
- **Params** Flags at `FinancialHealth!D15`: `> 0.05` warning, `> 0.02` monitor, `< 0` improving, else stable.
- **AUTO** `0.043010329117029594` (`4.30%` / `4.3` ppt). Excel displays `4.30%` while labelling it `ppt` — **unit/label inconsistency, documented not fixed**.
- **Valid** ✅ reconciled.
- **Gap** **B**.
- **Impl** Preserve the ratio (not ×100) internally; multiply only for display. Document the ppt/% confusion.

- **Impl** Implement exactly as Excel (Net Income numerator) for parity, but name it `INTEREST_COVERAGE_TEMPLATE`. Optionally expose a correctly-named `EBIT_INTEREST_COVERAGE` using `EBIT` (present in canonical data, unused by Excel) as a clearly separate metric. Requires a product decision — see §18.


### 5.20 EPS Annualized (Proj)

- **Ref** `MetricsClassification!B25` = `IFERROR(Proj_Net_Income / Proj_Shares * 1000, 0)`
- **Means** Forward annualised EPS used as the valuation denominator.
- **Web** none (mock `"EPS (TTM)": 477.8` is **mislabelled** — it is the *projected* EPS, not TTM).
- **Source** `financial_facts` (QUARTER) + projection.
- **Fields** `EARNINGS`, shares from `Proj_Shares` (annual `OUTSTANDING_SHARES`).
- **Kind** **Derived**.
- **Transform** annualisation of the latest-quarter YTD figure, then division by shares. See §9.
- **Unit** IDR per share.
- **As-of** Latest audited quarter.
- **Hist** no (single forward value).
- **Proj** **YES** — fully projection-dependent.
- **Params** none directly.
- **AUTO** `477.8003262836343` (Excel `Rp478`).
- **Valid** ✅ reproduced from workbook logic.
- **Gap** **C** — projection.
- **Impl** `Proj_Net_Income` annualisation rule (from `F15`):
  `Q1 → B15*4`, `Q2 → (B15+C15)*2`, `Q3 → (B15+C15+D15)*(12/9)`, `Q4 → sum(all four)`.
  The `Q3` factor is `12/9` (≈×1.333), a workbook simplification. Reproduce exactly.

### 5.21 PEG

- **Ref** `MetricsClassification!B30` = `IF(Metric_EPS_CAGR_Long<=0,"N/A – EPS growth ≤ 0%", IFERROR(Metric_PE_Fwd/(Metric_EPS_CAGR_Long*100),"N/A"))`
- **Means** Growth-adjusted valuation.
- **Web** none (mock `"PEG Ratio": "0,25x"` string).
- **Source** derived from PER + EPS CAGR.
- **Kind** **Derived**.
- **Transform** `PEG = PE_fwd / (EPS_CAGR_Long × 100)`. **Note the `×100`**: CAGR is a decimal (`0.19967`) multiplied by 100 to become a growth number (`19.967`).
- **Unit** x.
- **As-of** Current.
- **Hist** **YES** (EPS CAGR needs the EPS series).
- **Proj** **YES** (numerator is `PE_fwd`).
- **Params** Guard `EPS_CAGR_Long <= 0` → `N/A`.
- **AUTO** `4.918372530798526 / (0.19967136094934035 × 100) = 0.24632338395521788` (Excel `0.25x`) ✅
- **Valid** ✅ verified.
- **Gap** **B** (formula) / **C** (forward PER input).
- **Impl** The `×100` is easy to miss and produces a 100× error. Also note this uses **EPS** CAGR (`B13`), while most other growth metrics use **Revenue** CAGR.

### 5.22 Dividend Yield Average (Historical)

- **Ref** `MetricsClassification!B32`:
  ```text
  LET(Valid, Range_Stock_Price>0,
      Yield_Hist, FILTER(IFERROR(Range_DPS/Range_Stock_Price,""), Valid),
      IFERROR(TRIMMEAN(Yield_Hist,0.2),0))
  ```
- **Means** Trimmed historical average dividend yield.
- **Web** none (mock `"Dividend Yield Avg (Historical)": "5,18%"` string).
- **Source** `dividend_facts` + `prices_daily`.
- **Kind** **Derived** (time-series aggregate with trim).
- **Transform** element-wise `DPS/price`, filter `price>0`, then **TRIMMEAN with 20% total trim** (10% per tail).
- **Unit** ratio.
- **As-of** Year-end prices.
- **Hist** **YES**.
- **Proj** no.
- **Params** Trim fraction `0.2`.
- **AUTO** `0.05181071727774073` (`5.18%`); verified mean `0.051810717278` ✅
- **Valid** ✅ verified.
- **Gap** **B**.
- **Impl** Excel `TRIMMEAN` with `n=6, pct=0.2` trims `FLOOR(6×0.2/2) = FLOOR(0.6) = 0` per end — so for 6 points it **equals the plain mean**. With 7+ points trimming begins. Implement Excel-compatible `TRIMMEAN` (trim count = `FLOOR(n×pct/2)`), not a naive percentile cut.

### 5.23 Payout Average (Historical)

- **Ref** `MetricsClassification!B34` = `IFERROR(TRIMMEAN(IF(Range_EPS>0, Range_DPS/Range_EPS), 0.2), 0)`
- **Means** Trimmed historical average payout ratio.
- **Web** none (mock `"Payout Ratio Avg (Historical)": "0,27x"` string).
- **Source** `dividend_facts` + `financial_facts`.
- **Kind** **Derived**.
- **Transform** `DPS/EPS` for `EPS>0` only (2020's negative EPS is excluded by the `IF`), then `TRIMMEAN(...,0.2)`.
- **Unit** ratio.
- **As-of** Per year.
- **Hist** **YES**.
- **Proj** **YES** — `DataInputProyeksi!B6` uses `TRIMMEAN(Range_DPR, 0.4)` as the **projected payout** driver.
- **Params** Trim `0.2` (historical) / `0.4` (projection driver).
- **AUTO** `0.2727709642351656` (Excel `0.3x`).
- **Valid** ✅ **verified, including the cause of a subtle divergence:**
  - `dividend_facts` starts at **2020** and has **no 2019 row**.
  - Excel `Stock_Database!H` **has** a 2019 row with `DPS = 0`, and `Range_EPS` includes a derived 2019 EPS (`153.467422`).
  - Excluding 2019: mean = `0.327327936482`.
  - **Including 2019 with `DPS=0`**: mean = `0.272773280401` — matches Excel `0.2727709642351656` to 6 d.p. ✅
- **Gap** **B** — but requires deciding how to represent a **zero-DPS year that has no `dividend_facts` row** (see §18).
- **Impl** This is a real, quantified divergence source: a missing dividend row must be treated as **DPS = 0 for average purposes**, not as "year absent". If Phase 4 naively averages only existing `dividend_facts` rows it will report `0.3273` where Excel reports `0.2728` — a **20% relative error** on a displayed metric. Must be handled explicitly and documented as a deliberate replication choice.



### 5.24 PER Historical Average

- **Ref** `MetricsClassification!B36`:
  ```text
  LET(Valid, (Range_Stock_Price>0) * (Range_EPS > AVERAGE(Range_EPS)*0.25),
      PE_Hist, FILTER(IFERROR(Range_Stock_Price/Range_EPS,""), Valid),
      IFERROR(AVERAGE(PE_Hist),""))
  ```
- **Means** Average historical PER, used as the fair multiple.
- **Web** none (mock `"PER Avg (Historical)": "6,38x"` string).
- **Source** `prices_daily` + `financial_facts`.
- **Kind** **Derived**.
- **Transform** element-wise `price/EPS`, **filter** `price>0` **and** `EPS > mean(EPS)×0.25`. Excludes the 2020 near-zero/negative EPS outlier (`−5268.6`).
- **Unit** x.
- **As-of** Year-end prices.
- **Hist** **YES**.
- **Proj** no.
- **Params** Outlier guard `0.25 × AVERAGE(EPS)`.
- **AUTO** `6.382944640598736` (`6.38x`); verified `6.383041430459` ✅ (delta = rounding at the filter boundary).
- **Valid** ✅ verified.
- **Gap** **B**.
- **Impl** The `0.25×mean` filter is a **hard-coded outlier heuristic**, not a statistical test. Reproduce exactly and expose the threshold as a parameter. Verified PER series: `2020:−5268.63  2021:9.09  2022:5.31  2023:6.17  2024:5.45  2025:5.88`.

### 5.25 PBV Historical Average

- **Ref** two variants:
  ```text
  B37 (all history) = AVERAGE(FILTER(IFERROR(Range_Stock_Price/Range_BVPS,""), (Range_Stock_Price>0)*(Range_BVPS>0)))
  B38 (5Y window)   = AVERAGE(INDEX(PBV_Valid,1,SEQUENCE(1,MIN(Years_Compare, COLUMNS(PBV_Valid)))))
  ```
- **Means** Average historical PBV, used as the fair multiple.
- **Web** none (mock `"PBV Avg (Historical)": "0,67x"`).
- **Source** `prices_daily` + `financial_facts`.
- **Kind** **Derived**.
- **Transform** element-wise `price/BVPS` filtered `price>0 and BVPS>0`; `B38` takes the **first N = Years_Compare (5)** entries (newest-first).
- **Unit** x.
- **As-of** Year-end prices.
- **Hist** **YES**.
- **Proj** no.
- **Params** `Years_Compare` = 5 for the `B38` window.
- **AUTO** `B37 = 0.6717608090692812` (Excel `0.67x`); verified `0.671741630040` ✅. `B38 = 0.7107513889852919` (Excel `0.71x`); verified last-5 average `0.710728414889` ✅.
- **Valid** ✅ verified.
- **Gap** **B**.
- **Impl** `B37` (all years) and `B38` (newest 5) are **different metrics**, both displayed. Mean-Reversion IV (§5.28) uses `B37`; the classifier uses `B38`. Do not collapse them. Verified PBV series: `2020:0.4768  2021:0.4694  2022:0.5396  2023:0.7823  2024:0.9981  2025:0.7643`.

### 5.26 PBV Percentile

- **Ref** `MetricsClassification!B39`:
  ```text
  LET(Valid, (Range_Stock_Price>0)*(Range_BVPS>0),
      PBV_Hist, FILTER(IFERROR(Range_Stock_Price/Range_BVPS,""), Valid),
      CurrentPBV, Metric_PBV_Fwd,
      IF(CurrentPBV<=MIN(PBV_Hist), 0,
        IF(CurrentPBV>=MAX(PBV_Hist), 1,
          PERCENTRANK.INC(PBV_Hist, CurrentPBV))))
  ```
- **Means** Where the current PBV sits within its own history.
- **Web** none.
- **Source** `prices_daily` + `financial_facts`.
- **Kind** **Derived**.
- **Transform** `PERCENTRANK.INC` (inclusive), clamped to `[0,1]`.
- **Unit** ratio.
- **As-of** Current PBV versus historical series.
- **Hist** **YES**.
- **Proj** **YES** — the "current" PBV is `Metric_PBV_Fwd` (projected).
- **Params** none.
- **AUTO** `0.506` (Excel `50.60%`).
- **Valid** ✅ reproduced from workbook logic.
- **Gap** **B** / **C** (projected current value).
- **Impl** `PERCENTRANK.INC` semantics differ from SQL `PERCENT_RANK()` and `CUME_DIST`. Excel's inclusive rank interpolates between `(count<x)/(n−1)`. Implement Excel-compatible interpolation explicitly; a naive SQL percentile will not match. This feeds the **Asset Play** classifier (`PBV_Pct < 0.2`).


### 5.27 Peter Lynch Algo IV

- **Ref** `ValuationCurrent!B25` (the main-rule selector), reading `B4`–`B8`:
  ```text
  LET(Type, Stock_Type, Per_Val_Bottom, B4, Per_Val_Top, B5, Liquidation_Val, B6,
      Asset_Val, B7, PBV_Val, B8,
      Growth_Now, Metric_Rev_Growth_Actual, Growth_Hist, Metric_Rev_CAGR_Long,
      Momentum, Metric_Rev_Momentum,
      IFS(Type="TURN AROUND", Liquidation_Val,
          Type="ASSET PLAY",  Asset_Val,
          Type="CYCLICAL",    PBV_Val,
          AND(Growth_Now>Growth_Hist, Momentum="Slowing ⚠️"),      AVERAGE(Per_Val_Bottom, Per_Val_Top),
          AND(Growth_Now>Growth_Hist, Momentum="Accelerating 🚀"), Per_Val_Top,
          Growth_Now<Growth_Hist, Per_Val_Bottom,
          TRUE, AVERAGE(Per_Val_Bottom, Per_Val_Top)))
  ```
- **Component formulas** (`ValuationCurrent`):
  - `B4` PER Fair (Bottom) = `Target_PER × EPS_fwd`, where `Target_PER` = `IFS(CYCLICAL/ASSET PLAY/TURN AROUND → 0; STALWART+Financial → 25; SLOW GROWER → 12; STALWART → 16; FAST GROWER → growth×100×1.2; TRUE → 0)`
  - `B5` PER Fair (Top) = same, `×0.8`
  - `B6` Liquidation Value = `((Metric_Assets_Current − Metric_Liabilities_Total) / Proj_Shares) × 1000` → AUTO `896.9148290994541`
  - `B7` Asset Play Target (PBV) = `BVPS_fwd × Target_PBV`, `Target_PBV` = `IFS(Conservative→0.4, Moderate→0.5, Aggressive→0.7)` → AUTO `1783.8523420280746`
  - `B8` Cyclical Target (PBV) = `BVPS_fwd × Target_PBV` with `0.8/1.0/1.2` → AUTO `3567.7046840561493`
- **Means** The workbook's **main rule**: an adaptive intrinsic value that switches methodology by stock type.
- **Web** partial — `getMainValuationMethod(stockType)` only *selects a label*; it computes no IV.
- **Source** `financial_facts` + `prices_daily` + projection.
- **Fields** `EPS`, `TOTAL_EQUITY`, `OUTSTANDING_SHARES`, `CURRENT_ASSETS`/`TOTAL_CURRENT_ASSET`, `TOTAL_LIABILITIES`, `REVENUE`; plus `Proj_Shares`, `Proj_Equity`.
- **Kind** **Derived**.
- **Transform** branch on stock type; for `CYCLICAL` (AUTO) it reduces to `BVPS_fwd × 1.0`.
- **Unit** IDR per share.
- **As-of** Current.
- **Hist** **YES** (growth history + momentum for non-cyclical branches).
- **Proj** **YES** (`BVPS_fwd`, `EPS_fwd`, `Proj_Shares`).
- **Params** `Target_PER` table, `Target_PBV` by mode, type→mode map — all **hard-coded in the formula**, not in `Reference`.
- **AUTO** `3567.7046840561493` (Excel `Rp3,568`). Because `Stock_Type = CYCLICAL`, it equals `B8 = BVPS_fwd × 1.0` ✅
- **Valid** ✅ reproduced exactly.
- **Gap** **B** (structure) / **C** (projection inputs).
- **Impl** `Target_PER` / `Target_PBV` / the type→mode map live **inside** the formula with **no `Reference` table**. They must be lifted into a versioned parameter spec, otherwise the methodology cannot be versioned or reviewed. This is a prerequisite for `methodology_versions.parameter_spec`.

### 5.28 Type & Sector Weighted IV

- **Ref** `ValuationCurrent!B26`:
  ```text
  LET(PE_Fair_Proj,  Metric_EPS_Fwd  × Metric_PE_Avg_Long,
      PBV_Fair_Proj, Metric_BVPS_Fwd × Metric_PBV_Avg_Long,
      (PE_Fair_Proj×Param_W_PE + PBV_Fair_Proj×Param_W_PBV) / (Param_W_PE + Param_W_PBV))
  ```
  with `B21` / `B22`:
  ```text
  Param_W_PE  = (XLOOKUP(Company_Sector, Ref_Sec_List, Ref_Sec_W_PE)  + XLOOKUP(Stock_Type, Ref_Type_List, Ref_Type_W_PE))  / 2
  Param_W_PBV = (XLOOKUP(Company_Sector, Ref_Sec_List, Ref_Sec_W_PBV) + XLOOKUP(Stock_Type, Ref_Type_List, Ref_Type_W_PBV)) / 2
  ```
- **Means** Blended fair value from PER and PBV components, weighted by **sector and stock type**.
- **Web** partial — `getMainValuationMethod` returns the label for stalwart/fast-grower; no computation.
- **Source** `financial_facts` + projection + **`Reference` weight tables**.
- **Fields** `EPS`, `TOTAL_EQUITY`, `OUTSTANDING_SHARES`; sector via `instrument_sector_classifications` / `sectors`.
- **Kind** **Derived**.
- **Transform** two `XLOOKUP`s per weight (sector + type), averaged, then a weighted average of two fair values.
- **Unit** IDR per share.
- **As-of** Current.
- **Hist** **YES** (`PE_Avg_Long`, `PBV_Avg_Long`).
- **Proj** **YES** (`EPS_fwd`, `BVPS_fwd`).
- **Params** **`Reference!B5:C16`** sector weights and **`Reference!B22:C26`** type weights — full tables in §13.
- **AUTO** `Param_W_PE = 1.5`, `Param_W_PBV = 5.5`, IV = `2536.6003665489575` (Excel `Rp2,537`). Verified `(3049.773×1.5 + 2396.644×5.5)/7 = 2536.600` ✅
- **Valid** ✅ reproduced exactly.
- **Gap** **B** (formula) / **C** (weight tables + projection).
- **Impl** Sector/type weights must become **versioned reference data** (`methodology_versions.parameter_spec`), not code constants. AUTO: sector `Consumer Cyclicals` = `W_PE 3, W_PBV 1`; type `CYCLICAL` = `W_PE 0, W_PBV 10` → averages `1.5` / `5.5` ✅.
  `XLOOKUP` returns `#N/A` for an unknown sector/type, which the workbook catches as `"UNCLASSIFIED"`. Phase 4 must **fail closed**, never silently use `0`.


### 5.29 Mean Reversion PBV IV

- **Ref** `ValuationCurrent!B27` — a **quarterly** PBV series over `Years_Compare` years:
  ```text
  BaseYear = SUMMARY!E4 (2025),  Qtr = RIGHT(SUMMARY!E5,1) = 2,  TargetYear = BaseYear+1 = 2026
  NYears = Years_Compare = 5
  BaseIndex  = 2026*4 + 2 = 8106
  StartIndex = BaseIndex − (5*4) + 1 = 8087
  Keep = Ticker match
         AND (Year*4 + Quarter) BETWEEN StartIndex AND BaseIndex
         AND [Data Available Date] <> "" AND [Shares (Juta)] > 0 AND [Stock Price (Rp)] > 0
  PBV        = Price / ((Equity / Shares) * 1000)
  Valid_PBV  = FILTER(PBV, PBV > 0)
  IF(COUNT(Valid_PBV) < 3, 0,
     MAX((AVERAGE(Valid_PBV) − STDEV.P(Valid_PBV)) * Metric_BVPS_Fwd, 0))
  ```
- **Means** "Asset floor": the mean quarterly PBV **minus one population standard deviation**, applied to forward BVPS.
- **Web** none.
- **Source** `financial_facts` (QUARTER) + `prices_daily` + projection.
- **Fields** `TOTAL_EQUITY`, **quarterly `OUTSTANDING_SHARES`**, `close_price` (quarter-end PIT).
- **Kind** **Derived**.
- **Transform** 20-quarter window (5 years × 4), quarterly PBV, `AVERAGE − STDEV.P`, floored at `0`.
- **Unit** IDR per share.
- **As-of** Quarter-end prices across the window.
- **Hist** **YES** — a **20-quarter** series.
- **Proj** **YES** (`Metric_BVPS_Fwd` as the multiplier).
- **Params** `Years_Compare = 5`; minimum `3` valid quarters; `STDEV.P`.
- **AUTO** `1740.2732423202715` (Excel `Rp1,740`).
- **Valid** ✅ **reproduced and independently verified:**
  - Using **annual** shares for all quarters: `PBV_avg = 0.64832444`, `STDEV.P = 0.16058370`, IV = `1740.1149`.
  - Using **period-correct** shares (2021 `4.813.763.780`, 2022 `4.823.909.091`, else `4.819.733.000`): `PBV_avg = 0.64835233`, IV = `1740.2732` — **matches Excel to 4 d.p.** ✅
- **Gap** **B** / **C** (`BVPS_fwd`) / **D** (quarterly shares — see below).
- **Impl** **Critical dependency:** the exact match requires **per-quarter `Shares (Juta)`**, which Excel has in `Stock_Database_Quarter!N` but which is **absent from canonical PostgreSQL** for quarterly periods (`OUTSTANDING_SHARES` exists only for 7 annual rows). Using the nearest annual share count is a **close approximation** (`1740.11` vs `1740.27`, ≈0.01% error) but **not exact**. Resolving this needs either (a) a quarterly-shares ingestion path, or (b) a documented, accepted approximation. This is the sharpest single data gap for valuation parity — see §8 `G-SHARES-Q`.
  Also note the window is **5 years × 4 = 20 quarters**, and the workbook filters `Data Available Date <> ""` and `Price > 0`, which can shrink the effective window.

### 5.30 DDM IV (Dividend Discount Model)

- **Ref** `ValuationCurrent!B28`:
  ```text
  LET(AdjDiv, Proj_DPS,
      G_Long, Metric_Rev_CAGR_Long,
      G_Sustain, MIN(0.04, MAX(0, G_Long)),
      WACC, Param_RiskFreeRate + 0.06,
      IF(WACC > G_Sustain, (AdjDiv * (1 + G_Sustain)) / (WACC - G_Sustain), 0))
  ```
- **Means** Gordon-growth value of the forward dividend stream.
- **Web** none.
- **Source** `dividend_facts` + `financial_facts` + **external risk-free rate**.
- **Fields** `ANNUAL_TOTAL.amount_per_share` (projected via `Proj_DPS`), `REVENUE`.

### 5.31 Discounted Earnings IV

- **Ref** `ValuationCurrent!B29`:
  ```text
  LET(EPS, Metric_EPS_Fwd,
      GrowthRaw, IFERROR(Metric_Rev_CAGR_Long, 0.05),
      PE_Hist,   IFERROR(Metric_PE_Avg_Long, 15),
      RiskFree,  Param_RiskFreeRate,
      GrowthCapped, MIN(0.15, MAX(0, GrowthRaw)),
      PE_Capped,    MIN(PE_Hist, 25),
      Disc_Rate,    RiskFree + 0.04,
      FV_EPS,       EPS * (1 + GrowthCapped)^5,
      Future_Price, FV_EPS * PE_Capped,
      IV,           Future_Price / (1 + Disc_Rate)^5,
      MAX(IV, 0))
  ```
- **Means** Five-year forward earnings compounded at capped growth, re-rated at a capped PER, discounted back to present.
- **Web** none.
- **Source** `financial_facts` + `prices_daily` + **external risk-free rate**.
- **Fields** `EPS` (projected), `REVENUE` series.
- **Kind** **Derived**.
- **Transform** 5-year compounding; growth cap `15%`, PER cap `25`, discount `risk_free + 4%`, floor `0`.
- **Unit** IDR per share.
- **As-of** Current.
- **Hist** **YES** (`PE_Avg_Long`).
- **Proj** **YES** (`EPS_fwd`).
- **Params** Growth cap `0.15`, PER cap `25`, discount premium `+0.04`, horizon `5`, fallbacks `0.05` / `15`.
- **AUTO** `2304.8827926499084` (Excel `Rp2,305`). Verified: `477.8003 × 1.15^5 = 961.19`; `× 6.3830 = 6135.3`; `/ 1.1033^5 = 2304.88` ✅
- **Valid** ✅ arithmetic reproduced exactly.
- **Gap** **B** (formula) / **C** (risk-free rate, `EPS_fwd`, `PE_Avg_Long`).
- **Impl** The **fallback literals** (`0.05`, `15`) fire only when the underlying metric errors. Reproduce them for parity, but note they **mask missing data**. Phase 4 should emit an explicit `UNAVAILABLE` flag instead of silently substituting. This conflicts with the forward test suite's expectation that `DCF` is persisted as `UNAVAILABLE` — see §18.

### 5.32 IV Consensus

- **Ref** `SUMMARY!B19` and `B52`:
  ```text
  LET(Skip_Count,    COUNTIF(E13:E17, "⚪ N/A (Skip)"),
      Err_Count,     SUMPRODUCT((ISERROR(E13:E17))*1),
      Invalid_Count, Skip_Count + Err_Count,
      Valid_Count,   5 - Invalid_Count,
      Under_Count,   COUNTIF(E13:E17, "✅ UNDERVALUED"),
      IF(Valid_Count > 0, Under_Count & "/" & Valid_Count, "N/A"))
  ```
  Statuses come from `E13:E17` (per-method verdict text); the main method is chosen at `SUMMARY!B69`:
  `IF(B70<>"", B70, IF(OR(Stock_Type="stalwart", Stock_Type="fast grower"), "Weighted IV (Proj)", "Peter Lynch (Current)"))`
- **Means** How many of the five methods call the stock undervalued, out of the **valid** methods.
- **Web** **YES** — `classifyIntrinsicValuesAbovePrice` implements the count with `methodUndervaluedMinimum = 3`; `countMethodsAboveAnalysisPrice` formats `n/5`; `backtestConsensusDescription` documents it.
- **Source** derived from the five IV methods.
- **Kind** **Derived**.
- **Transform** count verdicts where `IV > price`; exclude `N/A`/errors from the denominator.
- **Unit** text `n/m`.
- **As-of** Current.
- **Hist** no.
- **Proj** **YES** (inherits).
- **Params** Main-verdict threshold `3/5` in the frontend.
- **AUTO** `2/5` (Excel `⚠️ MIXED SIGNAL — 2/5 metode valid | Main Rule Undervalued`); matches `SUMMARY!B52 = '2/5'` ✅
- **Valid** ✅ reproduced from workbook logic.

### 5.33 MoS (Margin of Safety)

- **Ref** per-method `SUMMARY!D13:D17` = `IFERROR((B13-Current_Price)/B13,"-")`; fundamental `SUMMARY!B75` = `IFERROR((B72-B71)/B72,"-")`; final `SUMMARY!B76` = `IFERROR((B74-B71)/B74,"-")`; `ValuationCurrent!B47` = `MoS_Peter_Lynch`
- **Means** Discount of the current price to intrinsic value. **Three variants exist:**
  1. `mos_method_i = (IV_i − price) / IV_i` — per method
  2. `mos_fundamental = (IV_baseline − price) / IV_baseline` — baseline `B72`, chosen by `B69`
  3. `mos_final = (quality_adj_target − price) / quality_adj_target` — `B74` = `B73 × quality factor`
- **Web** **YES** — `classifyMosMain` (`>= 0.30`), `classifyCurrentValuationMos` (divides a percent by 100 first). Mock carries `mosMain` / `mosPeter` / `mosWeight`.
- **Source** derived.
- **Kind** **Derived**.
- **Transform** `(IV − price)/IV`; guard `IV = 0`.
- **Unit** ratio.
- **As-of** Current price (PIT).
- **Hist** no.
- **Proj** **YES** (inherits).
- **Params** Entry threshold `0.35` (Excel `SUMMARY!C48`: "butuh 35%"); frontend classification threshold `0.30`.
- **AUTO** per-method `34.13% / 7.36% / −35.04% / −65.70% / −1.96%`; `mos_fundamental = 0.34131319486671524`; `mos_final = −0.17622643773800842` ✅
- **Valid** ✅ reproduced exactly.
- **Gap** **B**.
- **Impl** **Threshold inconsistency to resolve:** the workbook uses a **35%** entry threshold; the frontend's `backtestMethodology` uses **30%**. Both are live. Phase 4 must not silently pick one — see §18.
  Also note the divisor is `IV`, not price. `(IV − price)/IV` is the Excel MoS; `(IV − price)/price` is the "upside" variant shown in column `C`. Both are displayed and must stay distinct.

### 5.34 Liquidity Score

- **Ref** `SUMMARY!B56`:
  ```text
  MatchRow = (Ticker match) * (Year = BaseYear+1) * (Quarter = Qtr)
  AvgVol   = INDEX(FILTER([Avg Vol (3M)], MatchRow), 1)
  Price    = INDEX(FILTER([Stock Price (Rp)], MatchRow), 1)
  ValueTraded = AvgVol * Price
  IF(ValueTraded >= 200000000000, "Super Blue Chip (> 200 M)",
    IF(ValueTraded >=  50000000000, "Blue Chip (50 - 200 M)",
      IF(ValueTraded >= 10000000000, "Second Liner (10 - 50 M)",
        "Third Liner / Illiquid (< 10 M)")))
  ```
- **Means** Traded-value tier, used as a market-interest proxy.
- **Web** none (mock has no liquidity field).
- **Source** `prices_daily` (volume + close) + quarterly period selection.
- **Fields** `volume`, `close_price`, `trading_date`.
- **Kind** **Derived**.
- **Transform** 3-month average volume × as-of price, then threshold classification.
- **Unit** text tier.
- **As-of** **Critical** — the 3-month window ends at the target quarter's `Data Available Date`.
- **Hist** **YES** (3-month volume window).
- **Proj** no (but the target quarter is in the *projected* year).
- **Params** Thresholds `2e11`, `5e10`, `1e10` (**IDR**).
- **AUTO** `Third Liner / Illiquid (< 10 M)`. Verified: `AvgVol(3M) = 2449150.8474576273`, `Price = 2350`, `ValueTraded = 5.7555e9` < `1e10` → Third Liner ✅
- **Valid** ✅ **exactly reproduced**, including the 3-month window (§4.11.3).
- **Impl** Labels say `M` but thresholds are **billions** (the workbook's own unit confusion). Implement with the **numeric** thresholds; keep the labels unchanged.
  The forward test spec instead defines a **20-day** rolling turnover (`LIQUIDITY_DAILY_TURNOVER_20D`) — a **different** definition from Excel's 3-calendar-month average. Both cannot be "the" liquidity metric; see §18.

- **Gap** **B**.
- **Impl** **Denominator semantics matter:** Excel divides by **valid** methods (5 minus skipped/errored); the frontend divides by **total** (`values.length`). For AUTO both give `5`, but with a skipped method they diverge. Phase 4 must pick one and document it. Recommend Excel semantics (valid denominator) plus an explicit `valid_count` field.

- **Kind** **Derived**.
- **Transform** `DPS_fwd × (1 + g_sustain) / (WACC − g_sustain)`, `g_sustain` capped at `4%` and floored at `0`, `WACC = risk_free + 6%`.
- **Unit** IDR per share.
- **As-of** Current.
- **Hist** **YES** (revenue CAGR as the growth input).
- **Proj** **YES** (`Proj_DPS`).

### 5.35 Total Health Score

- **Ref** `FinancialHealth!B26`:
  ```text
  LET(Sector, Company_Sector, Type, Stock_Type,
      IsBank,  ISNUMBER(SEARCH("Financials", Sector)),
      IsProp,  ISNUMBER(SEARCH("Properties", Sector)),
      Limit_DER, IFS(IsBank, 15, IsProp, 2, TRUE,
                     IFERROR(XLOOKUP(Type, Ref_Type_List_Health, Ref_Type_MaxDER), 1)),
      Score_DER, IF(ISNUMBER(B8), IF(OR(AND(IsBank, B8<=Limit_DER), B8<=Limit_DER), 20, 0), 0),
      Limit_CR,  IFERROR(XLOOKUP(Type, Ref_Type_List_Health, Ref_Type_MinCR), 1),
      Score_CR,  IF(ISNUMBER(B9), IF(B9 >= Limit_CR, 20, 0), 0),
      Score_ICR, IF(OR(IsBank, Metric_Interest_Exp_Current=0), 20,
                    IF(ISNUMBER(B10), IF(B10 >= IFERROR(XLOOKUP(Type, Ref_Type_List_Health, Ref_Type_MinICR), 3), 20, 0), 0)),
      Score_OCF, IF(ISNUMBER(B11), IFS(B11>0, 20, IsBank, 10, TRUE, 0), 0),
      Penalty_Qual, LET(OCF_Ratio, IF(Metric_NetIncome_Current=0, 1,
                                      Metric_OCF_Current/Metric_NetIncome_Current),
                        IsCyclical, OR(Type="CYCLICAL", Type="ASSET PLAY",
                                       Sector="Energy", Sector="Basic Materials"),
                        Threshold, IF(IsCyclical, 0.6, 0.8),
                        IF(OCF_Ratio < Threshold, IF(OCF_Ratio < 0.4, -40, -20), 0)),
      Score_Safety, IF(B23="OK", 20, IF(B23="WARNING", 10, 0)),
      MAX(0, Score_DER + Score_CR + Score_ICR + Score_OCF + Score_Safety + Penalty_Qual))
  ```
- **Means** Composite 0–100 financial-health score: five 20-point components plus a penalty.
- **Web** **YES (partial)** — `classifyFinancialMetric` / `classifyCashConversion` reproduce some sub-labels, but **no score is computed**.
- **Source** `financial_facts`.
- **Fields** `TOTAL_LIABILITIES`, `TOTAL_EQUITY`, `CURRENT_ASSETS`/`TOTAL_CURRENT_ASSET`, `CURRENT_LIABILITIES`, `EARNINGS`, `INTEREST_EXPENSE_NON_OPERATING`, `OPERATING_CASH_FLOW`, `REVENUE`.
- **Kind** **Derived**.
- **Transform** four threshold checks (20 pts each) + OCF sign check (20) + clearance check (20) + an OCF/NI penalty (0/−20/−40), floored at 0.
- **Unit** integer 0–100.
- **As-of** Latest period.
- **Hist** **YES** (asset-growth-gap and NWC-change inputs need 2 periods).
- **Proj** **YES** — `B8` (DER) uses `Proj_Equity`.
- **Params** DER/CR thresholds by type (§13); ICR threshold **defaults to 3**; cyclical OCF thresholds `0.6`/`0.8`; penalty band `0.4`; bank overrides (`DER 15`, ICR auto-20, OCF 10).
- **AUTO** `80` (`🟢 HEALTHY`). **Verified component-by-component:** DER `0.3286 > 0.3` (CYCLICAL limit) → `0`; CR `2.205 ≥ 2.0` → `20`; ICR `49.706 ≥ 3` → `20`; OCF `1944.258 > 0` → `20`; Safety `"OK"` → `20`; Penalty `OCF/NI = 0.8817 ≥ 0.6` → `0`. **Total = 0+20+20+20+20+0 = 80** ✅
- **Valid** ✅ **fully reproduced component-by-component.**
- **Gap** **B** / **C** (projected equity for DER).
- **Impl** The DER component is the only reason AUTO does not score 100, and it hinges on **projected** equity. Reproducing the health score therefore **requires the projection engine**, even though four of six components are pure actuals. Also note `Max ICR` is missing, so the ICR threshold silently becomes `3` — document, don't fix.

### 5.36 Clearance / Risk Rating (supporting)

- **Ref** `FinancialHealth!B23` (clearance) and `B27` (rating):
  ```text
  B23 = IFS(AND(B18="Weak", Metric_OCF_Current<0), "FAIL",
            OR(B16>0.05, B17>0.1, B18="Weak", B14<-0.1, B15>0.05), "WARNING",
            TRUE, "OK")
  B27 = IF(B23="FAIL","☠️ TOXIC", IF(B26>=85,"💎 PERFECT", IF(B26>=70,"🟢 HEALTHY",
        IF(B26>=50,"🟡 MODERATE","🔴 HIGH RISK"))))
  ```
- **Means** Forensic gate plus a rating band.
- **Web** none.
- **Source** `financial_facts`.
- **Fields** `OPERATING_CASH_FLOW`, `EARNINGS`, `TOTAL_DEBT`, `CURRENT_ASSETS`, `CURRENT_LIABILITIES`, `REVENUE`, `GROSS_PROFIT`.
- **Kind** **Derived**.
- **Transform** five forensic sub-checks: `B16` debt-vs-profit growth gap, `B17` margin spike, `B18` OCF quality (`"Strong"` if `OCF >= 0.8×NI`), `B14` asset growth gap, `B15` NWC intensity change.
- **Unit** text.
- **As-of** Latest.
- **Hist** **YES** (growth series).
- **Proj** no.
- **Params** `>0.05`, `>0.1`, `<−0.1`, OCF/NI `0.8`; rating bands `85 / 70 / 50`.
- **AUTO** `B23 = "OK"`, `B27 = "🟢 HEALTHY"`, `B26 = 80`.

### 5.37 Business Quality

- **Ref** `SUMMARY!B57`, `B58`, `B59`:
  ```text
  B57 Brand Power    = IFS(AND(Metric_NPM_Avg>0.15, DataInput!B14>10000), 2,
                           AND(Metric_NPM_Avg>0.08, DataInput!B14>2000),  1,
                           Metric_ROE_Avg>0.15, 2, TRUE, 0)
  B58 GCG & Dividend = IF(Metric_Yield_Hist>0.03, 2, IF(Metric_Yield_Hist>0, 1, 0))
  B59 TOTAL QUALITY  = B57 + B58 + IFERROR(IFS(B56="Super Blue Chip (>200 M)", 2,
                                               B56="Blue Chip (50 - 200 M)", 1.5,
                                               B56="Second Liner (10 - 50 M)", 1, TRUE, 0), 0)
  ```
  Multiplier (`C59` / `B74`): `IFS(B59>=5 → 1.2; B59>=3 → 1.0; TRUE → 0.7)`
- **Means** Composite moat/quality score (0–5.5) and the multiplier it applies to the market-adjusted target.
- **Web** none.
- **Source** `financial_facts` + `prices_daily`.
- **Fields** `EARNINGS`, `REVENUE` (NPM), `TOTAL_EQUITY` (ROE), `close_price`, `volume`.
- **Kind** **Derived**.
- **Transform** three additive components, each a small `IFS` ladder.
- **Unit** points 0–5.5; multiplier `0.7 / 1.0 / 1.2`.
- **As-of** Latest + current market cap.
- **Hist** **YES** (`NPM_Avg`, `ROE_Avg`, `Yield_Hist`).
- **Proj** no.
- **Params** NPM `0.15`/`0.08`, market cap `10000`/`2000` (billion IDR), ROE `0.15`, yield `0.03`; liquidity tiers; multiplier bands `5`/`3`.
- **AUTO** `B57 = 0`, `B58 = 2`, `B59 = 2` → multiplier `0.7` (`⚠️ LOW QUALITY (0.7x)`) ✅
- **Valid** ✅ reproduced exactly: `NPM_Avg = 0.06796 < 0.08` → Brand `0`; `Yield_Hist = 0.05181 > 0.03` → GCG `2`; liquidity tier = Third Liner → `0`; total `2` → `0.7×`.
- **Gap** **B**.
- **Impl** **Correction to Phase 3:** §11C of `EXCEL_POSTGRES_VALIDATION.md` classifies "Brand Power / GCG / Moat scores" as **"manual analyst input — manual only"**. Verified from the workbook formulas, **`B57` and `B58` are fully derived** from canonical data (NPM, market cap, ROE, historical yield). Only the `B56` liquidity-tier *label text* is presentation. **Phase 4 can compute Business Quality without manual input.** This removes one previously assumed blocker.
  The `0.7` multiplier propagates into `SUMMARY!B74` (quality-adjusted target) and thus into `MoS (vs Final)` — a 0.1 error here moves the displayed target by ~14%.

### 5.38 Market Mood

- **Ref** `SUMMARY!B66` (mood) from manual inputs `B63`, `B64`, `B65`:
  ```text
  Score = (IF(B63="Bullish",1,0) + IF(B64="Inflow",1,0) + IF(B65="BI Rate Turun/Tetap",1,0))
  IFS(Score<=1 → "BEARISH (Winter)"; Score=2 → "NEUTRAL (Spring)"; Score=3 → "BULLISH (Summer)")
  ```
  Inputs are **literal typed text**: `B63 = "Bearish"`, `B64 = "Outflow"`, `B65 = "BI Rate Turun/Tetap"`.
- **Means** Market-wide regime, used to scale intrinsic value into a market-adjusted target.
- **Web** none.
- **Source** **NONE** — no canonical table.
- **Fields** — (missing).
- **Kind** **Derived from manual inputs**.
- **Transform** three boolean votes summed, then a 3-band `IFS`.
- **Unit** text.
- **As-of** Current.
- **Hist** no.
- **Proj** no.
- **Params** Three vote values; bands `1 / 2 / 3`.
- **AUTO** `"BEARISH (Winter)"` (Score = 0).
- **Valid** ✅ logic reproduced; **inputs are manual**.
- **Gap** **C** — requires data absent from Sectors and canonical PostgreSQL:
  1. **IHSG vs MA200** — market index series with a 200-day moving average.
  2. **Foreign Flow** — market-wide foreign net buy/sell.
  3. **BI Rate / Inflation** — Bank Indonesia policy rate and CPI.
- **Impl** **Genuinely non-replicable in Phase 4** from the current pipeline. Options: (a) manual input via an admin surface, (b) a separate macro ingestion source, or (c) exclude Market Mood from the first calculation release and mark dependent targets `UNAVAILABLE`. **Recommend (c) initially** — the only option that does not fabricate data. Note `B73`/`B74`/`B76` all depend on mood, so excluding it removes three displayed values; that is an explicit product decision.

- **Valid** ✅ reproduced.

### 5.39 Strategic Target and Ideal Price

- **Ref** `SUMMARY!B71`–`B74`, `B80`:
  ```text
  B69 IV Method     = IF(B70<>"", B70, IF(OR(Stock_Type="stalwart", Stock_Type="fast grower"),
                                          "Weighted IV (Proj)", "Peter Lynch (Current)"))
  B71 Current Price = Metric_Price_Current
  B72 IV Baseline   = IF(B69="Peter Lynch (Current)", B13, B14)
  B73 Market-Adj    = IFS(B66="BEARISH (Winter)", B72*0.8,
                          B66="NEUTRAL (Spring)", B72*0.9,
                          B66="BULLISH (Summer)", B72*1, TRUE, B72*0.9)
  B74 Quality-Adj   = B73 * IFS(B59>=5, 1.2, B59>=3, 1, TRUE, 0.7)
  B75 MoS (vs Fund) = IFERROR((B72-B71)/B72, "-")
  B76 MoS (vs Final)= IFERROR((B74-B71)/B74, "-")
  B80 Ideal Price   = B72 * 0.7
  ```
- **Means** The action panel: a baseline IV, a mood-adjusted price, a quality-adjusted final target, and the "ideal price" at a 30% discount.
- **Web** **partial** — `getMainValuationMethod` mirrors only `B69`'s selection rule.
- **Source** derived.
- **Kind** **Derived**.
- **Transform** two successive multiplicative adjustments plus a fixed 30% discount.
- **Unit** IDR per share.
- **As-of** Current.
- **Hist** **YES** (via `B59` quality inputs).
- **Proj** **YES** (via IV).
- **Params** Mood multipliers `0.8 / 0.9 / 1.0`; quality multipliers `1.2 / 1.0 / 0.7`; ideal-price discount `0.7`.
- **AUTO** `B71 = 2350`, `B72 = 3567.7046840561493`, `B73 = 2854.1637472449197` (`×0.8`, Bearish), `B74 = 1997.9146230714437` (`×0.7`), `B75 = 0.34131319486671524`, `B76 = −0.17622643773800842`, `B80 = 2497.3932788393045` (Excel `Rp2,497`) ✅
- **Valid** ✅ **fully reproduced**, including both adjustments.
- **Gap** **B** (arithmetic) / **C** (Market Mood input for `B73`/`B74`).
- **Impl** `Ideal Price` (`B80`) depends only on `B72` and the fixed `0.7` — so **Ideal Price is replicable without Market Mood**. `Market-Adj Price` and `Quality-Adj Target` are **not**. This yields a clean partial-release boundary: ship `Ideal Price`, `MoS (vs Fundamental)`, and per-method MoS; defer the mood-dependent pair.

### 5.40 Supporting metric — Revenue Momentum

- **Ref** `MetricsClassification!B9` = `IF(B8 > B7, "Accelerating 🚀", "Slowing ⚠️")`
- **Means** Whether the short-window CAGR exceeds the long-window CAGR.
- **Source** derived (CAGR pair).
- **Kind** **Derived**. **Unit** text. **Hist** **YES**. **Proj** no. **Params** none.
- **AUTO** `"Accelerating 🚀"` (`0.10896 > 0.04321`) ✅
- **Gap** **B**. **Impl** Drives the Peter-Lynch branch selection (§5.27) and the Fast-Grower classifier. Exact emoji/whitespace must be preserved if text comparison is used.

### 5.41 Supporting metric — EPS CAGR (Historical / 5Y)

- **Ref** `MetricsClassification!B13` (full) and `B14` (window):
  ```text
  B13 = LET(StartVal, INDEX(Range_EPS, Years_Avail), EndVal, INDEX(Range_EPS,1),
            Period, Years_Avail-1,
            IF(StartVal < 0, ((EndVal-StartVal)/ABS(StartVal))/Period,
               IFERROR(RRI(Period, StartVal, EndVal), 0)))
  B14 = same with INDEX(Range_EPS, Years_Compare+1) and Period = Years_Compare
  ```
- **Means** EPS compound growth, with a **negative-base fallback** to a normalised linear average.
- **Source** `financial_facts.EPS`.
- **Kind** **Derived**. **Unit** ratio. **Hist** **YES**. **Proj** no.
- **Params** Negative-base branch: `(End−Start)/ABS(Start)/Period` — a **linear** rate, not compounding.
- **AUTO** `B13 = 0.19967136094934035` (`19.97%`), `B14 = 432.55725490196073` (`43255.73%`).
- **Gap** **B**. **Impl** The **negative-base branch is not `RRI`**. AUTO's `B13` uses it because 2020 EPS is negative (`−0.2116`). Reproducing this exactly is essential for PEG (§5.21). The `B14` value is an artifact of a near-zero base, displayed as `43255.73%`; document, don't fix.

### 5.42 Supporting metric — EPS Momentum

- **Ref** `MetricsClassification!B15` = `IF(B14 > B13, "Accelerating 🚀", "Slowing ⚠️")`
- **Source** derived. **Kind** **Derived**. **AUTO** `"Accelerating 🚀"`. **Gap** **B**.

### 5.43 Supporting metric — Current Asset Growth (YoY)

- **Ref** `MetricsClassification!B17` = `IFERROR(INDEX(Range_Curr_Assets,1)/INDEX(Range_Curr_Assets,2)-1,"")`
- **Source** `financial_facts.CURRENT_ASSETS`. **Kind** **Derived**.
- **AUTO** `0.12272273788915` (`12.27%`) ✅ **Gap** **B**.

### 5.44 Supporting metric — Latest balance/flow accessors

- **Ref** `MetricsClassification!B55`–`B60` = `INDEX(Range_X, 1)` for current assets, current liabilities, total liabilities, interest expense, OCF, net income.
- **Means** "Latest period" accessors. `INDEX(...,1)` = **newest** because `DataInput` columns run newest-first.
- **AUTO** `B55 = 9973.987`, `B56 = 4523.347`, `B57 = 5651.097`, `B58 = 43.486`, `B59 = 1944.258`, `B60 = 2205.022` ✅ all match canonical 2025 values.
- **Gap** **A**. **Impl** These anchor the entire health/quality block; a wrong "latest" selection corrupts everything downstream.

- **Gap** **B**.
- **Impl** `B16`/`B17` formulas were not fully extracted (only their `D`-column diagnostic text). They must be re-read from the workbook before implementation — flagged in §18.

- **Params** **`Param_RiskFreeRate = 0.0633`** (hard-coded at `DataInput!B11`), equity risk premium `+0.06`, growth cap `0.04`.
- **AUTO** `1418.1931011077158` (Excel `Rp1,418`). Verified: `WACC = 0.0633+0.06 = 0.1233`; `g = MIN(0.04, MAX(0, 0.0432)) = 0.04`; `113.5918 × 1.04 / (0.1233 − 0.04) = 1418.19` ✅
- **Valid** ✅ arithmetic reproduced exactly.
- **Gap** **B** (formula) / **C** (**risk-free rate is NOT in the database**) / **C** (`Proj_DPS`).
- **Impl** Two independent `C` blockers: (1) `Param_RiskFreeRate = 0.0633` is a **hard-coded literal** with no canonical source; (2) `Proj_DPS` depends on the projection engine. Until (1) is sourced, DDM cannot be reproduced from PostgreSQL alone. The `+0.06` ERP and `0.04` cap are also un-sourced constants.


### 5.45 Supporting metric — Quality & Forensic block

- **Ref** `MetricsClassification`:
  - `B43` ROE Avg = `AVERAGE(Range_Net_Income/Range_Equity)` → AUTO `0.09377830468099553` (`9.38%`) ✅
  - `B44` ROE (Proj) = `Proj_Net_Income/Proj_Equity` → AUTO `0.1339237320899609` (`13.39%`) ✅
  - `B45` ROE Trend = `IF(Metric_ROE_Current > Metric_ROE_Avg, "Improving 🚀", "Declining ⚠️")` → AUTO `"Improving 🚀"`
  - `B46` GPM Range = `(MAX(GP/Rev) − MIN(GP/Rev))×100` → AUTO `87.7192490355679` (ppt) ✅
  - `B47` NPM Avg = `AVERAGE(NI/Rev)` → AUTO `0.06796213330933173` (`6.80%`) ✅
  - `B49` NPM vs Hist = `NI_latest/Rev_latest − AVERAGE(NI/Rev)` → AUTO `0.04280528686633309` ✅
  - `B50` ROE Stability = `STDEV.P(NI/Equity)` → AUTO `0.05598884432742073` (`5.60%`) ✅
  - `B51` Equity Growth Consistency = `IF(MIN(Equity)<0,"Negative Equity ☠️", IF(RRI(...,Equity)>0.05,"Consistent 💎","Stagnant/Erosion 📉"))` → AUTO `"Consistent 💎"`
  - `B66` Asset Growth Gap (5Y) = `Rev_CAGR_Short − RRI(5, CurrAssets[5], CurrAssets[1])` → AUTO `−0.03221225778395165`
  - `B69` CF Status = `IF(Proj_OCF < 0.5×Proj_Net_Income, "Warning: Low Cash", "OK")` → AUTO `"OK"`
- **Source** `financial_facts`. **Kind** **Derived**. **Hist** **YES** for all averages/StdDev. **Proj** for `B44`, `B69`.
- **Gap** **B** (all except `B44`/`B69`, which are **C**).
- **Impl** `B46` GPM Range = `87.72 ppt` is an artifact of the 2019 blank-COGS row (2019 gross margin `100%`), inflating the range. **Documented, not fixed.** If Phase 4 excludes the 2019 artifact this metric will legitimately differ from Excel — a decision point (§18).

### 5.46 Supporting metric — Stock Type Classifier

- **Ref** `MetricsClassification!B80` (full `LET` block); output `B82` = `IF(B81<>"", B81, B80)`.
- **Means** Rule-based classification: `TURN AROUND / FAST GROWER / CYCLICAL / STALWART / SLOW GROWER / ASSET PLAY / UNCLASSIFIED`.
- **Rules** (exact, verified):
  ```text
  SlowGrower = RevLong <= 0.08  AND Payout > 0.2
  Stalwart   = (IsFinancial AND RevLong>0.05 AND ROEAvg>0.12)
               OR (NOT IsFinancial AND RevLong>0.1 AND RevLong<=0.2 AND RevCoV<0.35)
               OR (IsConsumerDefensive AND RevLong>=0.05 AND RevLong<=0.15 AND ROEAvg>0.12 AND RevCoV<0.35)
  FastGrower = (IsFinancial AND EPSLong>0.15)
               OR (NOT IsFinancial AND RevLong>0.2 AND (RevCoV<0.35 OR RevMomentum="Accelerating 🚀"))
  Cyclical   = ProjNI>0 AND IF(IsFinancial, FALSE, OR(IsCyclicalSector, RevCoV>0.35))
  AssetPlay  = PBV_Fwd < 0.8 AND PBV_Pct < 0.2
  TurnAround = ProjNI < 0
  Scores     = TurnAround 100, Fast 80, Cyclical 60, Stalwart 40, Slow 20, AssetPlay 10
  Winner     = IFS(Sector="Energy","CYCLICAL"; ScoreMax=100,"TURN AROUND"; =80,"FAST GROWER";
                   =60,"CYCLICAL"; =40,"STALWART"; =20,"SLOW GROWER"; =10,"ASSET PLAY";
                   TRUE,"UNCLASSIFIED")
  ```
  `IsCyclicalSector` = Energy, Basic Materials, Transportation & Logistic, Properties & Real Estate, Consumer Discretionary, Industrials, **or Consumer Cyclicals**.
  `IsConsumerDefensive` = Consumer Non-Cyclicals, Utilities, or Healthcare.
- **Web** **partial** — `getMainValuationMethod` consumes a `stockType` string but **does not classify**; mock hard-codes `"Cyclical"`.
- **Source** `financial_facts` + derived metrics.
- **Kind** **Derived**. **Unit** text enum. **As-of** Current.
- **Hist** **YES** (RevLong, RevCoV, EPSLong, ROEAvg, PBV_Pct).
- **Proj** **YES** (`ProjNI > 0` gate for Cyclical / TurnAround).
- **Params** Thresholds `0.08`, `0.2`, `0.05`, `0.12`, `0.1`, `0.2`, `0.35`, `0.15`, `0.8`, `0.2`; score ladder `100/80/60/40/20/10`.
- **AUTO** `"CYCLICAL"` (`B81` override blank → `B82 = B80`); confidence `0.7`.
- **Valid** ✅ **reproduced exactly**: `ProjNI = 2302.87 > 0`, `IsFinancial = FALSE`, `IsCyclicalSector = TRUE` (Consumer Cyclicals) → Cyclical score `60`. Other rules score lower: `SlowGrower` (`0.0432 ≤ 0.08` ✅ and `Payout 0.2728 > 0.2` ✅) → `20`; `FastGrower` needs `RevLong>0.2` ✗; `AssetPlay` needs `PBV 0.6587 < 0.8` ✅ **and** `PBV_Pct 0.506 < 0.2` ✗. Winner = `CYCLICAL` ✅
- **Gap** **B** / **C** (`ProjNI`).
- **Impl** **Two hard-coded overrides matter:** (1) `Company_Sector="Energy"` **always** forces `"CYCLICAL"`, short-circuiting all scoring; (2) the score ladder means `TURN AROUND` beats `FAST GROWER` regardless of magnitude. Both must be preserved.
  A **manual override** exists at `B81` (blank for AUTO); the final type is `B82`. Phase 4 must either support an override channel or explicitly record it as unsupported.
  **`AssetPlay` is nearly unreachable:** it needs `PBV < 0.8` **and** `PBV_Pct < 0.2` simultaneously, which for AUTO is contradictory (`PBV 0.66` but percentile `50.6%`). Note the percentile uses all-history while `PBV_Fwd` is projected — an internal workbook inconsistency.

### 5.47 Supporting metric — Confidence Level

- **Ref** `MetricsClassification!B83` (large `LET` block) → `Confidence_Level`, surfaced at `SUMMARY!B83`.
- **Means** A 0–1 confidence in the classification.
- **Source** derived.
- **AUTO** `0.7` (Excel `Confidence Level 70.0%`).
- **Valid** ✅ value captured. **Formula body only partially extracted** (truncated in the dump).
- **Gap** **D** — the full formula must be re-read from the workbook before implementation.
- **Impl** Listed as an open item in §18. Not on the critical path for valuation, but it is displayed.


### 5.48 Supporting metric — Quarterly YoY Thesis Validator

- **Ref** `DataInputProyeksi!B47`–`B52` (labels/values), surfaced at `SUMMARY!B22:E27`.
- **Means** Per-quarter YoY comparison: Revenue, Gross Margin, Net Income, OCF/NI, Interest Expense.
- **Rules** (verified from `B48`–`B52`): `offset = 3` quarters from the latest, then a same-quarter prior-year join:
  ```text
  urutan_kuartal = tahun_terbaru*4 + kuartal_terbaru − offset
  tahun_target   = INT((urutan_kuartal − 1)/4);   kuartal_target = MOD(urutan_kuartal − 1, 4) + 1
  Revenue YoY    = nilai_skrg/nilai_thunlalu − 1
  Gross Margin   = (pendapatan + hpp)/pendapatan
  OCF/NI         = arus_kas/laba_bersih
  Interest Exp   = ABS(beban_bunga)
  ```
- **Source** `financial_facts` (QUARTER).
- **Fields** `REVENUE`, `COST_OF_REVENUE`, `EARNINGS`, `OPERATING_CASH_FLOW`, `INTEREST_EXPENSE_NON_OPERATING`.
- **Kind** **Derived**.
- **Transform** same-quarter prior-year join over 4 consecutive quarters.
- **Unit** ratio / IDR.
- **As-of** Latest quarter.
- **Hist** **YES** (needs the prior-year quarter).
- **Proj** no.
- **Params** `offset = 3` (start 3 quarters back).
- **AUTO** `Revenue YoY: 5.07% / 3.93% / 7.40% / 19.34%`; `GM: 16.79% / 18.79% / 16.01% / 15.12%`; `NI YoY: 22.36% / 25.96% / 10.56% / 36.71%`; `OCF/NI: 0.529 / 0.831 / 0.735 / 0.573`; `Interest Exp: 10.887 / 9.784 / 9.056 / 9.224` ✅
- **Valid** ✅ reproduced from workbook logic.
- **Gap** **B**.
- **Impl** Requires a **same-quarter prior-year** join, which the forward test spec flags as `QUARTERLY_COMPARISON_MISSING` when the counterpart period is absent. `offset = 3` means 4 quarters are displayed.

### 5.49 Supporting metric — TTM Aggregation

- **Ref** **No Excel TTM column exists.** The template's `DataInput`/`DataInputProyeksi` carry annual and quarterly columns only; TTM appears solely as a **projection** (`F12`–`F25`) and in `dividend_facts.TTM`.
- **Means** Trailing-twelve-month flows (revenue, earnings, OCF, dividend).
- **Web** none (mock `"EPS (TTM)"` is actually projected EPS).
- **Source** `financial_facts` (QUARTER) + `dividend_facts.TTM`.
- **Kind** **Derived**.
- **Transform** sum of the latest 4 `STANDALONE` quarters.
- **Unit** IDR (flows) / IDR per share.
- **As-of** Latest quarter.
- **Hist** **YES** — needs 4 quarters.
- **Proj** no.
- **Params** none.
- **AUTO** Not directly displayed by Excel. The forward test spec defines `calculate_ttm_flows` and expects a `TTM_INCOMPLETE` flag when fewer than 4 quarters are present.
- **Valid** ⚠️ Not in the workbook; **required by the forward test spec**.
- **Gap** **B** — derivable from `financial_facts` (26 quarters available), but it is an **addition**, not a replication.
- **Impl** `dividend_facts.TTM = 229.0` exists but has **no `period_year` and no `event_date`**, so it cannot be tied to a window. The test spec's `DIVIDEND_EVENT_DATE_MISSING` flag will fire. Phase 4 should compute TTM flows from `financial_facts` and treat the provider `TTM` dividend row as a **separate, unverifiable** value.


---

## 6. Inputs Required for Each Calculation

### 6.1 Canonical input set (the "input vocabulary")

Every replicable metric reduces to this set. Anything outside it is a gap.

| Input | Table | Field / filter | AUTO availability |
|---|---|---|---|
| Revenue | `financial_facts` | `REVENUE` | 7 annual + 26 quarter ✅ |
| Cost of revenue | `financial_facts` | `COST_OF_REVENUE` | 7 annual + 26 quarter ✅ |
| Gross profit | `financial_facts` | `GROSS_PROFIT` | 7 annual + 26 quarter ✅ |
| Net income | `financial_facts` | `EARNINGS` | 7 annual + 26 quarter ✅ |
| Operating cash flow | `financial_facts` | `OPERATING_CASH_FLOW` | 7 annual + 26 quarter ✅ |
| Interest expense | `financial_facts` | `INTEREST_EXPENSE_NON_OPERATING` | 7 annual + 26 quarter ✅ |
| Current assets | `financial_facts` | `CURRENT_ASSETS` (A) / `TOTAL_CURRENT_ASSET` (Q) | 7 annual + 26 quarter ✅ |
| Current liabilities | `financial_facts` | `CURRENT_LIABILITIES` | 7 annual + 26 quarter ✅ |
| Total liabilities | `financial_facts` | `TOTAL_LIABILITIES` | 7 annual + 26 quarter ✅ |
| Total equity | `financial_facts` | `TOTAL_EQUITY` | 7 annual + 26 quarter ✅ |
| Shares outstanding | `financial_facts` | `OUTSTANDING_SHARES` | **7 annual only** ⚠️ |
| EPS | `financial_facts` | `EPS` | 6 annual ✅ |
| Close price | `prices_daily` | `close_price` | 1.619 rows ✅ |
| Volume | `prices_daily` | `volume` | 1.619 rows ✅ |
| Trading date | `prices_daily` | `trading_date` | 1.619 rows ✅ |
| DPS (annual) | `dividend_facts` | `ANNUAL_TOTAL.amount_per_share` | 7 rows (2020–2026) ✅ |
| Yield (provider) | `dividend_facts` | `YIELD.yield_ratio` | 7 rows ✅ |
| Payout (provider) | `dividend_facts` | `PAYOUT_RATIO.yield_ratio` | 1 row ✅ |
| Sector / subsector | `sectors`, `instrument_sector_classifications` | `sector_name`, `subsector_name` | 1 row ✅ |
| Ticker | `instruments` | `ticker` | 1 row ✅ |
| Period type / label / end | `financial_periods` | `period_type`, `period_label`, `period_end` | 33 rows ✅ |

### 6.2 Minimum input set per metric group

| Metric group | Minimum inputs |
|---|---|
| Profitability / margins | `REVENUE`, `COST_OF_REVENUE` or `GROSS_PROFIT`, `EARNINGS` |
| Per-share metrics | above + `OUTSTANDING_SHARES` |
| Multiples | per-share metrics + `close_price` (as-of) |
| Balance-sheet ratios | `TOTAL_EQUITY`, `TOTAL_LIABILITIES`, `CURRENT_ASSETS`/`TOTAL_CURRENT_ASSET`, `CURRENT_LIABILITIES` |
| Cash quality | `OPERATING_CASH_FLOW`, `EARNINGS` |
| Coverage | `INTEREST_EXPENSE_NON_OPERATING`, `EARNINGS` |
| Growth series | `REVENUE` (or `EPS`) ordered by `period_end` |
| Forensic | `REVENUE`, `CURRENT_ASSETS`/`TOTAL_CURRENT_ASSET`, `TOTAL_DEBT`, `OPERATING_CASH_FLOW`, `EARNINGS` |
| Dividend metrics | `ANNUAL_TOTAL.amount_per_share` + `close_price` + `EPS` |
| Liquidity tier | `volume` + `close_price` over a 3-month window |
| Valuation methods | all of the above + projection + `Reference` weights + risk-free rate |

### 6.3 Inputs that must be **added** to the pipeline

| Input | Needed by | Status |
|---|---|---|
| Quarterly shares outstanding | Mean-Reversion PBV IV, quarterly BVPS/PBV | **missing** (annual only) |
| Risk-free rate (10Y SBN) | DDM, Discounted Earnings | **missing** (hard-coded `0.0633`) |

---

## 7. Direct DB Fields vs Derived Fields

### 7.1 Stored and usable directly (Class A)

| Metric | Canonical field |
|---|---|
| Revenue | `financial_facts.REVENUE` |
| Cost of revenue | `financial_facts.COST_OF_REVENUE` |
| Gross profit | `financial_facts.GROSS_PROFIT` |
| Net income | `financial_facts.EARNINGS` |
| Operating cash flow | `financial_facts.OPERATING_CASH_FLOW` |
| EBITDA / EBIT | `financial_facts.EBITDA` / `.EBIT` (present, **unused by Excel**) |
| Total assets | `financial_facts.TOTAL_ASSETS` (present, **unused by Excel**) |
| Free cash flow / capex | `financial_facts.FREE_CASH_FLOW` / `.CAPITAL_EXPENDITURE` (present, **unused**) |
| Inventories | `financial_facts.INVENTORIES` (annual only) |
| Total equity / liabilities | `financial_facts.TOTAL_EQUITY` / `.TOTAL_LIABILITIES` |
| Current assets / liabilities | `financial_facts.CURRENT_ASSETS` / `.CURRENT_LIABILITIES` |
| Shares outstanding | `financial_facts.OUTSTANDING_SHARES` (annual) |
| EPS | `financial_facts.EPS` |
| Close price / volume / date | `prices_daily.close_price` / `.volume` / `.trading_date` |
| DPS / yield / payout | `dividend_facts` |
| Ticker / sector / subsector | `instruments.ticker`, `sectors.*` |
| Period metadata | `financial_periods.*` |

### 7.2 Must be derived (Class B)

Gross margin, NPM, ROE, BVPS, PER, PBV, DPR (template), Dividend Yield (template),
Market Cap, NWC, NWC/Revenue, NWC intensity change, DER (actual), Current Ratio, ICR,
Quick Ratio, Revenue/EPS CAGR, CoV, YoY growth, Asset Growth Gap, EPS annualized,
PEG, historical averages, percentile, TTM flows, liquidity tier, the five IV methods,
IV consensus, MoS, health score, business quality, stock-type classification,
strategic targets, Ideal Price, quarterly YoY thesis.

### 7.3 Cannot be derived from canonical data (Class C/D)

Risk-free rate; projections; sector/type weight tables; DER/CR/ICR thresholds;
Market Mood inputs; quarterly shares; `available_date`-based point-in-time;
backtest cases/outcomes; the full confidence-level formula.

### 7.4 Reverse gap — stored but unused

`TOTAL_ASSETS`, `EBITDA`, `EBIT`, `FREE_CASH_FLOW`, `CAPITAL_EXPENDITURE`,
`INVENTORIES`, `CASH_AND_EQUIVALENTS`, `NET_DEBT`, `LONG_TERM_DEBT`,
`SHORT_TERM_DEBT`, `RETAINED_EARNINGS`, `FIXED_ASSETS`, `PREPAID_ASSETS`,
`TOTAL_NON_CURRENT_ASSETS`, `TOTAL_NON_CURRENT_LIABILITIES`, `MINORITIES`,
`EARNINGS_BEFORE_TAX`, `TAX`, `OPERATING_PNL`, `OPERATING_EXPENSE`,
`NON_OPERATING_INCOME_OR_LOSS`, `NON_INTEREST_INCOME`, `CASH_ONLY`,

---

## 8. Missing / Non-Replicable Inputs

Each gap is classified **A / B / C / D** and given an identifier for traceability.

### 8.1 Class C — requires external, manual, parameter, or projection input

| ID | Missing item | Needed by | Where it must come from | Effort |
|---|---|---|---|---|
| `G-RFR` | Risk-free rate (`0.0633`, 10Y SBN) | DDM IV, Discounted Earnings IV | External macro source (BI / SBN market); **not** in Sectors or canonical | Medium |
| `G-PROJ` | Projection engine (`Proj_*`, 11 series) | DER template, EPS annualized, PEG, PBV percentile, all 5 IV methods, health score, targets | New methodology spec + `methodology_versions`; workbook logic documented in §9 | **High** |
| `G-WEIGHTS` | Sector weights `W_PE`/`W_PBV` (12 sectors) | Type & Sector Weighted IV | `Reference!B5:C16` → versioned parameter seed | Low |
| `G-TYPEW` | Type weights `W_PE`/`W_PBV` (6 types) | Type & Sector Weighted IV | `Reference!B22:C26` → versioned parameter seed | Low |
| `G-THRESH` | DER/CR thresholds by type | Health score | `Reference!B32:C37` → versioned parameter seed | Low |
| `G-ICR-THRESH` | `Min ICR` threshold column | Health score ICR component | **Column does not exist**; workbook silently defaults to `3` | Low (decision) |
| `G-MOOD` | IHSG vs MA200, foreign flow, BI rate/inflation | Market Mood, market-adjusted target, `MoS (vs Final)` | External market/macro source; **not** in Sectors | **High** |
| `G-PARAMS` | `Target_PER`, `Target_PBV`, type→mode map, growth caps, ERP, discount premia | Peter Lynch IV, DDM, Discounted Earnings | Hard-coded in workbook formulas with no `Reference` table → must be lifted into a parameter spec | Medium |
| `G-OVERRIDE` | Manual stock-type override (`B81`) | Stock-type classifier final output | Product decision: support or explicitly not support | Low |

### 8.2 Class D — not currently defined / unresolved

| ID | Item | Why unresolved |
|---|---|---|
| `G-SHARES-Q` | Quarterly shares outstanding | Excel has `Stock_Database_Quarter!N`; canonical `OUTSTANDING_SHARES` is **annual only**. Mean-Reversion PBV IV matched Excel **only** when period-correct quarterly shares were supplied. Options: extend ingestion, or accept a documented approximation. **Requires a product/data decision.** |
| `G-PIT` | Point-in-time availability | `financial_periods.available_date` and `report_date` are **NULL for all 33 periods**. The workbook's quarterly logic depends on `Data Available Date`. Without it, PIT correctness cannot be enforced — only approximated via `period_end` or `ingestion_files.last_record_date`. |
| `G-SCOPE` | Statement scope / period basis | `statement_scope = UNKNOWN` for all periods; annual `period_basis = UNKNOWN`. Consolidated vs standalone is unverifiable, yet the test spec wants a `STATEMENT_SCOPE_UNKNOWN` flag. |
| `G-CONF` | Confidence-level formula | `MetricsClassification!B83` body only partially extracted. Must be re-read. |
| `G-F16-F17` | Forensic `B16` (debt vs profit growth) and `B17` (margin spike) | Only their diagnostic text was extracted; the numeric formulas must be re-read. |
| `G-BACKTEST` | Backtest cases and outcomes | `Backtest_Result` is **static pasted values with 0 formulas**. The generation rule is not in the workbook. The frontend has its own engine with **different** parameters (3/6/9/12-month horizons, ±20%/−15%) and uses `high`/`low`. |
| `G-TTM-DIV` | TTM dividend window | `dividend_facts.TTM` has no `period_year` and no `event_date`; all 16 dividend rows have `event_date = NULL`. |
| `G-2019-DPS` | 2019 DPS = 0 vs absent | Excel has a 2019 row with DPS `0`; `dividend_facts` starts at 2020. Changes Payout Average by ~20% (`0.2728` vs `0.3273`). |
| `G-2019-COGS` | 2019 blank COGS | Excel 2019 COGS is blank → Gross Profit falls back to Revenue (`15,444.8`), inflating GPM Range to `87.72 ppt`. Canonical has `GROSS_PROFIT = 2188.244` bn for 2019. |
| `G-LIQ-DEF` | Liquidity definition conflict | Excel = 3-calendar-month average volume; forward test spec = **20-day** rolling turnover. Two incompatible definitions. |
| `G-MOS-THRESH` | MoS threshold conflict | Workbook entry threshold `35%`; frontend `backtestMethodology` `30%`. |
| `G-CONSENSUS-DENOM` | IV consensus denominator | Excel divides by **valid** methods; frontend divides by **total**. |

### 8.3 Class A/B summary

Everything in §5 marked **A** or **B** is implementable from canonical PostgreSQL
alone (given the §13 parameter seeds for weight/threshold items). The **only**
structural data gaps that block exact parity are:

1. `G-SHARES-Q` — quarterly shares (affects Mean-Reversion PBV IV exactness)
2. `G-PIT` — `available_date` (affects point-in-time correctness and the
   `Data Available Date`-driven quarterly logic)
3. `G-RFR` — risk-free rate (blocks DDM and Discounted Earnings entirely)
4. `G-PROJ` — projection engine (blocks the entire forward-looking layer)
5. `G-MOOD` — market mood (blocks market-adjusted targets)

`STOCKHOLDERS_EQUITY`, and the four cash-flow lines.

**Note:** `EBIT` is the *correct* numerator for a true interest-coverage ratio and is
already available — a genuine improvement opportunity that Excel does not take (§5.14).

| Sector/type weight tables | Type & Sector Weighted IV | in workbook only |
| DER/CR thresholds by type | Health score | in workbook only |
| `Min ICR` threshold column | Health score ICR component | **does not exist** |
| Market Mood inputs (IHSG/MA200, foreign flow, BI rate) | Market Mood, market-adjusted target | **missing** |
| `financial_periods.available_date` / `report_date` | Point-in-time correctness | **all NULL** |
| Projection methodology spec | all `Proj_*` | **missing** |


---

## 9. Projection-Dependent Calculations

### 9.1 The `Proj_*` series

All eleven projections live in `DataInputProyeksi` column `F`, rows 12–25. They are
driven by the **latest audited quarter** plus an **annualisation factor** based on the
as-of quarter (`B4`):

| Named range | Cell | Annualisation (quarterly mode) |
|---|---|---|
| `Proj_Revenue` | `F12` | `Q1→B*4`, `Q2→(B+C)*2`, `Q3→(B+C+D)*(12/9)`, `Q4→B+C+D+E` |
| `Proj_COGS` | `F13` | same factor |
| `Proj_Interest` | `F14` | same factor |
| `Proj_Net_Income` | `F15` | same factor |
| `Proj_OCF` | `F16` | same factor |
| `Proj_DPS` | `F17` | `(Proj_NI × payout) / shares × 1000` |
| `Proj_Assets_Curr` | `F21` | **no factor** — latest quarter passed through (`IFS(Q1→B, Q2→C, Q3→D, Q4→E)`) |
| `Proj_Liab_Curr` | `F22` | no factor — latest quarter passed through |
| `Proj_Liab_Total` | `F23` | no factor — latest quarter passed through |
| `Proj_Equity` | `F24` | no factor — latest quarter passed through |
| `Proj_Shares` | `F25` | latest annual `Shares (Juta)`, with `MAXIFS` fallback |
| `Proj_Dividend_Payout_Ratio` | `B6` | `IF(B7<>"", B7, TRIMMEAN(Range_DPR, 0.4))` |

### 9.2 Verified AUTO projection values

| Projection | AUTO value | Source check |
|---|---:|---|
| `Proj_Revenue` | `21705.406` | `(5256.848 + 5595.855) × 2` ✅ |
| `Proj_COGS` | `−18329.472` | `(−4414.982 + −4749.754) × 2` ✅ |
| `Proj_Interest` | `36.56` | `(9.056 + 9.224) × 2` ✅ |
| `Proj_Net_Income` | `2302.87` | `(558.949 + 592.486) × 2` ✅ |
| `Proj_OCF` | `1500.906` | `(410.715 + 339.738) × 2` ✅ |
| `Proj_DPS` | `113.59181280987761` | `(2302.87 × 0.237739) / 4819.733 × 1000` ✅ |
| `Proj_Assets_Curr` | `11056.363` | 2026-Q2 current assets ✅ |
| `Proj_Liab_Curr` | `5459.244` | 2026-Q2 current liabilities ✅ |
| `Proj_Liab_Total` | `6686.521` | 2026-Q2 total liabilities ✅ |
| `Proj_Equity` | `17195.384` | 2026-Q2 total equity ✅ |
| `Proj_Shares` | `4819.733` | 2025 annual shares ✅ |
| `Proj_Dividend_Payout_Ratio` | `0.23773908589264262` | `TRIMMEAN(Range_DPR, 0.4)` ✅ |

**All twelve reproduced exactly from canonical data.** The projection engine is
therefore **fully specified by the workbook** and does **not** require an external
methodology — it is a deterministic annualisation plus a trimmed-mean payout. This
materially lowers the `G-PROJ` effort estimate from "invent a model" to
"reimplement a documented rule".

### 9.3 Why projections are still Class C

Although the *rule* is deterministic, the workbook obtains it from **quarterly columns
`B`–`E`** whose values are `SUMIFS` over `Stock_Database_Quarter` filtered by
`Data Available Date <> ""`. Canonical data has the quarterly facts but **not** the
availability dates (`G-PIT`). So:

- The arithmetic is replicable (**B**).
- The **as-of quarter selection** (`B4` — which quarter is "latest") depends on
  `Data Available Date` or a manual override. For AUTO it is **manual**
  (`SUMMARY!E4 = 2025`, `SUMMARY!E5 = "Q2"`) → **C**.

### 9.4 Metrics that cannot exist without projections

| Metric | Depends on |
|---|---|
| EPS Annualized (Proj) | `Proj_Net_Income`, `Proj_Shares` |
| BVPS Fwd | `Proj_Equity`, `Proj_Shares` |
| PER (Proj) / PBV (Proj) | above + current price |
| PEG | PER (Proj) + EPS CAGR |
| PBV percentile | `Metric_PBV_Fwd` |
| Peter Lynch Algo IV | `BVPS_fwd` (and `EPS_fwd` for non-cyclical) |
| Type & Sector Weighted IV | `EPS_fwd`, `BVPS_fwd` |
| Mean Reversion PBV IV | `BVPS_fwd` |
| DDM IV | `Proj_DPS` |
| Discounted Earnings IV | `EPS_fwd` |
| DER (template) | `Proj_Equity` |
| Total Health Score | DER component |
| ROE (Proj) | `Proj_Net_Income`, `Proj_Equity` |
| CF Status | `Proj_OCF`, `Proj_Net_Income` |
| Stock Type Classifier | `Proj_Net_Income > 0` |
| Strategic Target / Ideal Price | IV baseline |
| Dividend Yield (Proj), DPR (Proj) | `Proj_DPS` |

**20 of 38 primary metrics depend on projections.** This is the dominant
implementation risk and justifies sequencing projections immediately after the
actuals layer.


---

## 10. Historical-Series Calculations

### 10.1 Series required

| Series | Length | Used by |
|---|---|---|
| Annual revenue | 7 | CAGR (long/short), CoV, YoY, momentum, asset growth gap |
| Annual EPS | 6–7 | EPS CAGR (long/short), momentum, PEG, PER average |
| Annual net income | 7 | ROE average, NPM average, ROE stability, trends |
| Annual total equity | 7 | ROE average, equity growth consistency, BVPS |
| Annual current assets | 7 | Current asset growth, asset growth gap, NWC intensity |
| Annual current liabilities | 7 | NWC, NWC intensity |
| Annual total liabilities | 7 | DER, liquidation value |
| Annual OCF | 7 | CF status, quality |
| Annual interest expense | 7 | ICR |
| Annual stock price | 7 | PER/PBV series, dividend yield, market cap |
| Annual DPS | 6–7 | Yield, payout, DDM |
| **Quarterly equity** | 26 | Mean-Reversion PBV IV (20-quarter window) |
| **Quarterly price** | 26+ | Mean-Reversion PBV IV, quarterly PBV |
| **Quarterly shares** | 26 | Mean-Reversion PBV IV (**missing** — `G-SHARES-Q`) |
| **Daily volume** | 1.619 | Avg Vol (3M), liquidity tier |
| **Daily close** | 1.619 | PIT price, year-end price, quarter-end price |

### 10.2 Ordering and windowing rules (critical)

1. **Newest-first indexing.** `DataInput` columns run newest-first (`C` = latest,
   `I` = oldest). Excel's `INDEX(Range_X, 1)` therefore means **latest**, and
   `INDEX(Range_X, n)` means **n-th newest**. Replicate with
   `ORDER BY period_end DESC` plus an explicit offset — do **not** assume ascending.
2. **Window length** = `Years_Avail` (7) for long metrics, `Years_Compare` (5) for
   short metrics. `Years_Compare` is itself derived from `Years_Avail`
   (`>=7→5`, `>=5→3`, `>=3→2`, else `0`).
3. **`RRI` semantics** = `(end/start)^(1/n) − 1` where `start` is the **older** value
   and `n` = number of periods. Using `min`/`max` instead of first/last gives a
   different answer (verified: `0.0900` vs `0.0432` for AUTO).
4. **`STDEV.P`** = population standard deviation (`stddev_pop`), not sample.
5. **`TRIMMEAN`** trim count = `FLOOR(n × pct / 2)` per tail. For `n=6, pct=0.2`
   the trim is **0**, so it equals the plain mean.
6. **`PERCENTRANK.INC`** is inclusive and interpolated — not `PERCENT_RANK()`.
7. **Negative-base CAGR** uses a **linear** fallback, not compounding (§5.41).
8. **Outlier filter** for the PER average: `EPS > AVERAGE(EPS) × 0.25`.
9. **Missing dividend years count as DPS = 0** for average purposes (§5.23).

### 10.3 Historical-series metrics

Revenue CAGR (long/short), Revenue CoV, Revenue Growth YoY, Revenue Momentum,
EPS CAGR (long/short), EPS Momentum, Asset Growth Gap, Current Asset Growth,
NWC Intensity (latest + change), PER historical average, PBV historical average
(all + 5Y), PBV percentile, Dividend Yield average, Payout average, ROE average,
ROE stability, NPM average, GPM range, Equity growth consistency, Mean-Reversion
PBV IV, Quarterly YoY thesis, Avg Vol (3M), liquidity tier.

---

## 11. Point-in-Time / As-of-Date Rules

### 11.1 Rules

| ID | Rule |
|---|---|
| `PIT-1` | Every price used by a calculation must be the **last `close_price` on or before** the requested as-of date. Never the global latest. |
| `PIT-2` | Year-end price uses `as_of = YYYY-12-31` and takes the last available close on or before it. |
| `PIT-3` | Quarter-end price uses `as_of = Data Available Date` (workbook) or `period_end` (approximation). |
| `PIT-4` | Avg Vol (3M) window = `[EDATE(as_of, −3), as_of]` **inclusive**, averaged over available rows only. |
| `PIT-5` | `current_price` for valuation = last close on or before the workbook's as-of date. The AUTO workbook as-of is **2026-Q2** (`2350`); the DB's latest is **3340** (`2026-09-24`). These are **different dates**, not conflicting values. |
| `PIT-6` | Financial facts must be selected from the period whose `available_date` (or approximation) is on or before the as-of date. When `available_date` is NULL, emit `POINT_IN_TIME_UNSAFE`. |
| `PIT-7` | The as-of date must be an **explicit input** to every calculation run and stored on the result row (`observation_date` / `valuation_date`). |
| `PIT-8` | Idempotency keys must include the as-of date / source cutoff, so a re-run at a new date creates a **new** run rather than mutating the old one. |

### 11.2 Verified PIT behaviour

| As-of | Last close ≤ as-of | Date used |
|---|---:|---|
| 2020-12-31 | 1115 | 2020-12-30 |
| 2021-12-31 | 1155 | 2021-12-30 |
| 2022-12-31 | 1460 | 2022-12-30 |
| 2023-12-31 | 2360 | 2023-12-29 |
| 2024-12-31 | 2300 | 2024-12-30 |
| 2025-12-31 | 2690 | 2025-12-30 |
| 2026-06-30 | 2350 | 2026-06-30 |
| (none / latest) | 3340 | 2026-09-24 |

Every year-end resolves to **Dec 29/30**, because 31-Dec is a market holiday in most
years. The "last close ≤ 31-Dec" rule handles this correctly; a naive
`WHERE trading_date = 'YYYY-12-31'` would return nothing.

### 11.3 PIT blocker

`financial_periods.available_date` and `report_date` are **NULL for all 33 periods**,
and `statement_scope` is `UNKNOWN` everywhere. Therefore:

- **Price PIT is fully reliable** (100% populated, verified against Excel).
- **Fundamental PIT is not enforceable.** Period selection can only use `period_end`
  (a look-ahead risk) or `ingestion_files.last_record_date` (a coarse proxy). This
  must be an explicit, documented limitation, and the `POINT_IN_TIME_UNSAFE` flag
  should be emitted until `available_date` is populated.

---

## 12. Unit Normalization Rules

### 12.1 Canonical storage units (do not change)

| Field | Unit | Example (AUTO 2025) |
|---|---|---|
| `financial_facts.value_numeric` (flows/balances) | IDR | `19.906.774.000.000` |
| `financial_facts.value_numeric` (`EPS`) | IDR per share | `457.4987867585196` |
| `financial_facts.value_numeric` (`OUTSTANDING_SHARES`) | shares (raw units) | `4.819.733.000` |
| `financial_facts.unit_code` | `IDR` / `IDR_PER_SHARE` / `SHARES` | — |
| `prices_daily.close_price` | IDR per share | `2690` |
| `prices_daily.volume` | shares | `4.832.534,375` |
| `prices_daily.market_cap` | IDR | (partial) |
| `dividend_facts.amount_per_share` | IDR per share | `192` |
| `dividend_facts.yield_ratio` | ratio | `0.0856624320149422` |

### 12.2 Excel presentation units (documented, not "fixed")

| Excel label | Actual unit | Factor from canonical |
|---|---|---|
| `(M Rp)` on financial columns | **billion IDR (miliar)** | `÷ 1e9` |
| `Shares (Juta)` | **millions of shares** | `÷ 1e6` |
| `Stock Price (Rp)` | IDR per share | `× 1` |
| `EPS (Rp)` / `BVPS (Rp)` | IDR per share | `× 1` |
| `DPS (Rp)` | IDR per share | `× 1` |
| `Market Cap [M Rp]` | **billion IDR** | `price × shares ÷ 1e9` |
| `Avg Vol (3M)` | shares | `× 1` |
| `[ppt]` on NWC Intensity Change | **ratio** (label is wrong) | `× 1` |

### 12.3 The `×1000` trap (most likely scaling bug)

Excel's `×1000` in `EPS = NI/Shares×1000` and `BVPS = Equity/Shares×1000` exists
**only** because Excel's `Shares` column is in **Juta**. Canonical
`OUTSTANDING_SHARES` is in **raw units**, so:

```text
EPS_canonical  = EARNINGS / OUTSTANDING_SHARES          # NO x1000
BVPS_canonical = TOTAL_EQUITY / OUTSTANDING_SHARES      # NO x1000
```

Verified: `2205022000000 / 4819733000 = 457.4987867` = stored `EPS` ✅.
Applying `×1000` to the raw division is a **1.000× error**.

Equivalent, unit-explicit form:
`IDR_per_share = (value_billion_IDR / shares_millions) × 1000`.

### 12.4 Ratio and percentage conventions

| Quantity | Storage | Display |
|---|---|---|
| Ratios (yield, payout, CoV, CAGR, MoS, percentile) | decimal ratio | `× 100` + `%` |
| Multiples (PER, PBV, PEG, CR, DER, ICR) | x | `"x"` suffix |
| `NWC Intensity Change` | decimal ratio | workbook labels `ppt` but shows `%` — **keep the ratio** |
| Health score | integer 0–100 | integer |
| `GPM Range` | percentage points | `ppt` |
| Thresholds (liquidity `2e11`, MoS `0.35`) | **absolute IDR** / ratio | as-is |

### 12.5 Rules

| ID | Rule |
|---|---|
| `U-1` | Canonical `value_numeric` stays in raw IDR / raw shares. **Never** rewrite stored units. |
| `U-2` | Convert to presentation units only at the API/export boundary. |
| `U-3` | Never apply `×1000` to a raw-IDR ÷ raw-shares division. |
| `U-4` | Persist the **ratio**; format as percent in the client. |
| `U-5` | Preserve the `(M Rp)` label in any Excel-parity export, because changing it would break comparison with the reference workbook. |
| `U-6` | Do **not** "correct" the `ppt` mislabel on NWC Intensity Change in the reference model; document it. |



---

## 13. Parameter / Threshold / Weight Sources

### 13.1 Sector weights — `Reference!B5:C16` (named range `Method_Weights_Sector`)

| Sector | `W_PE` | `W_PBV` |
|---|---:|---:|
| Basic Materials | 2 | 2 |
| Consumer Cyclicals | 3 | 1 |
| Consumer Non-Cyclicals | 3 | 2 |
| Energy | 1 | 2 |
| Financials | 1 | 3 |
| Healthcare | 3 | 1 |
| Industrials | 2 | 2 |
| Infrastructures | 1 | 2 |
| Properties & Real Estate | 1 | 3 |
| Technology | 3 | 1 |
| Transportation & Logistic | 2 | 2 |
| Utilities | 1 | 3 |

### 13.2 Stock-type weights — `Reference!B22:C26` (`Method_Weights_Type`)

| Stock Type | `W_PE` | `W_PBV` |
|---|---:|---:|
| Asset Play | 0 | 3 |
| Cyclical | 0 | 10 |
| Fast Grower | 3 | 0 |
| Slow Grower | 2 | 3 |
| Stalwart | 3 | 2 |
| Turn around | 0 | 3 |

**AUTO:** sector `Consumer Cyclicals` (`3,1`) + type `CYCLICAL` (`0,10`) →
`Param_W_PE = (3+0)/2 = 1.5`, `Param_W_PBV = (1+10)/2 = 5.5` ✅

### 13.3 DER / CR thresholds — `Reference!B32:C37` (`StockType_Threshold`)

| Stock Type | `Max DER` | `Min CR` |
|---|---:|---:|
| Slow Grower | 0.5 | 1.5 |
| Stalwart | 0.8 | 1.3 |
| Fast Grower | 1.0 | 1.2 |
| Cyclical | 0.3 | 2.0 |
| Turn around | 0.5 | 1.5 |
| Asset Play | 0.4 | 1.5 |

`Min ICR` is **referenced by the formula but does not exist** in the table
(`Ref_Type_MinICR` → missing column). The formula falls back to `3`.

**Sector overrides (not in `Reference`, hard-coded in the formula):**
`Financials → Max DER 15`; `Properties → Max DER 2`.

### 13.4 Hard-coded constants inside formulas (no `Reference` entry)

These parameters currently have **no external, reviewable source** and must be lifted
into a versioned parameter spec:

| Constant | Value | Used in |
|---|---:|---|
| Risk-free rate | `0.0633` | `DataInput!B11` → DDM, Discounted Earnings |
| Equity risk premium (DDM) | `+0.06` | `ValuationCurrent!B28` |
| DDM growth cap | `0.04` | `ValuationCurrent!B28` |
| Discount premium (Disc. Earnings) | `+0.04` | `ValuationCurrent!B29` |
| Growth cap (Disc. Earnings) | `0.15` | `ValuationCurrent!B29` |
| PER cap | `25` | `ValuationCurrent!B29` |
| Disc. Earnings horizon | `5` years | `ValuationCurrent!B29` |
| Fallback growth | `0.05` | `ValuationCurrent!B29` |
| Fallback PER | `15` | `ValuationCurrent!B29` |
| `Target_PER` by type | Cyclical/AssetPlay/TurnAround `0`; Stalwart+Financial `25`; Slow `12`; Stalwart `16`; Fast `growth×100×1.2` | `ValuationCurrent!B4`,`B5` |
| `Target_PBV` by mode | Conservative `0.4`/`0.8`; Moderate `0.5`/`1.0`; Aggressive `0.7`/`1.2` | `ValuationCurrent!B7`,`B8` |
| Type → mode map | Fast→Aggressive; Cyclical/AssetPlay/Stalwart→Moderate; else Conservative | `ValuationCurrent!B7`,`B8` |
| Mean-Reversion min quarters | `3` | `ValuationCurrent!B27` |
| PER-average outlier factor | `0.25` | `MetricsClassification!B36` |
| Payout trim (projection) | `0.4` | `DataInputProyeksi!B6` |
| Payout/yield trim (historical) | `0.2` | `MetricsClassification!B32`,`B34` |
| Liquidity thresholds | `2e11`, `5e10`, `1e10` IDR | `SUMMARY!B56` |
| Business-quality NPM bands | `0.15`, `0.08` | `SUMMARY!B57` |
| Business-quality market-cap bands | `10000`, `2000` (bn IDR) | `SUMMARY!B57` |
| Business-quality ROE threshold | `0.15` | `SUMMARY!B57` |
| GCG yield threshold | `0.03` | `SUMMARY!B58` |
| Quality multiplier bands | `>=5 → 1.2`, `>=3 → 1.0`, else `0.7` | `SUMMARY!B74` |
| OCF/NI quality thresholds | `0.6` (cyclical), `0.8` (other) | `FinancialHealth!B26` |
| OCF/NI penalty bands | `<0.4 → −40`, else `<thr → −20` | `FinancialHealth!B26` |
| Forensic flag bands | `0.05`, `0.1`, `−0.1` | `FinancialHealth!B23` |
| Health rating bands | `85`, `70`, `50` | `FinancialHealth!B27` |
| Health clearance OCF/NI | `0.8` | `FinancialHealth!B18` |
| CF-status OCF/NI | `0.5` | `MetricsClassification!B69` |
| Stock-type thresholds | `0.08`, `0.2`, `0.05`, `0.12`, `0.1`, `0.35`, `0.15`, `0.8` | `MetricsClassification!B80` |
| Stock-type score ladder | `100/80/60/40/20/10` | `MetricsClassification!B80` |
| Energy sector override | force `CYCLICAL` | `MetricsClassification!B80` |
| Mood multipliers | Bearish `0.8`, Neutral `0.9`, Bullish `1.0` | `SUMMARY!B73` |
| Ideal-price discount | `0.7` | `SUMMARY!B80` |
| Quarterly YoY offset | `3` | `DataInputProyeksi!B47`–`B52` |
| Avg Vol window | `EDATE(asof, −3)` | `Stock_Database_Quarter!O` |
| MoS entry threshold | `0.35` (workbook) / `0.30` (frontend) | `SUMMARY!C48` / `backtest.ts` |
| IV consensus minimum | `3` of 5 (frontend only) | `backtest.ts` |
| Backtest horizons / thresholds | 3/6/9/12 months; `+0.20/−0.15`; `+0.15/−0.10` | `backtest.ts` |

### 13.5 Parameter governance requirement

Because the §13.4 constants are **embedded in formulas**, they cannot be versioned
today. The forward test suite already requires a `methodology_versions` table with
`parameter_spec` and `parameter_hash`. Phase 4 must therefore:

1. Extract every constant in §13.4 into a **parameter spec**.
2. Store it with `methodology_versions.parameter_spec` + `parameter_hash`.
3. Reference it by `methodology_version_id` from every result row.

Without this, "reproducibility" cannot be demonstrated — a parameter change would
silently alter historical results.

### 13.6 Excel-defined names verified as broken

| Name | Target |
|---|---|
| `Calc_Method` | `#REF!` |
| `Param_Growth` | `#REF!` |
| `Param_Price` | `#REF!` |
| `Proj_Mode` | `#REF!` |
| `Engine_Rec_Action` | empty sheet target |

`Param_Growth` and `Param_Price` are referenced by `SUMMARY!B77` (Dividend Safety),
which is why that cell returns `#REF!`. **Documented, not fixed** (Phase 3 §10.5).


---

## 14. Calculation Dependency Graph

### 14.1 Layered graph

```text
LAYER 0 - CANONICAL SOURCE (read-only)
  financial_periods, financial_facts, prices_daily, dividend_facts,
  instruments, sectors, instrument_sector_classifications

LAYER 1 - PIT PRIMITIVES (no dependencies beyond Layer 0)
  as_of_date (input)
  price_asof(as_of)            = last close_price <= as_of
  year_end_price(year)         = price_asof(YYYY-12-31)
  quarter_end_price(period)    = price_asof(period_end)
  avg_volume_3m(as_of)         = AVG(volume) over [EDATE(as_of,-3), as_of]
  latest_annual_period() / latest_quarter_period()
  ordered_series(metric, type) = facts ORDER BY period_end DESC

LAYER 2 - BASE FACTS (direct reads + unit normalisation)
  revenue, cogs, gross_profit, net_income, ocf, interest_exp,
  current_assets, current_liabilities, total_liabilities, total_equity,
  shares_outstanding, eps_stored, dps, close_price, volume

LAYER 3 - PERIOD DERIVATIVES
  eps            = EARNINGS / OUTSTANDING_SHARES          (or stored EPS)
  bvps           = TOTAL_EQUITY / OUTSTANDING_SHARES
  gross_margin   = (REVENUE - COST_OF_REVENUE) / REVENUE
  npm            = EARNINGS / REVENUE
  roe            = EARNINGS / TOTAL_EQUITY
  nwc            = current_assets - current_liabilities
  nwc_intensity  = nwc / revenue
  current_ratio  = current_assets / current_liabilities
  quick_ratio    = (current_assets - inventories) / current_liabilities  [annual only]
  der_actual     = TOTAL_LIABILITIES / TOTAL_EQUITY
  icr_template   = (EARNINGS - interest_exp) / ABS(interest_exp)
  per            = price_asof / eps
  pbv            = price_asof / bvps
  dpr_template   = dps / eps
  div_yield      = dps / year_end_price
  market_cap     = price_asof * shares_outstanding / 1e9

LAYER 4 - HISTORICAL SERIES AGGREGATES
  rev_cagr_long  = RRI(Years_Avail-1, rev[oldest], rev[newest])
  rev_cagr_short = RRI(Years_Compare, rev[n-1], rev[newest])
  rev_cov        = STDEV.P(revenue) / AVG(revenue)
  rev_yoy        = rev[0]/rev[1] - 1
  rev_momentum   = rev_cagr_short > rev_cagr_long
  eps_cagr_long / eps_cagr_short   (with negative-base fallback)
  eps_momentum
  curr_asset_growth    = ca[0]/ca[1] - 1
  asset_growth_gap     = rev_yoy - curr_asset_growth
  nwc_intensity_change = nwc_int[0] - nwc_int[1]
  yield_hist_avg = TRIMMEAN(dps/price, 0.2)
  payout_avg     = TRIMMEAN(dps/eps, 0.2)        [+ missing year = 0]
  pe_avg_long    = AVG(price/eps) with EPS > 0.25*AVG(EPS) filter
  pbv_avg_long   = AVG(price/bvps) all years
  pbv_avg_5y     = AVG(first 5 of pbv series)
  pbv_pct        = PERCENTRANK.INC(pbv_series, pbv_fwd)
  roe_avg, npm_avg, roe_stability, gpm_range, equity_growth_consistency
  quarterly_yoy_thesis (4 quarters x 5 metrics)

LAYER 5 - PROJECTIONS  (depends on Layer 3 + Layer 4 payout)
  proj_revenue, proj_cogs, proj_interest, proj_net_income, proj_ocf
      = annualise(latest quarter YTD)
  proj_assets_curr, proj_liab_curr, proj_liab_total, proj_equity
      = latest quarter passthrough
  proj_shares = latest annual shares
  proj_payout = TRIMMEAN(dpr_series, 0.4)
  proj_dps    = (proj_net_income * proj_payout) / proj_shares * 1000
  eps_fwd     = proj_net_income / proj_shares * 1000
  bvps_fwd    = proj_equity / proj_shares * 1000

LAYER 6 - VALUATION MULTIPLES (forward)
  pe_fwd    = price_asof / eps_fwd
  pbv_fwd   = price_asof / bvps_fwd
  peg       = pe_fwd / (eps_cagr_long * 100)
  yield_fwd = proj_dps / price_asof

LAYER 7 - STOCK TYPE
  stock_type = classifier(Layer 4 + Layer 6 + sector + proj_net_income)
  -> REQUIRED BY Layer 8 and Layer 9

LAYER 8 - VALUATION METHODS (depends on Layer 3-7)
  per_fair_bottom/top = Target_PER(type) * eps_fwd
  liquidation_value   = (current_assets - total_liabilities) / proj_shares * 1000
  asset_play_target   = bvps_fwd * Target_PBV(mode)
  cyclical_target     = bvps_fwd * Target_PBV(mode)
  iv_peter_lynch      = IFS(stock_type, growth/momentum)
  w_pe, w_pbv         = (sector_weight + type_weight) / 2
  iv_weighted         = (eps_fwd*pe_avg*w_pe + bvps_fwd*pbv_avg*w_pbv) / (w_pe+w_pbv)
  iv_mean_reversion   = MAX((AVG(qPBV) - STDEV.P(qPBV)) * bvps_fwd, 0)
  iv_ddm              = proj_dps*(1+g_s) / (WACC - g_s)           [needs risk-free]
  iv_disc_earnings    = (eps_fwd*(1+g)^5 * PE_cap) / (1+disc)^5   [needs risk-free]
  iv_consensus        = count(iv_i > price) / valid_count

LAYER 9 - RISK / QUALITY (depends on Layer 3-7)
  der_projected    = total_liabilities / proj_equity
  health_score     = 5 x 20-point checks + OCF/NI penalty
  clearance        = forensic gate
  business_quality = brand + gcg + liquidity_tier
  liquidity_tier   = avg_volume_3m * price_asof vs thresholds
  market_mood      = [NEEDS EXTERNAL INPUT]

LAYER 10 - OUTPUT COMPOSITES (depends on Layer 8-9)
  iv_baseline        = IF(main="Peter Lynch", iv_peter_lynch, iv_weighted)
  market_adj_price   = iv_baseline * mood_multiplier           [NEEDS mood]
  quality_adj_target = market_adj_price * quality_multiplier
  mos_fundamental    = (iv_baseline - price) / iv_baseline
  mos_final          = (quality_adj_target - price) / quality_adj_target
  ideal_price        = iv_baseline * 0.7
```


### 14.2 Hard dependency chains (blockers)

| Chain | Why it blocks |
|---|---|
| `Layer 4 → Layer 7 → Layer 8` | The classifier needs `proj_net_income`, `pbv_fwd`, `pbv_pct`, `rev_cagr`, `rev_cov`, `eps_cagr`, `roe_avg`. Every valuation method needs the classifier. **So no IV method can be produced without projections + history + classifier.** |
| `Layer 5 → Layer 8` | All five IV methods need `eps_fwd`, `bvps_fwd`, or `proj_dps`. |
| `Layer 8 → Layer 10` | Every target / MoS needs an IV. |
| `risk_free → Layer 8` | DDM and Discounted Earnings are blocked outright. |
| `mood → Layer 10` | `market_adj_price`, `quality_adj_target`, `mos_final` blocked. |
| `quarterly shares → Layer 8` | Exactness of the mean-reversion method. |

### 14.3 Critical-path observation

The dependency graph shows the **classifier is a hub**: it sits between history and
valuation and is required by all five methods. Any error in the classifier (e.g. AUTO
flipping from `CYCLICAL` to `SLOW GROWER`) changes `iv_peter_lynch` from
`bvps_fwd × 1.0` to a PER-based value — a completely different number. Therefore the
classifier must be validated **before** any valuation work is trusted.

---

## 15. Recommended Implementation Order

Ordered by dependency and by risk retirement. Each step states its exit criterion.

### Step 1 — Parameter & methodology registry (no math)
- Extract every §13.4 constant into a versioned parameter spec.
- Define the **method-code registry** (§3.6) mapping Excel prose → test-spec codes.
- Seed sector weights, type weights, DER/CR thresholds from §13.1–13.3.
- **Exit:** every §13.4 constant has a named, versioned home; `parameter_hash` reproducible.

### Step 2 — PIT primitives (Layer 1)
- `price_asof`, `year_end_price`, `quarter_end_price`, `avg_volume_3m`,
  `latest_annual_period`, `latest_quarter_period`, `ordered_series`.
- **Exit:** reproduces the seven verified year-end prices and the 2026-Q2
  `Avg Vol (3M) = 2449150.8474576273` exactly.

### Step 3 — Period derivatives (Layers 2–3)
- EPS, BVPS, margins, ROE, NWC, NWC intensity, CR, quick ratio, DER (actual), ICR,
  PER, PBV, DPR, dividend yield, market cap.
- **Exit:** reproduces §4.9 and §5 AUTO values exactly, including the
  **no-`×1000`** EPS/BVPS rule and the **positive-COGS subtraction** rule.

### Step 4 — Historical aggregates (Layer 4)
- CAGR (with negative-base fallback), CoV (`STDEV.P`), YoY, momentum, asset growth
  gap, NWC intensity change, trimmed averages, PER/PBV averages, percentile,
  quality block, quarterly YoY thesis.
- **Exit:** reproduces `rev_cagr 0.0432 / 0.1090`, `rev_cov 0.15782`,
  `payout_avg 0.27277` (with 2019 = 0), `pe_avg 6.38294`, `pbv_avg 0.67176`,
  `pbv_avg_5y 0.71075`, `yield_hist 0.05181`, and the AUTO quarterly thesis table.

### Step 5 — Projection engine (Layer 5)
- Annualisation by as-of quarter, quarterly passthrough, payout trim, `Proj_DPS`.
- **Exit:** reproduces all twelve §9.2 values exactly.

### Step 6 — Forward multiples (Layer 6)
- `eps_fwd`, `bvps_fwd`, `pe_fwd`, `pbv_fwd`, `peg`, `yield_fwd`.
- **Exit:** `eps_fwd 477.8003262836343`, `bvps_fwd 3567.7046840561493`,
  `pe_fwd 4.918372530798526`, `pbv_fwd 0.6586868051332847`, `peg 0.24632`.

### Step 7 — Stock-type classifier (Layer 7) — **highest-risk step**
- Full `IFS` rule set + score ladder + Energy override + manual-override channel.
- **Exit:** AUTO classifies as `CYCLICAL`; each of the six rules is unit-tested
  independently with boundary cases (`RevLong` exactly `0.08` / `0.2`;
  `RevCoV` exactly `0.35`; `PBV_Pct` exactly `0.2`).

### Step 8 — Risk & quality (Layer 9)
- `der_projected`, health score (six components), clearance, business quality,
  liquidity tier.
- **Exit:** AUTO health score = `80` with the documented component breakdown
  (`0+20+20+20+20+0`); business quality = `2` → multiplier `0.7`;
  liquidity = `Third Liner / Illiquid (< 10 M)`.

### Step 9 — Valuation methods (Layer 8)
- Implement in ascending dependency order:
  `iv_mean_reversion` → `iv_weighted` → `iv_peter_lynch` → `iv_disc_earnings`
  → `iv_ddm` (last, because it needs the risk-free rate).
- **Exit:** reproduces `3567.7046840561493`, `2536.6003665489575`,
  `1740.2732423202715`, `2304.8827926499084`, `1418.1931011077158`.

### Step 10 — Consensus, MoS, targets (Layer 10)
- `iv_consensus 2/5`, per-method MoS, `mos_fundamental 0.34131`,
  `ideal_price 2497.3932788393045`.
- **Exit:** all five MoS values and the `2/5` consensus match.

### Step 11 — Deferred items (explicitly gated)
- Market Mood + `market_adj_price` + `quality_adj_target` + `mos_final`
  → **blocked on `G-MOOD`**.
- DDM / Discounted Earnings → blocked on `G-RFR` (or ship with an explicit,
  labelled parameter).
- Backtest cases → blocked on `G-BACKTEST` (generation rule undefined).

### Step 12 — Persistence & API
- `calculation_runs`, `methodology_versions`, `calc_*` tables per the forward test
  spec; idempotency keys; provenance; `input_snapshot`.
- **Exit:** a rerun produces identical results and identical idempotency keys;
  a second run inserts `0` rows.

### 15.1 Rationale for the order

1. **Parameters first** — otherwise nothing is reproducible.
2. **PIT primitives second** — every price depends on them, and they are the most
   easily verified (seven exact matches already available).
3. **Actuals before projections** — projections are built on actuals.
4. **Classifier before valuation** — it is the hub (§14.3).
5. **Risk/quality before methods** — the quality multiplier feeds Layer 10.
6. **DDM last** — it has the extra external dependency.
7. **Persistence last** — so the schema reflects a proven calculation shape rather
   than a guess.


---

## 16. Validation Strategy

### 16.1 Reference oracle

`Template\Stock Analyzer [Dev].xlsm` with its **cached values** is the golden oracle
for ticker `AUTO`, as-of **2026-Q2**, using price `2350`.

### 16.2 Tolerance policy

| Metric type | Tolerance | Rationale |
|---|---|---|
| IDR amounts (canonical) | **exact** | Integer-scale source values |
| Ratios / multiples | `1e-6` relative | Float arithmetic order differences |
| Percentages displayed | `1e-4` (0.01 pp) | Excel display rounding |
| Text enums | **exact** | Emoji / whitespace significant |
| Health score | **exact integer** | Threshold bands |

### 16.3 Validation levels

| Level | What it proves | Method |
|---|---|---|
| **L1 — Input parity** | Canonical values equal the workbook feed | Reuse Phase 3 §9 (already **0 unexplained mismatches**) |
| **L2 — Single-metric parity** | Each derived metric equals the cached workbook value | Metric-by-metric comparison against §5 AUTO values |
| **L3 — Component parity** | Composites equal the sum/product of their components | Health score breakdown (§5.35); weighted-IV component check (§5.28) |
| **L4 — Full-pipeline parity** | All 38 primary + supporting metrics match in one run | Single automated comparison producing a diff report |
| **L5 — Cross-check parity** | Independent recomputation agrees | Recompute from raw IDR without Excel factors (§4.9 style) |
| **L6 — Point-in-time parity** | As-of prices match at multiple dates | Re-run at 2020…2025 year-ends (§11.2) |
| **L7 — Idempotency** | Rerun inserts 0 rows, identical hashes | Run twice, compare row counts + idempotency keys |
| **L8 — Negative cases** | Missing inputs yield `UNAVAILABLE` + flags, never 0 | Synthetic cases per the forward test spec |

### 16.4 Metrics with a ready-made expected value (L2 set)

All of the following have a verified expected value recorded in this document:

`gross_profit 3366.225` · `eps 457.4987867585196` · `bvps_2025 3519.7763` ·
`bvps_fwd 3567.7046840561493` · `per_2025 5.879797` · `per_fwd 4.918372530798526` ·
`pbv_2025 0.764253` · `pbv_fwd 0.6586868051332847` · `dpr 0.419673` ·
`div_yield 0.071375` · `market_cap 11326.37255` · `nwc 5450.640` ·
`nwc_intensity 0.273808` · `der_actual 0.333115` ·
`der_template 0.32864034906112016` · `current_ratio 2.2050015176814868` ·
`icr 49.706` · `rev_cagr_long 0.04320553666520399` ·
`rev_cagr_short 0.10895962318518992` · `rev_cov 0.15781626002544882` ·
`rev_yoy 0.043676416687415065` · `asset_growth_gap −0.07904632120173494` ·
`nwc_intensity_change 0.043010329117029594` · `eps_annualized 477.8003262836343` ·
`peg 0.24632338395521788` · `yield_hist 0.05181071727774073` ·
`payout_avg 0.2727709642351656` · `pe_avg 6.382944640598736` ·
`pbv_avg 0.6717608090692812` · `pbv_avg_5y 0.7107513889852919` · `pbv_pct 0.506` ·
`iv_peter_lynch 3567.7046840561493` · `iv_weighted 2536.6003665489575` ·
`iv_mean_reversion 1740.2732423202715` · `iv_ddm 1418.1931011077158` ·
`iv_disc_earnings 2304.8827926499084` · `iv_consensus 2/5` ·
`mos_fundamental 0.34131319486671524` · `mos_final −0.17622643773800842` ·
`liquidity_tier Third Liner` · `health_score 80` · `business_quality 2` ·
`market_mood BEARISH` · `market_adj_price 2854.1637472449197` ·
`quality_adj_target 1997.9146230714437` · `ideal_price 2497.3932788393045` ·
`stock_type CYCLICAL` · `avg_vol_3m 2449150.8474576273`.

### 16.5 Required test artifacts

1. **AUTO golden fixture** — every value above, frozen as JSON, version-tagged.
2. **Per-metric parity test** — one assertion per fixture key.
3. **Boundary tests** for the classifier and threshold ladders.
4. **Negative tests** for every flag in the forward test spec.
5. **PIT tests** at seven as-of dates.
6. **Idempotency test** — run twice, assert `0` inserts and equal keys.
7. **Divergence register** — a machine-readable list of every accepted divergence
   (§16.6), so parity gaps are never silent.

### 16.6 Divergences that must be registered, not hidden

| Divergence | Expected difference | Decision needed |
|---|---|---|
| Current price | `2350` (2026-Q2) vs `3340` (2026-09-24) | Choose the as-of convention |
| DER | `0.3286` (projected equity) vs `0.3331` (actual) | Publish both |
| Payout average | `0.2728` (2019 = 0) vs `0.3273` (2019 absent) | Treat missing year as 0 |
| 2019 gross profit | `15444.8` (Excel artifact) vs `2188.244` (canonical) | Publish canonical; document |
| GPM range | `87.72 ppt` (artifact-inflated) | Decide whether to keep the artifact |
| MoS threshold | `35%` vs `30%` | Pick one |
| Liquidity | 3-month average vs 20-day rolling | Pick one |
| IV consensus denominator | valid vs total | Pick one |
| Dividend payout | `0.4197` (template) vs `0.4566` (provider) | Publish both |
| Dividend yield | `0.071375` (template) vs `0.08566` (provider) | Publish both |


---

## 17. Explicit Exclusions for Phase 4

The following are **deliberately out of scope** for the Phase 4 calculation engine.

### 17.1 Excluded by instruction

1. No calculation code is written in this phase.
2. No migration is created (`0008_calculation_v1_batch.sql` is **not** created here).
3. No frontend change; `frontend/src/lib/analysis/**` and
   `frontend/src/data/mock-stock-details.ts` are untouched.
4. No change to `docs/EXCEL_POSTGRES_VALIDATION.md`.
5. No change to canonical or raw data, storage, or `ingestion_*` tables.

### 17.2 Excluded from the first calculation release

| Excluded | Reason |
|---|---|
| **Market Mood** and its dependents (`market_adj_price`, `quality_adj_target`, `mos_final`) | `G-MOOD` — no data source. Fabricating a mood would violate P5. |
| **Backtest engine** (WIN/RECOVERED/RISK/FLAT, success rate, sample count) | `G-BACKTEST` — the workbook's `Backtest_Result` is static values with no generation rule. The frontend's existing engine uses **different** parameters. |
| **Manual overrides** (stock type `B81`, manual IV method `B70`, manual price `SUMMARY!E3`) | Product decision required; not defined in canonical data. |
| **Technical / chart metrics** (returns, moving averages, volatility of price, OHLC signals) | Confirmed **not used** by the workbook (Phase 3 §4.1). |
| **Price-level mean reversion** | The workbook's "mean reversion" is **PBV**-based, not price-based. |
| **Open / High / Low / Market Cap from price history** | Confirmed **0 formula references** in the workbook. |
| **`quick_ratio`** for quarterly periods | `INVENTORIES` is annual-only; must return `UNAVAILABLE`. |
| **Bank / insurance metrics** (`NET_PREMIUM_INCOME`, `PREMIUM_*`, `PROVISION`, `NON_LOAN_ASSETS`) | Present in the vocabulary but **all NULL**; no bank ticker in scope. |
| **Presentation strings** (all `✅/⚠️/❌/🛒` labels, verdict prose, diagnostic text, `DB_ANALYSIS`, `ExportConfig`, `Helper`) | Phase 3 §14 — display only. |
| **Dividend Safety (`SUMMARY!B79`)** | `#REF!` in the workbook; requires a product decision. |
| **Confidence Level** | `G-CONF` — formula not fully extracted. |
| **`Engine_*` named ranges** (`Engine_Target_Sell`, `Engine_Hard_Floor`, `Engine_Rec_Action`) | `Engine_Rec_Action` points to an empty target; semantics undefined. |
| **Multi-ticker / sector aggregation** | Only `AUTO` is loaded; scope is single-instrument. |

### 17.3 Explicitly preserved (not "fixed")

Per rule P3, Phase 4 must reproduce — not repair — the following:

1. `Stock_Database!O` "Avg Vol (3M)" returning **Close** (annual defect).
2. The `(M Rp)` label on columns that hold **billion IDR**.
3. The `[ppt]` label on `NWC Intensity Change` that holds a **ratio**.
4. `SUMMARY!B79` = `#REF!` (documented as unavailable, not computed).
5. The missing `Min ICR` threshold column defaulting to `3`.
6. The `2019` blank-COGS gross-profit fallback.
7. The `EPS CAGR 5Y = 43255.73%` near-zero-base artifact.
8. `XLOOKUP` → `"UNCLASSIFIED"` on an unknown sector/type.


---

## 18. Open Questions / Unresolved Gaps

### 18.1 Data & schema questions

| # | Question | Blocks | Owner |
|---|---|---|---|
| Q1 | Will `OUTSTANDING_SHARES` be ingested for **quarterly** periods (`G-SHARES-Q`), or is an annual-share approximation acceptable for Mean-Reversion PBV IV? | Exactness of one of five IV methods | Data/Product |
| Q2 | Will `financial_periods.available_date` / `report_date` be populated (`G-PIT`)? Without it, fundamental PIT is unenforceable. | PIT correctness, `POINT_IN_TIME_UNSAFE` | Data |
| Q3 | Where does the **risk-free rate** come from (`G-RFR`)? External API, manual parameter, or excluded? | DDM + Discounted Earnings | Product |
| Q4 | Is there a **market/macro data source** for Market Mood (`G-MOOD`)? | Market Mood + 3 targets | Product |
| Q5 | Will `statement_scope` / `period_basis` be resolved (`G-SCOPE`)? | Scope flags, consolidation semantics | Data |
| Q6 | Should `dividend_facts` gain a **2019 row**, or should a missing year be treated as `DPS = 0` (`G-2019-DPS`)? | Payout average (~20% difference) | Data/Product |
| Q7 | Will the schema add the columns the forward test suite assumes (`revision_key`, `supersedes_fact_id`, `supersedes_dividend_fact_id`, `prices_daily.available_date`, `financial_periods.source_ingestion_file_id`)? | Persistence layer | Data |
| Q8 | Which of the four `Template\*.xlsm` is the production master? | Reference oracle stability | Product |

### 18.2 Definition & semantics questions

| # | Question | Impact |
|---|---|---|
| Q9 | MoS entry threshold: **35%** (workbook) or **30%** (frontend `backtestMethodology`)? | `G-MOS-THRESH` — verdict flips |
| Q10 | Liquidity definition: **3-calendar-month average volume × price** (Excel) or **20-day rolling turnover** (forward test spec)? | `G-LIQ-DEF` — different tier |
| Q11 | IV consensus denominator: **valid methods** (Excel) or **total methods** (frontend)? | `G-CONSENSUS-DENOM` — displayed ratio |
| Q12 | ICR numerator: keep Excel's **Net Income** (misnamed) or introduce a correctly-named `EBIT`-based variant? | Metric semantics |
| Q13 | Should Phase 4 emit `UNAVAILABLE` where Excel silently substitutes fallbacks (`0.05` growth, `15` PER)? | Parity vs honesty trade-off |
| Q14 | Should the `2019` blank-COGS gross-profit artifact be reproduced or corrected? | GPM range, gross profit 2019 |
| Q15 | Are `DCF`, `DDM`, `GRAHAM`, `RESIDUAL_INCOME` meant to be **persisted as `UNAVAILABLE`** (forward test spec) while the workbook *does* compute a DDM and a discounted-earnings value? The test spec's `DCF`/`DDM` naming does **not** map 1:1 to the workbook's five methods. | Method-code registry |
| Q16 | Does the 11-method `calc_valuation_methods` requirement replace or extend the workbook's 5 methods? | Persistence shape |

### 18.3 Extraction gaps to close before implementation

| # | Item | Action |
|---|---|---|
| Q17 | `MetricsClassification!B83` (Confidence Level) full formula | Re-extract from workbook |
| Q18 | `FinancialHealth!B16` (debt vs profit growth) and `B17` (margin spike) numeric formulas | Re-extract from workbook |
| Q19 | `MetricsClassification!B6` (`Proj_Mode` / annual-vs-quarter mode switch) | Re-extract; `Proj_Mode` is `#REF!` |
| Q20 | `SUMMARY!B70` (manual IV method override) and `SUMMARY!E3` (manual price override) | Confirm they are intentionally blank |
| Q21 | Full `ValuationCurrent!D25:D29` status logic (`✅ UNDERVALUED` / `❌ OVERVALUED` / `⚪ N/A (Skip)`) | Re-extract; the consensus formula counts these exact strings |
| Q22 | `Backtest_Result` column semantics (27 columns, 0 formulas) | Decide whether to reproduce at all |

### 18.4 Summary classification counts

**Gap register (items needing a decision or a data source):**

| Class | Count | Meaning |
|---|---:|---|
| **A — directly replicable** | **14** | Straight reads from canonical PostgreSQL |
| **B — replicable with deterministic transformation** | **32** | Arithmetic / series aggregation |
| **C — requires external, manual, parameter, or projection input** | **9** | §8.1 register |
| **D — not currently defined / unresolved** | **13** | §8.2 register |

**Primary metrics (the 38 in §5.1):**

| Class | Count | Examples |
|---|---:|---|
| **A** | **1** | Gross Profit |
| **B** | **24** | EPS, BVPS (hist), PER, PBV, DPR, Yield, Market Cap, NWC, NWC/Rev, CR, CAGR, CoV, YoY, Asset Growth Gap, NWC Change, Yield Avg, Payout Avg, PER/PBV Avg, PBV Pct, IV Consensus, MoS, Liquidity, Business Quality, Strategic Target |
| **B/C** | **8** | BVPS (fwd), DER, PEG, Peter Lynch IV, Weighted IV, Mean-Reversion IV, Discounted Earnings IV, Ideal Price |
| **C** | **4** | EPS Annualized (Proj), DDM IV, Total Health Score, Market Mood |
| **D** | **0** | Gaps are input-level, not metric-level |

Both counts are reported because they answer different questions: the **metric**
counts say *what can be shipped*, the **gap** counts say *what needs a decision*.


---

## 19. Verification Log

Every numeric claim in this document was verified against the live database or the
workbook. Key independent reproductions:

| Claim | Method | Result |
|---|---|---|
| `Avg Vol (3M)` 2026-Q2 = `2449150.8474576273` | SQL `AVG(volume)` over the `EDATE` window | ✅ exact |
| 7 year-end prices (2020–2025) | SQL last-close-≤-Dec-31 | ✅ all exact |
| `revenue_cov = 0.15781626` | SQL `stddev_pop/avg` | ✅ exact |
| `payout_avg = 0.27277` | SQL incl. 2019 with `DPS = 0` | ✅ exact |
| `pe_avg = 6.38294` | SQL with `EPS > 0.25×AVG(EPS)` filter | ✅ exact |
| `pbv_avg = 0.67176` | SQL `AVG(price/BVPS)` | ✅ exact |
| `pbv_avg_5y = 0.71075` | SQL newest-5 average | ✅ exact |
| `iv_mean_reversion = 1740.2732` | SQL 20-quarter window, period-correct shares | ✅ exact |
| `iv_weighted = 2536.600` | Manual `(3049.773×1.5 + 2396.644×5.5)/7` | ✅ exact |
| `iv_ddm = 1418.19` | Manual Gordon growth | ✅ exact |
| `iv_disc_earnings = 2304.88` | Manual 5-yr compound + discount | ✅ exact |
| `health_score = 80` | Manual component sum `0+20+20+20+20+0` | ✅ exact |
| `business_quality = 2` → `0.7×` | Manual component sum | ✅ exact |
| `stock_type = CYCLICAL` | Manual rule evaluation | ✅ exact |
| `ideal_price = 2497.3933` | Manual `3567.7047 × 0.7` | ✅ exact |
| COGS stored **positive** | SQL sign distribution (`0` negative / `31` positive) | ✅ corrected Phase 3 |
| `EPS` / `BVPS` need **no ×1000** | Stored `EPS` vs derived | ✅ exact |

**Corrections to Phase 3 recorded here:**

1. §4.6 — COGS is stored **positive** in canonical PostgreSQL (Phase 3 §9.1 showed
   it negative).
2. §5.37 — `Business Quality` (Brand Power / GCG) is **formula-derived**, not
   "manual analyst input" as Phase 3 §11C stated.
3. §5.4 — `Avg Vol (3M)` was **exactly reproduced** from `prices_daily`, including
   the 3-calendar-month `EDATE` window.

**Phase 4 scope respected:** no calculation code, no `calc_*` table, no migration,
no frontend change, no canonical/raw data change. Only
`docs/PHASE4_CALCULATION_BLUEPRINT.md` was created.
