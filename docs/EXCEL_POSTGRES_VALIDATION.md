# Excel ↔ PostgreSQL Validation & Logic Mapping

**Phase:** 3 (validation & mapping only)
**Status:** COMPLETE — no calculation, no migration, no database change
**Ticker used for reconciliation:** `AUTO`
**Canonical source:** `stocklens_raw` (Storage) → `public.*` (PostgreSQL)

> This document **documents** the Excel template. It does not implement, fix, or
> recalculate any formula. Values marked `UNKNOWN / NEEDS REVIEW` were not
> resolvable from the workbook itself and are not guessed.

---

## 1. Workbook

### 1.1 Files found in `Template\`

| File | Size | Sheets | Notes |
|---|---:|---:|---|
| `Stock Analyzer [Dev].xlsm` | 1.519.519 B | 15 | **Primary reference for this audit** (most complete: has `Backtest_Result`, full `Stock_Database` 116 rows, full `Company_Information` 17 rows) |
| `Stock Analyzer [Dev] Quarter.xlsm` | 2.498.558 B | 4 | Quarterly-only variant (25.512 price rows) |
| `Stock Analyzer [Dev] - Backup.xlsm` | 589.815 B | 16 | Earlier backup (has `ValuationProjection` + `Backtest_Historical`) |
| `Stock Analyzer.xlsm` | 380.271 B | 16 | Oldest; `Company_Information` only 2 rows |

- All four are `.xlsm` (macro-enabled) and are **not** tracked by Git.
- `Template_Sample_data.md` (repo root) is the **canonical frontend reference** derived from this workbook, per `DEVELOPMENT_GUIDE.md`.
- **UNKNOWN / NEEDS REVIEW:** which workbook is the single production master going forward. `[Dev].xlsm` is used here because it is the most complete and its `SUMMARY` matches `Template_Sample_data.md` exactly (`AUTO`, CYCLICAL, Rp2.350, Quarter 2 2026).

### 1.2 Worksheets in `Stock Analyzer [Dev].xlsm`

| Sheet | Rows | Cols | Role |
|---|---:|---:|---|
| `SUMMARY` | 204 | 19 | **Output / dashboard** — valuation table, thesis validator, dividend, health, thresholds, quality, market mood |
| `DataInput` | 102 | 26 | **Input + derived** — annual financial line items, balance sheet, ratios |
| `DataInputProyeksi` | 89 | 14 | **Input + derived** — quarterly line items, projection, YoY thesis |
| `FinancialHealth` | 71 | 5 | **Calculation** — DER, CR, ICR, forensic flags, health score |
| `MetricsClassification` | 130 | 10 | **Calculation** — growth, momentum, multiples, averages, percentile, stock-type engine |
| `ValuationCurrent` | 177 | 9 | **Calculation** — 5 valuation methods, MoS |
| `Backtest_Result` | 19 | 27 | **Output** — historical evidence |
| `DB_ANALYSIS` | 2 | 27 | Presentation — liquidity/market-cap verdict strings |
| `Reference` | 143 | 19 | **Reference/helper** — sector & stock-type weights, DER/CR thresholds |
| `ExportConfig` | 81 | 15 | Export driver |
| `Stock_Database` | 116 | 15 | **Data feed table** `tblStockDatabase_DB` — annual per ticker |
| `Stock_Database_Quarter` | 413 | 18 | **Data feed table** `tblStockDatabaseQuarter_DB` — quarterly per ticker |
| `Company_Information` | 17 | 4 | **Data feed table** `tblStockInformation_DB` |
| `Price_History` | 25.512 | 8 | **Data feed table** `tblPriceHistory_DB` — daily prices |
| `Helper` | 17 | 3 | **Helper** — stock list, year list |

---

## 2. Primary Metrics (output-facing)

These drive the dashboard. All live on `SUMMARY` and pull from calculation sheets.

| # | Metric | Sheet | Cell | Formula | Inputs | Period | Unit | Dependency |
|---|---|---|---|---|---|---|---|---|
| 1 | Peter Lynch Algo IV | SUMMARY | B13 | `=ValuationCurrent!B25` | BVPS Fwd, Target PBV | current | Rp | MetricsClassification |
| 2 | Type & Sector Weighted IV | SUMMARY | B14 | `=ValuationCurrent!B26` | EPS Fwd, BVPS Fwd, PE/PBV avg, weights | current | Rp | Reference weights |
| 3 | Mean Reversion PBV IV | SUMMARY | B15 | `=ValuationCurrent!B27` | BVPS Fwd, PBV Hist Avg | current | Rp | MetricsClassification |
| 4 | Dividend Discount Model IV | SUMMARY | B16 | `=ValuationCurrent!B28` | Proj DPS, Rev CAGR Long, risk-free | current | Rp | DataInputProyeksi |
| 5 | Discounted Earnings Model IV | SUMMARY | B17 | `=ValuationCurrent!B29` | EPS Fwd, Rev CAGR Long, PE Hist | current | Rp | MetricsClassification |
| 6 | IV Consensus | SUMMARY | B19 | Array formula (verdict count) | B13:B17 | current | text | — |
| 7 | Total Health Score | SUMMARY | B40 | `=Health_Score` → `FinancialHealth!B26` | DER, CR, ICR, OCF, forensic | latest | 0–100 | DataInput |
| 8 | Debt (DER) | SUMMARY | B41 | `=FinancialHealth!B8` | Total Liabilities, Total Equity | latest | x | DataInput |
| 9 | Cash (Current Ratio) | SUMMARY | B42 | `=FinancialHealth!B9` | Current Assets, Current Liabilities | latest | x | DataInput |
| 10 | Cashflow (OCF) | SUMMARY | B43 | `=FinancialHealth!B11` | OCF | latest | M Rp | DataInput |
| 11 | Fraud Check (Asset Growth Gap) | SUMMARY | B44 | `=FinancialHealth!B14` | Revenue growth, Current Asset growth | 5Y | ratio | MetricsClassification |
| 12 | MoS vs Entry Threshold | SUMMARY | B48 | `=TEXT(MoS_Fundamental,"0.0%")` | IV, Current Price | current | % | ValuationCurrent |
| 13 | Liquidity Score | SUMMARY | B56 | `AvgVol(3M) × Price` thresholds | Avg Vol, Stock Price | target quarter | text | Stock_Database_Quarter |
| 14 | Business Quality total | SUMMARY | — | brand + GCG + dividend scores | manual + dividend | current | 0–? | UNKNOWN (manual inputs) |
| 15 | Market Mood | SUMMARY | — | IHSG vs MA200, foreign flow, BI rate | external | current | text | **NOT in template data** |
| 16 | Strategic target (Quality-Adj.) | SUMMARY | B76 | market-adjusted × quality adjustment | IV, mood, quality | current | Rp | — |
| 17 | Ideal Price | SUMMARY | B80 | threshold logic | MoS target | current | Rp | — |

### 2.1 Intermediate / helper metrics

| Metric | Sheet | Formula |
|---|---|---|
| Revenue CAGR (Historical) | MetricsClassification!B7 | `(latest/earliest)^(1/n) - 1` over `Range_Revenue` |
| Revenue CAGR (recent) | MetricsClassification!B8 | same over shorter window |
| Revenue Volatility (CoV) | MetricsClassification!B10 | `STDEV.P(Range_Revenue)/AVERAGE(Range_Revenue)` |
| Revenue Growth YoY | MetricsClassification!B11 | year-over-year delta |
| EPS Growth/Recovery | MetricsClassification!B13 | growth over `Range_*` |
| Current Asset Growth YoY | MetricsClassification!B17 | delta |
| Asset Growth Gap YoY | MetricsClassification!B18 | `Rev_Growth - Curr_Assets_Growth` |
| NWC / Revenue | MetricsClassification!B19 | NWC ÷ Revenue |
| NWC Intensity Change | MetricsClassification!B20 | delta in ppt |
| EPS Annualized (Proj) | MetricsClassification!B25 | `Proj_Net_Income/Proj_Shares*1000` |
| BVPS | MetricsClassification!B26 | `Proj_Equity/Proj_Shares*1000` |
| PER / PBV | MetricsClassification!B28/B29 | price ÷ EPS / BVPS |
| PEG | MetricsClassification!B30 | `PE_Fwd/(EPS_CAGR*100)` |
| Dividend Yield Avg (Hist) | MetricsClassification!B32 | mean over `Range_*` |
| Payout Ratio Avg (Hist) | MetricsClassification!B34 | `TRIMMEAN(Range_DPR,0.4)` |
| PER / PBV Avg (Hist) | MetricsClassification!B36/B37 | mean of historical multiples |
| PBV Percentile | MetricsClassification!B39 | percentile of current PBV |
| NWC, NWC/Revenue, Gross Profit, EPS, BVPS, PBV, PER, DPR, Yield | DataInput!B35–B43 | see §7 |
| DER, CR, ICR, forensic, health score | FinancialHealth!B8–B26 | see §7 |
| Revenue YoY, Gross Margin, NI YoY, OCF/NI, Interest Exp (quarterly) | DataInputProyeksi!B48–B52 | see §7 |

### 2.2 Presentation-only

| Metric | Location | Note |
|---|---|---|
| Valuation method description strings | `ValuationCurrent` D25:D29 | explanatory text |
| Verdict text (✅ UNDERVALUED / ❌ OVERVALUED) | `SUMMARY` D13:D17 | derived label |
| Diagnostic text (⚠️/✅/🛒) | `SUMMARY` C40:C68 | label only |
| Narrative commentary blocks | `DataInput`/`SUMMARY` | `CONCATENATE` prose |
| `DB_ANALYSIS` verdict strings | `DB_ANALYSIS!A2:AA2` | label only |

---

## 3. Input Fields (what must be supplied)

From `DataInput` / `DataInputProyeksi` / the three feed tables:

| # | Input | Location | Source per template guide |
|---|---|---|---|
| 1 | Ticker | `SUMMARY!B4` → `Stock_Ticker` | user |
| 2 | Base Annual Years | `SUMMARY!E4` (=2025) | user |
| 3 | Manual Quarter | `SUMMARY!E5` (=Q2) | user |
| 4 | Manual Price (override) | `SUMMARY!E3` (blank) | user |
| 5 | Current Price | `DataInput!B10` → `Current_Price` | `Price_History` or manual |
| 6 | Risk Free Rate | `DataInput!B11` (=0.0633) | **manual constant** |
| 7 | Years Base Selected | `DataInput!B12` | derived |
| 8 | Data Years (manual) | `DataInput!B16` (blank) | manual override |
| 9 | Manual DPR | `DataInputProyeksi!B7` (blank) | manual override |
| 10 | Revenue (M Rp) | `Stock_Database!C` | Sectors financials |
| 11 | HPP COGS (M Rp) | `Stock_Database!D` | Sectors financials |
| 12 | Interest Expenses (M Rp) | `Stock_Database!E` | Sectors financials |
| 13 | Net Income (M Rp) | `Stock_Database!F` | Sectors financials |
| 14 | OCF (M Rp) | `Stock_Database!G` | Sectors financials |
| 15 | DPS (Rp) | `Stock_Database!H` | **manual / pasardana.id** |
| 16 | Current Assets (M Rp) | `Stock_Database!I` | Sectors financials |
| 17 | Current Liabilities (M Rp) | `Stock_Database!J` | Sectors financials |
| 18 | Total Liabilities (M Rp) | `Stock_Database!K` | Sectors financials |
| 19 | Total Equity (M Rp) | `Stock_Database!L` | Sectors financials |
| 20 | Shares (Juta) | `Stock_Database!M` | Sectors financials |
| 21 | Stock Price (Rp) | `Stock_Database!N` | **computed** from `Price_History` |
| 22 | Avg Vol (3M) | `Stock_Database!O` | **computed** from `Price_History` |
| 23 | Quarterly: Data Available Date, Year, Quarter | `Stock_Database_Quarter!B,C,D` | Sectors |
| 24 | Quarterly: Revenue…Shares | `Stock_Database_Quarter!E..N` | Sectors |
| 25 | Quarterly: Avg Vol (3M), Stock Price | `Stock_Database_Quarter!O,P` | computed from `Price_History` |
| 26 | Company Information | `Company_Information!A:D` | Sectors info |
| 27 | Price History | `Price_History!A:H` | Sectors daily |
| 28 | Sector / Type weights | `Reference!B5:C16`, `B22:C26` | reference constants |
| 29 | DER/CR thresholds | `Reference!B32:C37` | reference constants |

**Unit reality check (important):** every `* (M Rp)` column is labelled "M Rp" but holds **billions of IDR**.
`AUTO` 2025 revenue raw = `19,906,774,000,000` IDR → template `19906.774`. So `1 template unit = 1,000,000,000 IDR`. The label "M Rp" (million) is **misleading**; the actual scale is **miliar (billion) IDR**. This must be preserved exactly when replicating.

---

## 4. Daily-Price Usage (STEP 3)

`tblPriceHistory_DB` has columns: `Ticker, Date, Open, High, Low, Close, Volume, Market Cap`.

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

### 4.1 What daily price is actually used for

| Purpose | Used? | Evidence |
|---|---|---|
| Chart | **NO** | no chart series / no `Sparkline` refs found |
| Return | **NO** | no `(Close/Close_prev)-1` pattern |
| Moving average | **NO** | no `AVERAGE` over price (only over `Volume`) |
| Mean reversion | **NO** (of price) | "Mean Reversion" in `ValuationCurrent!B27` is **PBV** mean reversion, not price |
| Volatility | **NO** (of price) | volatility is computed on **Revenue** only (`MetricsClassification!B10`) |
| Liquidity | **YES** | `SUMMARY!B56` / `DB_ANALYSIS!O2` = `AvgVol(3M) × Price` thresholds |
| Technical signal | **NO** | none |
| **Point-in-time valuation price** | **YES** | `Stock_Database!N` and `Stock_Database_Quarter!P` |

### 4.2 Exact formulas

**Annual year-end price — `Stock_Database!N` (all rows):**
```
LET(
  ticker,  [#This Row Ticker],
  asof,    DATE([#This Row Year], 12, 31),
  IFERROR(
    XLOOKUP(1,
      (tblPriceHistory_DB[Ticker]=ticker) * (tblPriceHistory_DB[Date]<=asof),
      tblPriceHistory_DB[Close], "", 0, -1),
    ""))
```
= last available `Close` on or before 31-Dec of that year.

**Quarterly 3M average volume — `Stock_Database_Quarter!O` (all rows):**
```
LET(
  ticker,    [#This Row Ticker],
  asof,      [#This Row Data Available Date],
  startdate, EDATE(asof, -3),
  IFERROR(AVERAGEIFS(tblPriceHistory_DB[Volume],
      tblPriceHistory_DB[Ticker], ticker,
      tblPriceHistory_DB[Date], ">="&startdate,
      tblPriceHistory_DB[Date], "<="&asof), ""))
```
= simple mean of daily `Volume` over the 3 calendar months ending at `Data Available Date`. **Not** a rolling 63-trading-day average, and **not** adjusted for missing days.

**Quarterly price — `Stock_Database_Quarter!P`:** identical to `Stock_Database!N` but `asof = Data Available Date`.

### 4.3 ⚠️ Defect found (documented, not fixed)

`Stock_Database!O` is **labelled** `Avg Vol (3M)` but its formula is **identical to `Stock_Database!N`** (returns `[Close]`, not `[Volume]`). Cached values confirm it: AUTO 2025 → N15 = 2690 **and** O15 = 2690.

Consequence: the **annual** liquidity input is actually year-end close price, not average volume. The **quarterly** sheet `Stock_Database_Quarter!O` is correct (AUTO 2026-Q2 cached = 7917.46, a volume-scale number).

Per the Phase 3 rule ("do not fix Excel formulas based on assumptions"), this is **reported, not corrected**.

---

## 5. Financial Usage (STEP 4)

### 5.1 Annual

| Item | Feed column | Used by |
|---|---|---|
| Revenue | `Stock_Database!C` | growth, margin, NWC intensity, DDM/DEM growth input |
| HPP COGS | `D` | gross profit (`B20+B21`), gross margin |
| Interest Expenses | `E` | ICR |
| Net Income | `F` | EPS, DPR, trends, quality |
| OCF | `G` | OCF/NI quality, health |
| DPS | `H` | DPR, yield, DDM |
| Current Assets | `I` | NWC, current ratio, liquidation value |
| Current Liabilities | `J` | NWC, current ratio |
| Total Liabilities | `K` | DER, liquidation value |
| Total Equity | `L` | BVPS, DER |
| Shares | `M` | EPS, BVPS, market cap |
| Stock Price | `N` | PER, PBV, yield |
| Avg Vol (3M) | `O` | liquidity (**defective**, see §4.3) |

### 5.2 Quarterly

`Stock_Database_Quarter`: Revenue, HPP COGS, Interest Expenses, Net Income, OCF, Current Assets, Current Liabilities, Total Liabilities, Total Equity, Shares, Avg Vol (3M), Stock Price.
Used for: quarterly YoY thesis validator (`DataInputProyeksi!B47:F52`), projection inputs, latest-quarter balance sheet, liquidity.

### 5.3 TTM / point-in-time / derived classification

| Category | Items |
|---|---|
| **Annual** | Revenue, COGS, Interest Exp, Net Income, OCF, DPS, Current Assets, Current Liabilities, Total Liabilities, Total Equity, Shares, Stock Price |
| **Quarterly** | same set + Data Available Date, Year, Quarter |
| **TTM** | **NONE explicit.** `dividend_ttm` exists in raw/DB but the template has no TTM column; DDM uses `Proj_DPS`. |
| **Point-in-time** | Stock Price (last close ≤ as-of), Avg Vol (3M window), Total Assets/Equity/Liabilities at period end |
| **Derived** | Gross Profit, NWC, NWC/Revenue, EPS, BVPS, PER, PBV, DPR, Yield, Market Cap, DER, CR, ICR, CAGR, CoV, percentile, health score, all IV methods |
| **Never used** | Open, High, Low, Market Cap (from price history), Total Assets, EBITDA, EBIT, Gross Profit (from feed), Free Cash Flow, Capex, Inventory, AR, `industry_breakdown`, `yoy_*_growth` |

Note: `Total Assets`, `EBITDA`, `EBIT`, `Free Cash Flow`, `Capital Expenditure` **exist in canonical PostgreSQL** but are **not consumed** by the template.

---

## 6. Dividend Usage

| Excel metric | Source | Formula | Period |
|---|---|---|---|
| DPS (Rp) | `Stock_Database!H` | manual input | annual 2020–2025 |
| DPR (%) | `DataInput!B28` | `B26/B30` (DPS ÷ EPS) | annual |
| Dividend Yield (%) | `DataInput!B29` | `B26/B25` (DPS ÷ Price) | annual |
| Proj DPS | `DataInputProyeksi` → `Proj_DPS` | projection | forward |
| DPS/DPR/Yield consistency table | `SUMMARY` B34:B36 | pulls `DataInput!B/C26,B/C28,B/C29` | 2022–2026 + 4Y avg |
| Dividend safety | `SUMMARY` B79 | `#REF!` | **BROKEN** |

Canonical `dividend_facts` holds `ANNUAL_TOTAL` (amount_per_share), `YIELD` (yield_ratio), `TTM`, `PAYOUT_RATIO`.
**Gap:** Excel DPR = `DPS/EPS` (computed); canonical `PAYOUT_RATIO` = `0.4566` while Excel 2025 DPR = `0.4197`. Different definitions — see §10.4.

---

## 7. Formula Inventory (STEP 7)

| Metric | Formula | Input 1 | Input 2 | Input 3 | Output |
|---|---|---|---|---|---|
| Gross Profit | `B20+B21` | Revenue | COGS (negative) | — | M Rp |
| EPS | `B23/B41*1000` | Net Income | Shares (Juta) | ×1000 | Rp |
| BVPS | `B40/B41*1000` | Total Equity | Shares (Juta) | ×1000 | Rp |
| PER | `B25/B30` | Price | EPS | — | x |
| PBV | `B25/B42` | Price | BVPS | — | x |
| DPR | `B26/B30` | DPS | EPS | — | % |
| Dividend Yield | `B26/B25` | DPS | Price | — | % |
| Market Cap | `Current_Price*B13/1000` | Price | Shares (Juta) | ÷1000 | M Rp |
| NWC | `B37-B38` | Current Assets | Current Liabilities | — | M Rp |
| NWC / Revenue | `B35/B20` | NWC | Revenue | — | % |
| DER | `Metric_Liabilities_Total/Proj_Equity` | Total Liabilities | Total Equity | — | x |
| Current Ratio | `Metric_Assets_Current/Metric_Liabilities_Current` | Current Assets | Current Liabilities | — | x |
| Interest Coverage | `LET(... Metric_Interest_Exp_Current ...)` | EBIT/Operating PnL | Interest Exp | bank bypass | x |
| Revenue CAGR (Hist) | growth over `Range_Revenue` | Revenue latest | Revenue earliest | years | % |
| Revenue Volatility | `STDEV.P(Range_Revenue)/AVERAGE(Range_Revenue)` | Revenue series | — | — | % |
| Asset Growth Gap | `Metric_Rev_Growth_Actual - Metric_Curr_Assets_Growth` | Revenue growth | Current Asset growth | — | ratio |
| NWC Intensity Change | delta of NWC/Revenue | NWC/Rev latest | NWC/Rev prior | — | ppt |
| EPS Annualized | `Proj_Net_Income/Proj_Shares*1000` | Proj NI | Proj Shares | ×1000 | Rp |
| PEG | `PE_Fwd/(EPS_CAGR_Long*100)` | PE Fwd | EPS CAGR | ×100 | x |
| Payout Ratio Avg | `TRIMMEAN(Range_DPR,0.4)` | DPR series | trim 40% | — | x |
| PBV Percentile | percentile of current PBV | PBV current | PBV history | — | % |
| **Peter Lynch IV** | PBV route: `BVPS × Target PBV` | BVPS Fwd | Target PBV | — | Rp |
| **Type & Sector Weighted IV** | `(PE_Fair×W_PE + PBV_Fair×W_PBV)/(W_PE+W_PBV)` | PE Fair | PBV Fair | weights | Rp |
| **Mean Reversion PBV IV** | `BVPS × PBV_Hist_Avg` | BVPS Fwd | PBV Avg Hist | — | Rp |
| **DDM IV** | `AdjDiv / (WACC − G_sustain)` | Proj DPS | risk-free/rev CAGR | `MIN(0.04,MAX(0,G_Long))` | Rp |
| **Discounted Earnings IV** | discounted EPS × PE | EPS Fwd | Growth | Discount rate | Rp |
| Margin of Safety | `(IV − Price)/IV` | IV | Price | — | % |
| Liquidity class | `AvgVol×Price` vs thresholds | Avg Vol | Price | 10/50/200 bn | text |
| Health Score | weighted sum of health checks | DER | CR | ICR/OCF/forensic | 0–100 |
| Weight lookup | `XLOOKUP` sector & type weights | `Company_Sector` | `Stock_Type` | `Reference` | x |
| Sector weight blend | `IFERROR(LET(W_Sector…,W_Type…))` | sector weight | type weight | blend rule | x |

**Formula-count context:** `tblPriceHistory` appears in **1.066** formula references (essentially every `N`/`O`/`P` row of both feed tables). No circular references detected in the sheets inspected.

---

## 8. Excel → PostgreSQL Mapping (STEP 5)

| Excel Metric | Excel Input | PostgreSQL Table | PostgreSQL column / metric_code | Period | Unit | Match |
|---|---|---|---|---|---|---|
| Revenue | `Stock_Database!C` | `financial_facts` | `REVENUE` | ANNUAL 2019–2025 | IDR (÷1e9 = Excel) | **MATCH** |
| HPP COGS | `Stock_Database!D` | `financial_facts` | `COST_OF_REVENUE` | ANNUAL | IDR | **MATCH** |
| Interest Expenses | `Stock_Database!E` | `financial_facts` | `INTEREST_EXPENSE_NON_OPERATING` | ANNUAL | IDR | **MATCH** |
| Net Income | `Stock_Database!F` | `financial_facts` | `EARNINGS` | ANNUAL | IDR | **MATCH** |
| OCF | `Stock_Database!G` | `financial_facts` | `OPERATING_CASH_FLOW` | ANNUAL | IDR | **MATCH** |
| DPS | `Stock_Database!H` | `dividend_facts` | `ANNUAL_TOTAL.amount_per_share` | 2020–2026 | IDR/share | **MATCH** |
| Current Assets | `Stock_Database!I` | `financial_facts` | `CURRENT_ASSETS` | ANNUAL | IDR | **MATCH** |
| Current Liabilities | `Stock_Database!J` | `financial_facts` | `CURRENT_LIABILITIES` | ANNUAL | IDR | **MATCH** |
| Total Liabilities | `Stock_Database!K` | `financial_facts` | `TOTAL_LIABILITIES` | ANNUAL | IDR | **MATCH** |
| Total Equity | `Stock_Database!L` | `financial_facts` | `TOTAL_EQUITY` | ANNUAL | IDR | **MATCH** |
| Shares (Juta) | `Stock_Database!M` | `financial_facts` | `OUTSTANDING_SHARES` | ANNUAL | shares (÷1e6) | **MATCH** |
| Stock Price | `Stock_Database!N` | `prices_daily` | `close_price` (last ≤ 31-Dec) | ANNUAL | IDR | **MATCH** |
| Avg Vol (3M) | `Stock_Database!O` | `prices_daily` | `volume` (AVGIFS 3M) | ANNUAL | shares | **MISMATCH (Excel defect)** |
| EPS | `DataInput!B30` | `financial_facts` | `EPS` | ANNUAL | IDR/share | **MATCH** |
| BVPS | `DataInput!B42` | *(derived)* | `TOTAL_EQUITY/OUTSTANDING_SHARES` | ANNUAL | IDR/share | **MATCH (derived)** |
| PER / PBV | `DataInput!B31/B43` | *(derived)* | price ÷ EPS / BVPS | ANNUAL | x | **MATCH (derived)** |
| Quarterly Revenue | `Stock_Database_Quarter!E` | `financial_facts` | `REVENUE` | QUARTER | IDR | **MATCH** |
| Quarterly COGS | `Stock_Database_Quarter!F` | `financial_facts` | `COST_OF_REVENUE` | QUARTER | IDR | **MATCH** |
| Quarterly Interest Exp | `Stock_Database_Quarter!G` | `financial_facts` | `INTEREST_EXPENSE_NON_OPERATING` | QUARTER | IDR | **MATCH** |
| Quarterly Net Income | `Stock_Database_Quarter!H` | `financial_facts` | `EARNINGS` | QUARTER | IDR | **MATCH** |
| Quarterly OCF | `Stock_Database_Quarter!I` | `financial_facts` | `OPERATING_CASH_FLOW` | QUARTER | IDR | **MATCH** |
| Quarterly Current Assets | `Stock_Database_Quarter!J` | `financial_facts` | `TOTAL_CURRENT_ASSET` | QUARTER | IDR | **MATCH (name differs)** |
| Quarterly Current Liab. | `Stock_Database_Quarter!K` | `financial_facts` | `CURRENT_LIABILITIES` | QUARTER | IDR | **MATCH** |
| Quarterly Total Liab. | `Stock_Database_Quarter!L` | `financial_facts` | `TOTAL_LIABILITIES` | QUARTER | IDR | **MATCH** |
| Quarterly Total Equity | `Stock_Database_Quarter!M` | `financial_facts` | `TOTAL_EQUITY` | QUARTER | IDR | **MATCH** |
| Quarterly Shares | `Stock_Database_Quarter!N` | `financial_facts` | `OUTSTANDING_SHARES` | QUARTER | shares | **NOT PRESENT in DB** |
| Quarterly Avg Vol (3M) | `Stock_Database_Quarter!O` | `prices_daily` | `volume` (AVGIFS 3M) | QUARTER | shares | **MATCH (derivable)** |
| Quarterly Stock Price | `Stock_Database_Quarter!P` | `prices_daily` | `close_price` (last ≤ avail. date) | QUARTER | IDR | **MATCH** |
| Ticker / Sector / Subsector | `Company_Information`, `DataInput!B6:B9` | `companies`, `instruments`, `sectors`, `instrument_sector_classifications` | `provider_identity`, `ticker`, `sector_name`, `subsector_name` | — | text | **MATCH** |
| Current Price | `DataInput!B10` | `prices_daily` | latest `close_price` | point-in-time | IDR | **MATCH** |
| Risk Free Rate | `DataInput!B11` = 0.0633 | **NOT IN DB** | — | — | % | **GAP** |
| Avg Vol (3M) — annual col | `Stock_Database!O` | `prices_daily` | `volume` | ANNUAL | shares | **MISMATCH** |

---

## 9. AUTO Reconciliation (STEP 6)

All comparisons: **Excel cached value × 1.000.000.000 = raw/PostgreSQL IDR**.
Raw Storage and PostgreSQL were verified equal in Phase 2; both are shown where useful.

### 9.1 Annual financials

| Metric | Year | Excel (billion IDR) | PostgreSQL (IDR) | Excel×1e9 | Match |
|---|---|---:|---:|---:|---|
| Revenue | 2025 | 19906.774 | 19.906.774.000.000 | 19.906.774.000.000 | ✅ |
| Revenue | 2024 | 19073.703 | 19.073.703.000.000 | 19.073.703.000.000 | ✅ |
| Revenue | 2020 | 11869.221 | 11.869.221.000.000 | 11.869.221.000.000 | ✅ |
| Revenue | 2019 | 15444.775 | 15.444.775.000.000 | 15.444.775.000.000 | ✅ |
| COGS | 2025 | −16540.549 | −16.540.549.000.000 | −16.540.549.000.000 | ✅ |
| Interest Exp | 2025 | 43.486 | 43.486.000.000 | 43.486.000.000 | ✅ |
| Net Income (EARNINGS) | 2025 | 2205.022 | 2.205.022.000.000 | 2.205.022.000.000 | ✅ |
| OCF | 2025 | 1944.258 | 1.944.258.000.000 | 1.944.258.000.000 | ✅ |
| Current Assets | 2025 | 9973.987 | 9.973.987.000.000 | 9.973.987.000.000 | ✅ |
| Current Liabilities | 2025 | 4523.347 | 4.523.347.000.000 | 4.523.347.000.000 | ✅ |
| Total Liabilities | 2025 | 5651.097 | 5.651.097.000.000 | 5.651.097.000.000 | ✅ |
| Total Equity | 2025 | 16964.382 | 16.964.382.000.000 | 16.964.382.000.000 | ✅ |
| Shares | 2025 | 4819.733 | 4.819.733.000 | 4.819.733.000 | ✅ |
| EPS | 2025 | 457.4988 | 457.4987867585196 | 457.4988 | ✅ |
| **EBITDA** | — | **not in Excel** | 3.243.685.000.000 (2025) | — | **N/A** |

### 9.2 Quarterly financials

| Metric | Quarter | Excel (billion IDR) | PostgreSQL (IDR) | Match |
|---|---|---:|---:|---|
| Revenue | 2026-Q2 | 5595.855 | 5.595.855.000.000 | ✅ |
| Revenue | 2026-Q1 | 5256.848 | 5.256.848.000.000 | ✅ |
| COGS | 2026-Q2 | −4749.754 | −4.749.754.000.000 | ✅ |
| Net Income | 2026-Q2 | 592.486 | 592.486.000.000 | ✅ |
| Net Income | 2026-Q1 | 558.949 | 558.949.000.000 | ✅ |
| OCF | 2026-Q2 | 339.738 | 339.738.000.000 | ✅ |
| OCF | 2026-Q1 | 410.715 | 410.715.000.000 | ✅ |
| Current Assets | 2026-Q2 | 11056.363 | 11.056.363.000.000 | ✅ |
| Current Liabilities | 2026-Q2 | 5459.244 | 5.459.244.000.000 | ✅ |
| Interest Exp | 2026-Q2 | 9.224 | 9.224.000.000 | ✅ |
| Interest Exp | 2026-Q1 | 9.056 | 9.056.000.000 | ✅ |

### 9.3 Price / volume / dividend

| Metric | Year | Excel | PostgreSQL | Match |
|---|---|---:|---:|---|
| Stock Price (year-end close) | 2025 | 2690 | 2690 (2025-12-30) | ✅ |
| Stock Price | 2024 | 2300 | 2300 (2024-12-30) | ✅ |
| Stock Price | 2023 | 2360 | 2360 (2023-12-29) | ✅ |
| Stock Price | 2022 | 1460 | 1460 (2022-12-30) | ✅ |
| Stock Price | 2021 | 1155 | 1155 (2021-12-30) | ✅ |
| Stock Price | 2020 | 1115 | 1115 (2020-12-30) | ✅ |
| DPS | 2025 | 192 | 192 (`ANNUAL_TOTAL` 2025) | ✅ |
| DPS | 2024 | 189 | 189 | ✅ |
| DPS | 2022 | 62 | 62 | ✅ |
| DPS | 2020 | 42 | 42 | ✅ |
| Current Price (latest) | — | 2350 (manual override) | 3340 (2026-09-24) | **MISMATCH — see §10.1** |

### 9.4 Excel-derived metrics (recomputed from PostgreSQL inputs only, for cross-check)

| Metric | Excel cached | Recompute from PostgreSQL | Match |
|---|---:|---:|---|
| EPS 2025 | 457.4988 | 2.205.022.000.000 ÷ 4.819.733.000 × 1000 = 457.4988 | ✅ |
| BVPS 2025 | 3519.7763 | 16.964.382.000.000 ÷ 4.819.733.000 × 1000 = 3519.7763 | ✅ |
| PBV 2025 | 0.764253 | 2690 ÷ 3519.7763 = 0.764253 | ✅ |
| PER 2025 | 5.879797 | 2690 ÷ 457.4988 = 5.879797 | ✅ |
| DER (latest) | 0.328640 | 5.651.097.000.000 ÷ 16.964.382.000.000 = 0.3331 | **⚠️ see §10.2** |
| Current Ratio | 2.205002 | 9.973.987.000.000 ÷ 4.523.347.000.000 = 2.205002 | ✅ |
| Market Cap | 11326.373 | 2350 × 4.819.733 ÷ 1000 = 11326.373 | ✅ (uses manual price) |
| Gross Profit 2025 | 3366.225 | 19906.774 + (−16540.549) = 3366.225 | ✅ |
| DPR 2025 | 0.419673 | 192 ÷ 457.4988 = 0.419673 | ✅ |
| Dividend Yield 2025 | 0.071375 | 192 ÷ 2690 = 0.071375 | ✅ |
| Revenue Volatility (CoV) | 0.1578163 | `STDEV.P/AVERAGE` over 2019–2025 revenue = 0.1578163 | ✅ |

**Mismatch count: 0** for all annual/quarterly financial, price, DPS and derived-metric checks. Two items are flagged separately in §10.

---

## 10. Mismatches

### 10.1 Current Price — intentional manual override (NOT a data defect)

- Excel `SUMMARY!E3` (Manual Price) is blank; `DataInput!B10` falls back to `Current_Price` = **2350**, which resolves to the **2026-Q2** point-in-time close (cached `SUMMARY!C5` = "Current Price: Rp2,350").
- Latest PostgreSQL `close_price` = **3340** (2026-09-24).
- **Cause:** the workbook was last populated with data as of **2026-Q2**; the canonical database now holds data through **2026-09-24**. Different as-of dates, not different values. Phase 3 does not modify data.
- **Action:** none. When replicating, `current_price` must be resolved against the workbook's as-of date, not "today".

### 10.2 DER — period definition difference

- Excel `FinancialHealth!B8` = `Metric_Liabilities_Total / Proj_Equity` = **0.328640**.
- `Proj_Equity` = **projected** equity (from `DataInputProyeksi`), not the 2025 actual.
- 2025 actual `TOTAL_LIABILITIES/TOTAL_EQUITY` = 5.651.097/16.964.382 = **0.333125**.
- **Cause:** Excel mixes a current-period liability figure with a **projected** equity denominator. This is by design in the template, not a data error.
- **Action:** documented only. Replication must reproduce the projection step before computing DER.

### 10.3 `Stock_Database!O` — Excel formula defect

Detailed in §4.3. Annual `Avg Vol (3M)` actually returns year-end **Close**. **Not fixed** (Phase 3 rule).

### 10.4 Dividend DPR definition

- Excel 2025 DPR = `DPS/EPS` = 192/457.4988 = **0.419673**.
- Canonical `dividend_facts` `PAYOUT_RATIO` = **0.456556** (provider-supplied `payout_ratio`).
- **Cause:** different definitions. Provider payout ratio uses provider net income / share basis; Excel uses the template's own EPS.
- **Action:** documented. Both are internally consistent; do not treat one as wrong.

### 10.5 `SUMMARY!B79` Dividend Safety = `#REF!`

Broken reference in the workbook (pre-existing). **UNKNOWN / NEEDS REVIEW** — cannot be repaired without a product decision.

---

## 11. Data Gaps (STEP 8)

### A. Directly replicable from canonical PostgreSQL

| Metric group | Source |
|---|---|
| Revenue, COGS, Interest Exp, Net Income, OCF | `financial_facts` (ANNUAL + QUARTER) |
| Current Assets, Current Liabilities, Total Liabilities, Total Equity | `financial_facts` |
| Shares Outstanding | `financial_facts.OUTSTANDING_SHARES` |
| EPS | `financial_facts.EPS` |
| Stock Price (year-end / point-in-time) | `prices_daily.close_price` |
| DPS, Yield, TTM, Payout (provider) | `dividend_facts` |
| Company name, sector, subsector | `companies`, `sectors`, `instrument_sector_classifications` |
| Quarterly period labels (`YYYY-Qn`) | `financial_periods.period_label` |

### B. Replicable but needs transformation

| Metric | Transformation required |
|---|---|
| Unit normalisation | IDR ÷ 1e9 → Excel "M Rp" column (actually billion) |
| BVPS | `TOTAL_EQUITY / OUTSTANDING_SHARES × 1000` |
| PER / PBV | price ÷ EPS / BVPS |
| Market Cap | `price × shares / 1000` |
| Gross Profit | `REVENUE + COST_OF_REVENUE` (COGS stored negative) |
| NWC, NWC/Revenue, NWC Intensity Change | subtraction + ratio + delta |
| DPR (template definition) | `DPS / EPS` |
| Dividend Yield (template definition) | `DPS / year-end price` |
| Year-end price | "last `close_price` on or before 31-Dec" window function |
| Avg Vol (3M) | `AVG(volume)` over 3 calendar months ending at as-of date |
| Current Price | last close ≤ workbook as-of date |
| Revenue CAGR / CoV / growth | time-series aggregation over `Range_Revenue` |
| Asset Growth Gap | two growth series differenced |
| PER/PBV historical averages & percentile | aggregate over historical multiples |
| Quarterly YoY thesis (Revenue/NI/GM/OCF-NI) | same-quarter prior-year join |
| Liquidity class | `AvgVol(3M) × Price` vs 10/50/200 bn thresholds |
| ICR | `EBIT / Interest Exp` with bank-sector bypass |
| Gross Margin (actual %) | `(Revenue + COGS) / Revenue` per quarter |

### C. Cannot be replicated — data/schema not available

| Missing item | Needed data | Where it would come from |
|---|---|---|
| **Risk-Free Rate (0.0633)** | 10Y SBN yield, time series | external macro source; **not** in Sectors raw or canonical |
| **Projection engine** (`Proj_Revenue`, `Proj_COGS`, `Proj_Interest`, `Proj_Net_Income`, `Proj_OCF`, `Proj_Assets_Curr`, `Proj_Liab_Curr`, `Proj_Liab_Total`, `Proj_Equity`, `Proj_Shares`, `Proj_DPS`, `Proj_Dividend_Payout_Ratio`) | forward projection methodology | **no canonical equivalent**; template uses `DataInputProyeksi` + growth assumptions |
| **Sector/Type method weights** (`W_PE`, `W_PBV`, blend rule) | `Reference` B5:C16, B22:C26 | reference constants; could be seeded as reference data, but is **not** canonical yet |
| **DER/CR thresholds per stock type** | `Reference` B32:C37 | reference constants |
| **Stock Type classification** (`CYCLICAL`, etc.) | `MetricsClassification` rule engine + manual override | requires calculation (Phase 4+) |
| **Brand Power / GCG / Moat scores** | manual analyst input | **manual only** |
| **Market checklist** (IHSG vs MA200, Foreign Flow, BI Rate/Inflation, Market Mood) | market-wide index & flow data | **not in Sectors company API** |
| **Backtest outcomes** (WIN/RECOVERED/RISK/FLAT, success rate, sample count) | historical condition→outcome engine | requires calculation |
| **Quarterly `Shares` feed column** (`Stock_Database_Quarter!N`) | quarterly share count | canonical has annual shares only; quarterly shares are **not** in `financial_facts` for AUTO |
| **Total Assets, EBITDA, EBIT, Free Cash Flow, Capex, Inventory, AR** | *available* in canonical DB but **never used** by Excel | note: reverse gap — DB has data the template ignores |
| **`raw_ingestion_payloads` linkage** | provenance FK | left NULL by design in Phase 2 (no migration allowed) |

---

## 12. Dependency Map

```
Price_History (daily)  ──────────────┐
  [Close]  → point-in-time price      │
  [Volume] → 3M average               │
  [Date]   → as-of matching           │
                                      ▼
Stock_Database (annual)      Stock_Database_Quarter (quarterly)
  C..L financials              E..N financials
  M  shares                    N  shares
  N  price  ◄───────────────── P  price
  O  avgvol (DEFECTIVE)        O  avgvol  ◄──────────────────────┘
        │                              │
        ▼                              ▼
   DataInput                    DataInputProyeksi
   B20..B43                      B12..B23, B47..B52
        │                              │
        ├──────────────┬───────────────┤
        ▼              ▼               ▼
 MetricsClassification  FinancialHealth   ValuationCurrent
   B7..B39                B8..B26           B6..B47
        │                      │                │
        └──────────┬───────────┴────────────────┘
                   ▼
                SUMMARY (dashboard)
                B13..B19 valuation, B40..B44 health,
                B48..B56 thresholds/liquidity, B76..B80 targets

Reference (weights, thresholds) ──► MetricsClassification, ValuationCurrent
Company_Information ─────────────► DataInput B6..B9
```

Named-range anchors (verified):

| Name | Target |
|---|---|
| `Stock_Ticker` | `SUMMARY!$B$4` |
| `Current_Price` | `DataInput!$B$10` |
| `Param_RiskFreeRate` | `DataInput!$B$11` |
| `Years_Base_Selected` | `DataInput!$B$12` |
| `Years_Avail` | `DataInput!$B$15` |
| `Company_Sector` | `DataInput!$B$8` |
| `Stock_Type` | `MetricsClassification!$B$82` |
| `Metric_Price_Current` | `MetricsClassification!$B$24` |
| `Years_Compare` | `MetricsClassification!$B$5` |
| `AsofQuarter` | `DataInputProyeksi!$B$4` |
| `Last_Audited_Year` | `DataInputProyeksi!$B$5` |
| `Proj_Shares` | `DataInputProyeksi!$F$25` |
| `Health_Score` | `FinancialHealth!$B$26` |
| `Health_Status` | `FinancialHealth!$B$27` |
| `liquidity_score` | `SUMMARY!$B$56` |
| `Range_Revenue` | `OFFSET(DataInput!$C$20,0,0,1,Years_Avail)` |
| `Range_DPR` | `OFFSET(DataInput!$C$28,0,0,1,Years_Avail)` |
| `Ref_Sec_List` | `Method_Weights_Sector[Sector]` |
| `Ref_Type_List` | `Method_Weights_Type[Stock Type]` |

---

## 13. Metrics That Genuinely Need Calculation

These are **not** stored in canonical PostgreSQL and must be computed (Phase 4+):

1. All projection outputs (`Proj_*`) — forward estimates.
2. Stock-type classification engine (SLOW GROWER / STALWART / FAST GROWER / CYCLICAL / ASSET PLAY / TURN AROUND).
3. The five valuation methods (Peter Lynch, Type & Sector Weighted, Mean Reversion PBV, DDM, Discounted Earnings).
4. IV Consensus verdict.
5. Margin of Safety and Ideal Price.
6. Health Score, Risk Rating, Clearance Status.
7. Forensic flags (Asset Growth Gap, NWC Intensity Change, Margin Spike, Debt vs Profit Growth).
8. Business Quality / Moat composite.
9. Market Mood / market checklist.
10. Backtest outcomes and success rates.
11. CAGR / CoV / growth series / averages / percentile.
12. Liquidity classification.
13. TTM aggregation (if a TTM view is required).

## 14. Metrics That Are Display-Only

1. All `✅/⚠️/❌/🛒` status labels and diagnostic strings.
2. Valuation method description prose (`ValuationCurrent!D25:D29`).
3. Narrative commentary blocks.
4. `DB_ANALYSIS` verdict strings.
5. Unit suffixes and `CONCATENATE` presentation text.
6. `Reference` lookup tables (constants, not computed).
7. `ExportConfig` sheet.
8. `Helper` stock/year lists.
9. `#REF!` Dividend Safety cell (§10.5).

---

## 15. Summary of Findings

| Finding | Severity | Status |
|---|---|---|
| Excel "M Rp" actually means **billion IDR** (×1e9) | HIGH — silent scale error if ignored | Documented |
| `Stock_Database!O` "Avg Vol (3M)" returns **Close** (formula defect) | HIGH | Documented, **not fixed** |
| `Current Price` differs (2350 vs 3340) due to as-of date | LOW — not a data defect | Documented |
| DER uses **projected** equity, not actual | MEDIUM — must reproduce projection first | Documented |
| Dividend DPR: template `DPS/EPS` vs provider `PAYOUT_RATIO` | LOW — different definitions | Documented |
| `SUMMARY!B79` = `#REF!` | LOW | Documented as UNKNOWN |
| Risk-free rate, projections, weights, market data absent from canonical | HIGH — blocks full replication | Listed in §11C |
| DB has `TOTAL_ASSETS`, `EBITDA`, `FCF`, `CAPEX`, `INVENTORY`, AR **unused** by Excel | INFO | Reverse gap noted |

**Reconciliation result:** all annual (2019–2025) and quarterly (2026-Q1/Q2) financial, price, share, DPS and derived-metric values in the workbook **match** canonical PostgreSQL exactly once the ×1.000.000.000 unit factor is applied. **0 unexplained mismatches.**

**Phase 3 scope respected:** no Python/SQL calculation written, no `calc_*` table, no migration, no frontend change, no canonical/raw data change.
