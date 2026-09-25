# Phase 4.1 — Registry & PIT Primitives Implementation Notes

**Phase:** 4.1 (first implementation after the Phase 4 blueprint)
**Status:** COMPLETE — registry + Layer-1 PIT primitives implemented and validated
**Scope:** additive only; no valuation methods, no `calc_*` result tables
**Blueprint:** `docs/PHASE4_CALCULATION_BLUEPRINT.md` (authoritative for methodology)
**Forward contract:** `Testing/test_calculation_v1.py`, `Testing/test_run_calculation_v1.py` (authoritative for schema/contracts)

> This document records what Phase 4.1 built, the exact source-to-field mappings,
> and the limitations that remain unresolved. It does not restate the blueprint
> and it does not modify the Phase 3 audit.

---

## 1. What Phase 4.1 delivers

| Deliverable | Status |
|---|---|
| A. Parameter & methodology registry (schema + seed + hashing) | ✅ |
| B. Layer-1 point-in-time primitives (price, year-end, AvgVol 3M, EDATE) | ✅ |
| Offline unit tests (70 assertions) | ✅ all pass |
| Live AUTO PIT integration validation | ✅ all pass |
| Documentation of unresolved limitations | ✅ this file |

Explicitly **not** delivered (deferred to Phase 4.2+):

- Peter Lynch / Type & Sector Weighted / Mean Reversion PBV / DDM /
  Discounted Earnings intrinsic values
- IV consensus, MoS, Ideal Price
- Growth, quality, balance-sheet, liquidity, classification calculations
- Projection engine
- Any `calc_*` result table

---

## 2. Files added

### 2.1 Python modules (`supabase/`)

| File | Role |
|---|---|
| `calculation_registry.py` | Canonical hashing contract: `canonical_json`, `sha256_text`, `sha256_json`, `input_hash`, `idempotency_key`, `methodology_hashes`, status/resolution vocabularies |
| `calculation_parameter_catalogue.py` | The 100-parameter catalogue + Excel `Reference` tables (weights, thresholds) |
| `calculation_methodology_registry.py` | The 9 methodology definitions + seed builder + the unresolved valuation-method mapping spec |
| `calculation_v1_common.py` | `CalculationError`, `SupabaseRest`, and re-exported hashing (the module path the test contract imports from) |
| `pit_primitives.py` | Layer-1 PIT primitives: `edate`, `as_of_price`, `year_end_price`, `avg_volume_3m`, `latest_price_date`, `normalize_prices` |
| `emit_calculation_v1_seed_sql.py` | Renders the 9 seed rows as SQL `VALUES` tuples |
| `render_calculation_v1_migration.py` | Keeps the migration seed block in sync with the registry (`--check` / `--write`) |
| `seed_calculation_registry.py` | Seeds and verifies the registry via PostgREST (`--dry-run` / `--write` / `--check`) |
| `build_pit_fixture.py` | Dumps the canonical AUTO prices into an offline test fixture |
| `validate_pit_primitives_live.py` | Live-database PIT validation (read-only) |

### 2.2 Migration

| File | Role |
|---|---|
| `supabase/migrations/0008_calculation_v1_batch.sql` | Additive registry schema + lineage guards + 9 methodology seeds |

### 2.3 Tests & fixture

| File | Role |

---

## 3. Schema created (additive)

The 12-table canonical baseline from `0001`–`0003` is unchanged. Phase 4.1 adds
**three registry tables** and **two nullable columns**.

| Object | Kind | Purpose |
|---|---|---|
| `public.methodology_versions` | new table | One row per `(method_code, method_version)`: formula text, `formula_hash`, `parameter_spec`, `parameter_hash`, `code_version`, `input_vocabulary_version`, `status` ∈ {`DRAFT`,`PUBLISHED`,`RETIRED`} |
| `public.calculation_parameters` | new table | One row per `(parameter_code, parameter_version)`: `parameter_value` (jsonb), `unit`, `resolution_status`, `source_reference`, `note`, `value_hash` |
| `public.calculation_runs` | new table | One row per execution: `input_hash`, unique `idempotency_key`, `input_snapshot`, `retry_of_run_id`, `status` ∈ {`QUEUED`,`RUNNING`,`SUCCEEDED`,`FAILED`,`PARTIAL`} |
| `financial_facts.supersedes_fact_id` | new nullable column | Lineage self-reference, guarded by `financial_facts_supersedes_not_self` |
| `dividend_facts.supersedes_dividend_fact_id` | new nullable column | Lineage self-reference, guarded by `dividend_facts_supersedes_not_self` |

**No `calc_*` result table was created.** Verified: `calc_tables = 0` before
Phase 4.1 and still `0` after (the two `calc*`-prefixed tables are
`calculation_parameters` and `calculation_runs`, which are registry tables
required by the contract, not valuation results).

**No canonical row was modified.** Verified after migration + seed:

| Table | Count | Before | After |
|---|---:|---:|---:|
| `companies` | 1 | 1 | 1 |
| `instruments` | 1 | 1 | 1 |
| `financial_periods` | 33 | 33 | 33 |
| `financial_facts` | 1.213 | 1.213 | 1.213 |
| `prices_daily` | 1.619 | 1.619 | 1.619 |
| `dividend_facts` | 16 | 16 | 16 |
| `ingestion_runs` | 62 | 62 | 62 |
| `ingestion_files` | 60 | 60 | 60 |
| lineage columns set | 0 | — | 0 |

---

## 4. Hashing contract (exact)

Two **different** hash rules exist and must not be conflated:

| Hash | Rule | Used for |
|---|---|---|
| `formula_hash` | `sha256(formula_text.encode('utf-8')).hexdigest()` | methodology formula identity |
| `parameter_hash` | `sha256(canonical_json(parameter_spec).encode('utf-8')).hexdigest()` | methodology parameter identity |
| `value_hash` | `sha256(canonical_json(parameter_value))` | per-parameter change detection |
| `input_hash` | `sha256(canonical_json(input_snapshot))` | run input identity |
| `idempotency_key` | `sha256(canonical_json({... run contract ...}))` | run deduplication |

`canonical_json(value)` = `json.dumps(value, sort_keys=True, separators=(',',':'), ensure_ascii=False)`.

Consequences that the tests assert:

1. Key order in a snapshot does **not** change its hash.
2. A JSON round trip does **not** change a hash.
3. The two rules coincide **only** when the formula text happens to equal the
   canonical JSON of the spec; otherwise they differ.
4. A retry (`retry_of_run_id` set) or a moved cutoff produces a **different**
   idempotency key, so a retry is a new run rather than a mutation.

### 4.1 Why parameter values are decimal strings

Every scalar numeric parameter is stored as its **exact decimal text**
(`'0.0633'`, not `0.0633`). This:

- preserves precision exactly (no binary-float artefacts),
- keeps `parameter_hash` stable across a JSON round trip,
- makes the stored value directly comparable to the Excel literal.

A test enforces this: no scalar parameter may be a JSON number.

---

## 5. Registry contents

| Metric | Value |
|---|---:|
| Parameters | **100** |
| Methodologies | **9** |
| Parameters flagged unresolved | **16** |
| Sector weight rows | 12 |
| Stock-type weight rows | 6 |
| Stock-type threshold rows | 6 |

### 5.1 Methodology codes

The 8 codes required by the forward test suite:

`QUARTERLY_GROWTH_QUALITY`, `DAILY_LIQUIDITY`, `BALANCE_SHEET_LIQUIDITY`,
`VALUATION_INPUTS`, `VALUATION_MULTIPLES`, `VALUATION_METHOD_PERSISTENCE`,
`CLASSIFICATION_DESCRIPTIVE`, `AVAILABILITY_REVISION`.

Plus the ninth row, `VALUATION_METHOD_MAPPING` — see §6.

### 5.2 Parameter groups

| Group | Count | Examples |
|---|---:|---|
| Core valuation (discount rates, target multiples) | 15 | `risk_free_rate`, `equity_risk_premium_ddm`, `target_per_by_type`, `target_pbv_by_mode`, `mean_reversion_min_quarters`, `pe_average_outlier_factor` |
| Aggregation & projection | 7 | `payout_trim_projection`, `years_compare_thresholds`, `negative_base_cagr_mode`, `projection_annualisation_factors` |
| Health score | 17 | `health_component_points`, `health_default_min_icr`, `health_ocf_penalty_severe`, `health_rating_bands` |
| Forensic flags | 4 | `forensic_asset_growth_gap_bands`, `forensic_debt_growth_gap_threshold` |
| Business quality | 6 | `quality_npm_bands`, `quality_multiplier_bands`, `quality_liquidity_tier_scores` |
| Stock-type classifier | 6 | `classifier_thresholds`, `classifier_score_ladder`, `classifier_energy_override` |
| Strategic targets | 7 | `mood_target_multipliers`, `ideal_price_discount`, `mos_entry_threshold_workbook` |
| Market mood | 4 | `market_mood_ihsg_vs_ma200`, `market_mood_bands` |
| Backtest | 5 | `backtest_horizons_months`, `backtest_thresholds_undervalued` |
| PIT gaps | 5 | `fundamental_available_date`, `quarterly_shares_outstanding`, `price_point_in_time` |
| Reference tables (expanded per row) | 24 | `sector_weight:*`, `type_weight:*`, `type_threshold:*` |

### 5.3 Units preserved

`ratio`, `multiple`, `count`, `integer_score`, `IDR`, `bn_IDR`, `text_enum`,
`expression`. Notable cases:

- Liquidity thresholds are `IDR` absolute values (`200000000000`), matching the
  workbook's numeric thresholds even though its labels say `M`.
- `quality_market_cap_bands` is `bn_IDR` (`10000`, `2000`), matching Excel's
  billion-IDR market cap.
- `target_per_by_type.FAST GROWER` is an `expression` (`growth_rate * 100 * 1.2`),
  not a scalar, because the workbook computes it.

|---|---|
| `Testing/test_phase_4_1_registry_and_pit.py` | 70 offline assertions (registry, hashing, migration contract, PIT primitives, AUTO validation) |
| `Testing/fixtures/auto_prices_daily.json` | 1.619 canonical AUTO price rows + expected values |

---

## 6. The unresolved valuation-method mapping

`Testing/test_run_calculation_v1.py` requires `calc_valuation_methods` to hold
**11** unique method codes and asserts that `DCF`, `DDM`, `GRAHAM` and
`RESIDUAL_INCOME` are persisted with `value_numeric = NULL` and
`method_status = 'UNAVAILABLE'`.

The workbook computes exactly **five** methods:

1. Peter Lynch Algo IV
2. Type & Sector Weighted IV
3. Mean Reversion PBV IV
4. Dividend Discount Model IV
5. Discounted Earnings Model IV

These sets do **not** map one-to-one. The test suite names only **7** of the 11
codes it requires, so **4 remain unidentified**.

Rather than force a false mapping, `VALUATION_METHOD_MAPPING` records the
mismatch machine-readably:

| Field | Value |
|---|---|
| `resolution_status` | `UNRESOLVED_DEFINITION` |
| `workbook_methods` | the 5 above |
| `workbook_method_count` | `5` |
| `test_suite_method_count_required` | `11` |
| `test_suite_named_method_codes` | 7 codes |
| `test_suite_named_method_count` | `7` |
| `test_suite_enumerated_codes_incomplete` | `true` |
| `confirmed_mapping` | `{Dividend Discount Model IV: DDM}` |
| `approximate_mapping` | `{Discounted Earnings Model IV: DCF}` |
| `workbook_methods_without_test_code` | Peter Lynch Algo IV, Type & Sector Weighted IV, Mean Reversion PBV IV |
| `test_codes_without_workbook_method` | `GRAHAM`, `RESIDUAL_INCOME` |

**This must be settled by a product decision before `calc_valuation_methods` is
populated.** Do not force a 1:1 mapping.

---

## 7. Layer-1 PIT primitives — exact mapping

### 7.1 `as_of_price(prices, as_of_date)`

| Aspect | Detail |
|---|---|
| Workbook source | `Stock_Database!N` and `Stock_Database_Quarter!P` backward `XLOOKUP` |
| Rule | last `close_price` with `trading_date <= as_of_date` |
| Returns | `Decimal` or `None` when no row qualifies |
| PIT guarantee | rows after `as_of_date` are never considered |
| NULL handling | a row with NULL close is skipped in favour of the most recent row that has one |

### 7.2 `year_end_price(prices, year)`

| Aspect | Detail |
|---|---|
| Workbook source | `Stock_Database!N` with `asof = DATE(year, 12, 31)` |
| Rule | `as_of_price(prices, YYYY-12-31)` |
| Why it matters | 31-Dec is a market holiday most years, so the result is normally 29-Dec or 30-Dec. A naive `trading_date = 'YYYY-12-31'` filter returns nothing. |

### 7.3 `avg_volume_3m(prices, as_of_date)`

| Aspect | Detail |
|---|---|
| Workbook source | `Stock_Database_Quarter!O` `AVERAGEIFS` |
| Rule | mean of `volume` over `[EDATE(as_of, -3), as_of]`, **inclusive both ends** |
| Not | a 63-trading-day window |
| Missing days | not imputed; the mean is over rows that exist |
| Returns | `Decimal` or `None` when the window has no volume |

### 7.4 `edate(start, months)`

Reproduces Excel `EDATE`, including **month-end clamping**:
`EDATE(2026-05-31, -3) == 2026-02-28` (2026 is not a leap year) while
`EDATE(2024-05-31, -3) == 2024-02-29`.

### 7.5 `latest_price_date(prices)`

Returns the true data edge. Provided so callers can report it **without**
accidentally using it as a valuation as-of price.

---

## 8. Unit rules honoured

| Rule | Implementation |
|---|---|
| Canonical financial values are IDR | No conversion is applied anywhere in Phase 4.1 |
| Excel `(M Rp)` is a presentation transformation | Not applied; documented only |
| Canonical `OUTSTANDING_SHARES` is a raw share count | No `×1000` factor exists in any Phase 4.1 code path |
| Prices are IDR per share | `close_price` passed through unchanged |
| Volume is share volume | `volume` passed through unchanged |
| Never apply Excel's `×1000` EPS/BVPS multiplier | No EPS/BVPS computation exists yet; the rule is recorded in the registry note and the blueprint |
| All PIT calculations respect the requested as-of date | Enforced by `as_of_price` / `avg_volume_3m` |

### 8.1 COGS sign

The blueprint (§4.6) corrects the Phase 3 audit: canonical
`COST_OF_REVENUE` is stored **positive** (`+16.540.549.000.000` for 2025), and
`GROSS_PROFIT` is stored directly. Phase 4.1 does not compute gross profit, so
no arithmetic is affected yet. The rule is recorded here so Phase 4.2 uses
`revenue − cost_of_revenue` (or the stored `GROSS_PROFIT`) and never reproduces
Excel's negative-feed addition.

---

## 9. Point-in-time and fundamental availability

### 9.1 Price PIT — solved

`prices_daily` is 100% populated for `trading_date`, `close_price` and `volume`
(1.619 rows, 2020-01-02 → 2026-09-24). Price PIT is therefore reliable and is
validated live.

### 9.2 Fundamental PIT — explicitly NOT solved

| Field | State | Consequence |
|---|---|---|
| `financial_periods.available_date` | NULL for all 33 periods | Fundamental PIT cannot be enforced |
| `financial_periods.report_date` | NULL for all 33 periods | Same |
| `financial_periods.statement_scope` | `UNKNOWN` for all 33 | Consolidated vs standalone unverifiable |
| `financial_periods.period_basis` | `UNKNOWN` (annual), `STANDALONE` (quarter) | Annual basis unknown |

Phase 4.1 deliberately:

- does **not** fabricate availability dates,
- does **not** substitute an ingestion timestamp (the blueprint forbids it),
- records the gap as three `MISSING_INPUT` parameters
  (`fundamental_available_date`, `fundamental_report_date`,
  `fundamental_statement_scope`),
- keeps the `AVAILABILITY_REVISION` methodology's `parameter_spec` carrying
  `null` for those keys, so the gap is visible in the seeded registry.

The forward contract expects a `POINT_IN_TIME_UNSAFE` flag for this condition;
emitting that flag belongs to the `AVAILABILITY_REVISION` calculation phase.

### 9.3 Quarterly shares

`OUTSTANDING_SHARES` exists for **7 annual periods only**. The blueprint showed
that Mean-Reversion PBV IV matches Excel exactly only with period-correct
quarterly shares. Recorded as `quarterly_shares_outstanding`
(`MISSING_INPUT`) under `BALANCE_SHEET_LIQUIDITY`.


---

## 10. Validation results

### 10.1 Offline unit tests

```
python -m unittest Testing.test_phase_4_1_registry_and_pit
Ran 70 tests
OK
```

Coverage: canonical hashing (8), parameter catalogue (11), methodology registry
(7), migration contract (9), EDATE (5), price normalisation (4), as-of price (7),
AvgVol 3M (5), year-end price (3), latest price date (2), AUTO validation (9).

### 10.2 Mandatory AUTO PIT validation

| Check | Result |
|---|---|
| Seven year-end prices | ✅ 2019 `None`, 2020 `1115`, 2021 `1155`, 2022 `1460`, 2023 `2360`, 2024 `2300`, 2025 `2690` |
| `avg_volume_3m('2026-06-30')` | ✅ `2449150.847457627118644067797` → float **`2449150.8474576273`** |
| Exact rational form | ✅ `144499900 / 59` |
| Window boundary | ✅ `EDATE(2026-06-30,-3) = 2026-03-30`, 59 rows, total volume `144499900` |
| No globally-latest fallback | ✅ as-of `2026-06-30` → `2350`; latest `2026-09-24` → `3340` |
| Historical leak check | ✅ 7 cutoffs, **0 leaks** |
| Determinism | ✅ repeated runs identical |

### 10.3 Live-database integration validation

```
python supabase/validate_pit_primitives_live.py AUTO
RESULT: OK - all live PIT validations passed
```

### 10.4 Registry seeding

```
python supabase/seed_calculation_registry.py --write
methodologies written: 9
parameters written   : 100
post-write verification: OK
```

A re-run produced identical hashes and `0` drift, proving idempotency.
`--check` reports `registry check: OK`.

### 10.5 Migration rendering

```
python supabase/render_calculation_v1_migration.py --check
exit 0
```

The migration's seed block is byte-identical to the registry, so the migration
and the Python catalogue cannot drift.

---

## 11. Deferred items (explicit)

| Item | Why deferred | Where it belongs |
|---|---|---|
| `calculation_contract`, `growth_result`, `ratio_result` | Inputs and status semantics depend on the growth/quality phase. Defining them now would be silent invention. | Phase 4.2 (growth/quality) |
| All five intrinsic-value methods | Explicitly excluded by the Phase 4.1 brief | Phase 4.3+ (valuation) |
| IV consensus, MoS, Ideal Price | Depend on the IV methods | Phase 4.3+ |
| Projection engine | Depends on as-of quarter selection, which needs `available_date` | Phase 4.2 |
| `calc_*` result tables | Not required for a registry-only phase | Phase 4.2+ |
| `AVAILABILITY_REVISION` audit output | Needs the calculation-result layer | Phase 4.2 |


---

## 12. Unresolved gaps carried forward

All 16 unresolved parameters are recorded in `calculation_parameters` with a
non-`RESOLVED` status. Grouped by cause:

**No data source (`UNRESOLVED_SOURCE`) — 4**

| Parameter | Blocks |
|---|---|
| `risk_free_rate` (`0.0633` preserved verbatim) | DDM IV, Discounted Earnings IV |
| `market_mood_ihsg_vs_ma200` | Market Mood, market-adjusted target |
| `market_mood_foreign_flow` | Market Mood |
| `market_mood_bi_rate` | Market Mood |

**Missing canonical input (`MISSING_INPUT`) — 4**

| Parameter | Blocks |
|---|---|
| `fundamental_available_date` | Fundamental PIT correctness |
| `fundamental_report_date` | Fundamental PIT correctness |
| `fundamental_statement_scope` | Scope flags |
| `quarterly_shares_outstanding` | Exact Mean-Reversion PBV IV |

**Definition undecided (`UNRESOLVED_DEFINITION`) — 8**

| Parameter | Conflict |
|---|---|
| `health_default_min_icr` | Workbook references a non-existent `Min ICR` column |
| `forensic_debt_growth_gap_threshold` | Formula not extractable from the workbook |
| `forensic_margin_spike_threshold` | Formula not extractable |
| `classifier_confidence_level` | `B83` LET block only partially extractable |
| `mos_entry_threshold_workbook` | `35%` vs `30%` (frontend) |
| `mos_entry_threshold_frontend` | Same conflict, other side |
| `iv_consensus_denominator_mode` | valid-methods vs total-methods denominator |
| `backtest_generation_rule` | Workbook sheet has 0 formulas |

`BROKEN_REFERENCE`: **0**. The workbook's `#REF!` names (`Param_Growth`,
`Param_Price`, `Proj_Mode`, `Calc_Method`) are documented in the blueprint, but
no Phase 4.1 parameter depends on them.

### 12.1 Decisions needed before Phase 4.2

1. Which `Template\*.xlsm` is the production master?
2. Will `financial_periods.available_date` / `report_date` be populated?
3. Will quarterly `OUTSTANDING_SHARES` be ingested?
4. Where does the risk-free rate come from?
5. MoS entry threshold: 35% or 30%?
6. Liquidity: 3-calendar-month average (workbook) or 20-day rolling (test suite)?
7. IV consensus denominator: valid or total?
8. The 5-to-11 valuation method mapping (§6).

---

## 13. How to run everything

```powershell
# Offline tests (no network, no credentials)
python -m unittest Testing.test_phase_4_1_registry_and_pit

# Registry dry run (no network)
cd supabase; python seed_calculation_registry.py --dry-run

# Migration / registry drift check
cd supabase; python render_calculation_v1_migration.py --check

# Live seeding + verification (requires credentials)
$env:SUPABASE_URL='...'; $env:SUPABASE_SERVICE_ROLE_KEY='...'
cd supabase; python seed_calculation_registry.py --write
cd supabase; python seed_calculation_registry.py --check

# Live PIT validation (read-only)
cd supabase; python validate_pit_primitives_live.py AUTO

# Rebuild the offline fixture after a price refresh
cd supabase; python build_pit_fixture.py AUTO
```

---

## 14. Phase 4.1 scope compliance

| Constraint | Status |
|---|---|
| No valuation methods implemented | ✅ none |
| `frontend/**` unmodified | ✅ |
| `frontend/src/lib/analysis/**` unmodified | ✅ |
| `Phyton/01_download_sectors.py` unmodified | ✅ |
| `Phyton/02_convert_sectors_raw.py` unmodified | ✅ |
| `docs/EXCEL_POSTGRES_VALIDATION.md` unmodified | ✅ |
| No existing baseline migration modified | ✅ `0001`–`0003` byte-identical |
| No canonical row modified | ✅ all counts unchanged |
| No `calc_*` result table created | ✅ |
| Raw ingestion state unchanged | ✅ 62 runs / 60 files |
| Workbook defects not silently fixed | ✅ `Stock_Database!O` defect documented; the PIT primitive models the correct quarterly formula |

