# Frontend Audit — Sample-Data Frontend vs Current Frontend

**Type of task:** read-only audit / comparison. No application code, frontend file, migration, or Git state was modified.
**Date of audit:** 2026-09-30
**Method:** `git log` / `git show` / `git diff` plus a read-only `git archive` extraction into `%TEMP%`. Nothing was checked out, reset, committed, or pushed.

---

## 1. Historical commit selected

| Field | Value |
| --- | --- |
| Historical commit | **`2480f2b`** — `2480f2b9ea302e8f1954d967538e5cff59a55be9` |
| Subject | `feat: checkpoint current StockLens development` |
| Author date | 2026-09-27 |
| Current HEAD | **`80c3c1d`** — `80c3c1dff0f7518a871858fc4e457bb5f17a606a` |
| Subject | `checkpoint: current StockLens development` |
| Author date | 2026-09-30 |

`2480f2b` is the **direct first parent of HEAD** (`git rev-list --parents -1 HEAD` → `80c3c1d 2480f2b`).

The task brief pointed at `frontend/src/lib/analysis/mock-stock-details.ts`. **That path does not exist in this repository at any commit.** `git log --all -- frontend/src/lib/analysis/mock-stock-details.ts` returns nothing. The mock dataset lives at `frontend/src/data/mock-stock-details.ts`, which was added by `71bfaef` (`git log --all --diff-filter=A -- frontend/src/data/mock-stock-details.ts`). This audit uses the real path.

## 2. Why `2480f2b` represents the sample-data version

Every claim below is a command result, not an inference.

| Evidence | Command / result |
| --- | --- |
| The stock page read the mock table directly | `git show 2480f2b:frontend/src/components/stock-research/stock-research-page.tsx` contains `import { mockStockDetails } from "@/data/mock-stock-details";` and `const stock = mockStockDetails[ticker.toUpperCase()] ?? mockStockDetails.AUTO;` |
| The market list read the mock table directly | `git show 2480f2b:frontend/src/components/market-overview-page.tsx` contains `import { mockMarketOverviewStocks, type MarketOverviewStock } from "@/data/mock-stock-details";` and `const totalPages = Math.ceil(mockMarketOverviewStocks.length / PAGE_SIZE);` |
| The route did no database read | `git show 2480f2b:frontend/src/app/market/[ticker]/page.tsx` → `return <StockResearchPage ticker={resolvedParams.ticker} />;` (no `await`, no RPC) |
| The market route did no database read | `git show 2480f2b:frontend/src/app/market/page.tsx` → `return <MarketOverviewPage />;` (no props) |
| The frontend had **zero** Supabase references | `git grep -l -i supabase 2480f2b -- frontend` → no output, exit code 1 |
| The frontend had no Supabase dependency | `git show 2480f2b:frontend/package.json` has no `@supabase/supabase-js` and no `server-only` |
| The whole data layer did not exist yet | `git ls-tree -r --name-only 2480f2b -- frontend/src/lib` returns **only** the five `analysis/*` files. No `stock-data.ts`, `stock-detail-adapter.ts`, `stock-types.ts`, `sample-comparison.ts`, `valuation-methods.ts`, `backtest-adapter.ts`, `market-page-size.ts`, `utils/dates.ts`. |
| It is the last such commit | `git log --oneline --first-parent HEAD` = `80c3c1d → 2480f2b → cbe62c0 → 0a7f9fb → e7d7ff4 → 78ff158 → 2ce60df → d0db1a4 → …`. The Supabase switch happens in the **next** commit, `80c3c1d`. |
| It is also the same frontend as the `2ce60df` sample-data state | `git diff --name-only 2ce60df 2480f2b -- frontend` → **0 files**. `78ff158`, `e7d7ff4`, `0a7f9fb`, `cbe62c0` touched only `docs/` and `supabase/`. |

So `2480f2b` is simultaneously (a) the last commit whose frontend is entirely mock-data driven and (b) byte-identical, for `frontend/`, to the `2ce60df` "fixing single source data" frontend state.

**Extraction used for inspection (read-only, outside the repository):**

```powershell
git archive --format=tar --output="$env:TEMP\sl_hist.tar" 2480f2b frontend
mkdir "$env:TEMP\sl_hist"; tar -xf "$env:TEMP\sl_hist.tar" -C "$env:TEMP\sl_hist"
git archive --format=tar --output="$env:TEMP\sl_cur.tar"  80c3c1d frontend
mkdir "$env:TEMP\sl_cur";  tar -xf "$env:TEMP\sl_cur.tar"  -C "$env:TEMP\sl_cur"
```

58 files at `2480f2b` vs 75 files at HEAD.

> Note: piping `git archive` directly into `tar` on this Windows host corrupts the stream (`tar.exe: Damaged tar archive (bad header checksum)`). `--output=<file>` then `tar -xf <file>` works.

## 3. Current HEAD

`80c3c1d` = `checkpoint: current StockLens development`, 2026-09-30, also `origin/main`. Working tree clean: `git status --short` → empty (0 bytes).


## 4. Executive comparison

| Dimension | `2480f2b` (sample data) | `80c3c1d` (current) |
| --- | --- | --- |
| Stock detail data source | `mockStockDetails[ticker] ?? mockStockDetails.AUTO` — one hand-written TS object | `getStockResearchData()` RPC `get_stock_research_data` → `buildStockDetail()` |
| Market list data source | `mockMarketOverviewStocks` — 8 hardcoded stocks | `get_market_overview_page` RPC, server-paged |
| Unknown ticker | silently rendered **AUTO's** data under the requested ticker | `notFound()` → `market/[ticker]/not-found.tsx` |
| Tickers with data | 8 market rows, 1 full detail record (AUTO) | whatever is in the database |
| New data-layer files | 0 | 8 (`stock-data`, `stock-detail-adapter`, `stock-types`, `valuation-methods`, `backtest-adapter`, `sample-comparison`, `market-page-size`, `utils/dates`) |
| New UI files | 0 | 4 (`unavailable-badge`, `demo-data-badge`, `chart-empty-state`, `sample-comparison-card`) |
| New routes | 0 | 3 (`market/loading`, `market/[ticker]/loading`, `market/[ticker]/not-found`) |
| Nullability | most fields non-nullable (`mos: number`) | most fields nullable (`mos: number \| null`) plus explicit "Not available" surfaces |
| New dependencies | — | `@supabase/supabase-js ^2.117.2`, `server-only ^0.0.1` |
| Frontend files changed | — | **39** (17 added, 22 modified); 3760 insertions, 321 deletions |

**Verdict in one line:** the UI shell, tab set, card layout and product flow are preserved; the **data provenance** moved from a single hardcoded AUTO object to the database, and several metrics that the sample object populated are now either emptied, renamed, or no longer produced.

## 5. Metric-by-metric comparison

Legend for column 4: `SAME` · `RENAMED` · `REMOVED` · `NEW` · `LOGIC CHANGED` · `DATA SOURCE CHANGED` · `UNKNOWN`.
"Old" = `2480f2b`. "Current" = `80c3c1d`. `mock.ts` = `frontend/src/data/mock-stock-details.ts`; `adapter.ts` = `frontend/src/lib/stock-detail-adapter.ts`.

**Status totals across the 139 rows below:** DATA SOURCE CHANGED 42 · REMOVED 37 (35 plain + `REMOVED (6 rows)` + `REMOVED (3+)`) · LOGIC CHANGED 27 · RENAMED 15 · NEW 9 · SAME 9 · UNKNOWN 0.

### 5.1 Global / routing / shell

| # | Metric / UI field | Old sample-data frontend | Current frontend | Status | Evidence |
| --- | --- | --- | --- | --- | --- |
| 1 | Stock detail data source | `mockStockDetails[ticker.toUpperCase()] ?? mockStockDetails.AUTO` | `await getStockResearchData(ticker)` → `buildStockDetail(data, backtest)` | DATA SOURCE CHANGED | old `stock-research-page.tsx:34`; current `app/market/[ticker]/page.tsx:11-24` |
| 2 | Market list data source | `mockMarketOverviewStocks` (8 rows) | `getMarketOverviewData(page, size)` RPC | DATA SOURCE CHANGED | old `market-overview-page.tsx:6,14,22`; current `app/market/page.tsx:2,19` |
| 3 | Unknown ticker handling | falls back to `mockStockDetails.AUTO` (renders another company) | `if (!data) notFound()` | LOGIC CHANGED | old `stock-research-page.tsx:34`; current `app/market/[ticker]/page.tsx:19-21` |
| 4 | Research tab set | `Overview, Financials, Growth, Valuation, Backtest` | identical | SAME | `research-tabs.tsx` byte-identical in both trees |
| 5 | Tab deep-link (`#hash`) | `tabFromHash` | identical | SAME | `research-tabs.tsx:18-21` in both |
| 6 | Breadcrumb / header / disclaimer footer | present | present, unmodified | SAME | `disclaimer-footer.tsx`, `breadcrumb.tsx` absent from `git diff --name-status 2480f2b 80c3c1d -- frontend` |
| 7 | Demo-data labelling | none existed | `DemoDataBadge`, `UnavailableBadge`, `ChartEmptyState` | NEW | `components/ui/demo-data-badge.tsx`, `unavailable-badge.tsx`, `chart-empty-state.tsx` (all added) |
| 8 | "Workbook Sample vs Tabel" audit card | none | `SampleComparisonCard` + `buildSampleComparison()` | NEW | `components/stock-research/sample-comparison-card.tsx`, `lib/sample-comparison.ts`, `data/workbook-sample-auto.ts` |


### 5.2 Overview — five key metric cards

| # | Metric / UI field | Old sample-data frontend | Current frontend | Status | Evidence |
| --- | --- | --- | --- | --- | --- |
| 9 | Current Price | `formatRupiah(stock.price)`; subtext `+2,63% today` (green) | `formatRupiah(stock.price)`; subtext `Last updated: 24 Sep 2026` (slate) | LOGIC CHANGED | old `key-metric-card.tsx:9-16`; current `key-metric-card.tsx:15-22` + `utils/dates.ts:50` |
| 10 | Intrinsic Value | `stock.intrinsicValue` (mock `2780`) | `primaryMethod.intrinsicValue` (DB), nullable | DATA SOURCE CHANGED | `adapter.ts:827`, `:878` |
| 11 | Intrinsic Value sub-label "Method:" | `getMainValuationMethod(stockType)` → `"Peter Lynch / Adaptive"` / `"Type & Sector Weighted"` | → `"Peter Lynch"` / `"Weighted IV"` | RENAMED | `lib/valuation-methods.ts:39-45`; `analysis/valuation.ts:1-8` |
| 12 | Margin of Safety (card) | `stock.mos.toFixed(1)` (mock `29,9%`) | `stock.mos != null ? … : "Not available"`; mos = `(IV−price)/IV×100` | LOGIC CHANGED | `adapter.ts:36-39`, `:829`; `key-metric-card.tsx:38` |
| 13 | Stock Character | `stock.stockCharacter` (`"Cyclical"`) | `stockCharacter = stockType` from DB, else `"Not available"` | DATA SOURCE CHANGED | `adapter.ts:831`, `:880` |
| 14 | Stock Character description | `"Tends to follow economic cycles"` | `"Stock type classification from the database"` | LOGIC CHANGED | old `mock.ts:525`; current `adapter.ts:881` |
| 15 | Historical Evidence (wins / total) | `4 / 4` from mock | now **two win rates**: `evidenceWinRates` = `(WIN + RECOVERED) / Undervalued` for each rule, shown as the figure with a `by Method` / `by MoS` label under it (`100%`, `75%`, `66.7%`), or `"Not available"` when that rule flagged no Undervalued case or there is no backtest | DATA SOURCE CHANGED | old `mock.ts:526-527`; current `adapter.ts:57-70,855-861,927`, `analysis/historical-evidence.ts:44-72`, `key-metric-card.tsx:56-118` |

### 5.3 Overview — cards

| # | Metric / UI field | Old sample-data frontend | Current frontend | Status | Evidence |
| --- | --- | --- | --- | --- | --- |
| 16 | Research Summary text | hand-written per-stock prose | generated: `"<TICKER> was evaluated using the <method> valuation model…"` | LOGIC CHANGED | old `mock.ts:528-529`; current `adapter.ts:884-886` |
| 17 | Company Profile description | full company paragraph | `"<name> — the full company description is not available in the database yet."` | DATA SOURCE CHANGED | old `mock.ts:532-533`; current `adapter.ts:889` |
| 18 | Listed date | `"15 Jul 1997"` | `"Not available"` | REMOVED | old `mock.ts:536`; current `adapter.ts:892` |
| 19 | Headquarters | `"Jakarta, Indonesia"` | `"Not available"` | REMOVED | old `mock.ts:537`; current `adapter.ts:893` |
| 20 | Website | `"www.astra-otoparts.com"` | `"Not available"` | REMOVED | old `mock.ts:538`; current `adapter.ts:894` |
| 21 | Price Chart series | 13 hardcoded monthly points | `buildMonthlyPricePoints(data.prices)` from ≤260 daily closes | DATA SOURCE CHANGED | old `mock.ts:542-556`; current `adapter.ts:791-806` |
| 22 | Price Chart timeframe selector | `points.slice(-Number.parseInt(tf))` (array count) | calendar-month window via `toMonthIndex` | LOGIC CHANGED | old `price-chart-card.tsx:18`; current `price-chart-card.tsx:196-208` |
| 23 | 52W Low / 52W High | mock `low52W: 1520`, `high52W: 2350` | `Math.min/Math.max` over DB closes | LOGIC CHANGED | old `mock.ts:557-558`; current `adapter.ts:833-835` |
| 24 | YTD | mock `ytdPercent: -12.4` | `ytdPercent: changePercent` = last close vs previous close | LOGIC CHANGED | old `mock.ts:559`; current `adapter.ts:824-825`, `:901` |
| 25 | Market Cap | `"Rp12 T"` | `Rp${marketCap/1e12} T` from DB, else `"Not available"` | DATA SOURCE CHANGED | old `mock.ts:560`; current `adapter.ts:902-903` |

### 5.4 Current Valuation

| # | Metric / UI field | Old sample-data frontend | Current frontend | Status | Evidence |
| --- | --- | --- | --- | --- | --- |
| 27 | "Based Method" verdict badge | always `tone="undervalued"` | `verdictTone(valuation.verdict)` | LOGIC CHANGED | old `current-valuation-card.tsx:48-50`; current `current-valuation-card.tsx:62-67,155-160` |
| 28 | "Based MoS" badge | `classifyCurrentValuationMos(mos) === "UNDERVALUED"` | identical | SAME | `current-valuation-card.tsx:33` (both) + `analysis/backtest.ts:67-69` |
| 29 | Price-vs-IV comparison bars | unconditional; no empty state | guarded; `UnavailableBadge` when no IV/price | LOGIC CHANGED | old `current-valuation-card.tsx:13-14,80-115`; current `:14-21,141-148` |
| 30 | EPS (TTM) | mock `477.8`, note "Trailing twelve months" | `earnings / outstandingShares` from latest annual period | DATA SOURCE CHANGED | old `mock.ts:569`; current `adapter.ts:757,771-774` |
| 31 | BVPS | mock `2780`, note "Book value per share" | `totalEquity / outstandingShares` | DATA SOURCE CHANGED | old `mock.ts:570`; current `adapter.ts:758,776-779` |
| 32 | P/E Ratio | `"4,92x"`, note "Below sector average" | `price / eps`, note `"Price / EPS"` | DATA SOURCE CHANGED | old `mock.ts:571`; current `adapter.ts:780` |
| 33 | P/BV Ratio | `"0,66x"`, note "Below historical avg" | `price / bvps`, note `"Price / BVPS"` | DATA SOURCE CHANGED | old `mock.ts:572`; current `adapter.ts:781` |
| 34 | PEG Ratio | `"0,25x"`, note "Attractive" | **not produced** | REMOVED | old `mock.ts:573`; current `buildValuationMetrics` returns only 4 rows (`adapter.ts:769-782`) |
| 35 | Dividend Yield (valuation metric) | `"4,83%"`, note "Above market avg" | **not produced** | REMOVED | old `mock.ts:574`; current `adapter.ts:769-782` |
| 36 | "Why the Methods Differ?" cards | per-stock `currentValuation.explanations[]` in the mock object | static `VALUATION_LENS_CARDS` module | RENAMED | old `mock.ts:18-22,547-551`; current `data/valuation-lenses.ts:21-40` |
| 37 | Key Takeaway readouts | 3 mock bullets (`"2 dari 5 metode menunjukkan Undervalued"`, highest/lowest IV) | `readouts: []` → always empty | REMOVED | old `mock.ts:541-545`; current `adapter.ts:917` |

### 5.5 Valuation tab — methods table

| # | Metric / UI field | Old sample-data frontend | Current frontend | Status | Evidence |
| --- | --- | --- | --- | --- | --- |
| 38 | Method names | `Peter Lynch / Adaptive`, `Type & Sector Weighted`, `Mean Reversion PBV`, `Dividend Discount Model`, `Discounted Earnings` | `Peter Lynch`, `Weighted IV`, `Mean Reversion PBV [Asset]`, `Dividend Discount Model (Cash Flow)`, `Discounted Earnings Model (Growth)` | RENAMED | old `mock.ts:533-537` (at `2480f2b`); current `valuation-methods.ts:39-45` |
| 39 | Method set shown | all 5 always | only `intrinsicValue != null` and status `VALID` or `APPROXIMATED`; `IV = 0` rows stay visible but are marked `SKIPPED` | LOGIC CHANGED | `adapter.ts:912-932` |
| 40 | ~~Potential~~ | stored mock strings (`"+51,82%"`) | **column removed** — it restated the same gap MoS already shows, against a different denominator, and nothing consumed it | REMOVED | old `mock.ts:533`; was `adapter.ts:920`, `valuation-tab-content.tsx:50` |
| 41 | Margin of Safety (per method) | stored mock strings (`"34,13%"`) | `(IV − price) / IV × 100`, but **`null` when `IV <= 0`**: the divisor's sign flips the ratio, so GEMA's `−22` IV used to print a bogus `+522%`. Backtest keeps negative IVs (D5) via its own path. | LOGIC CHANGED (bug fix) | old `mock.ts:533`; current `adapter.ts:42-61,948` |
| 42 | Status badge per method | stored `UNDERVALUED` / `OVERVALUED` | three-way: `IV = 0` → `SKIPPED` (workbook `⚪ N/A (Skip)`, neutral badge); `IV < 0` → `OVERVALUED` (D5); else the stored verdict. Was a binary collapse that turned `NOT_APPLICABLE` into `OVERVALUED`. | LOGIC CHANGED (bug fix) | old `mock.ts:533-537`; current `adapter.ts:93-101,955`, `valuation-methods.ts:22-36`, `status-badge.tsx:33-34` |
| 43 | "Main" method badge | `method === getMainValuationMethod(stockType)` | `methodCode === currentValuation.mainMethodCode` — the badge **follows the fallback**: when the preferred rule has `IV <= 0` the other main-rule candidate supplies the headline IV/MoS and carries the badge (GEMA: Peter Lynch `−22` → Weighted IV `32.74`) | LOGIC CHANGED | `valuation-tab-content.tsx:36-41`, `adapter.ts:30-66,939-941`, `analysis/valuation.ts:11-16` |
| 44 | Spectrum chart labels | hardcoded string comparisons for wrapping | `valuationMethodShortLabel()` from the registry | RENAMED | old `valuation-tab-content.tsx:64`; current `:88` + `valuation-methods.ts:51-60` |
| 45 | Intrinsic Value / MoS "Method:" label | `getMainValuationMethod(stockType)` | `valuationMethodLabel(currentValuation.mainMethodCode)` — names the rule that actually supplied the figure, not the type's preferred rule | LOGIC CHANGED | `key-metric-card.tsx:12-18,44,55` |


### 5.6 Financials tab

| # | Metric / UI field | Old sample-data frontend | Current frontend | Status | Evidence |
| --- | --- | --- | --- | --- | --- |
| 45 | Annual metric — Return on Equity (ROE) | `"17,8%"` (mock) | `earnings / equity` | DATA SOURCE CHANGED | old `mock.ts:886-888`; current `adapter.ts:309-312` |
| 46 | Annual metric — Gross Margin | `"18,4%"` | `grossProfit / revenue` | DATA SOURCE CHANGED | old `mock.ts:890-892`; current `adapter.ts:314-317` |
| 47 | Annual metric — Net Margin | `"7,2%"` | `earnings / revenue` | DATA SOURCE CHANGED | old `mock.ts:894-896`; current `adapter.ts:319-322` |
| 48 | Annual metric — Operating Profit | `"2,5"` | **not produced** | REMOVED | old `mock.ts:898-900`; current `adapter.ts:307-338` |
| 49 | Annual metric — Total Assets | `"22,0"` | **not produced** | REMOVED | old `mock.ts:902-904`; current `adapter.ts:307-338` |
| 50 | Annual metric — Revenue | not in the annual metric strip | `revenue` in Rp Trillion | NEW | current `adapter.ts:324-327` |
| 51 | Annual metric — Total Equity | `"10,2"` | `totalEquity` in Rp Trillion | DATA SOURCE CHANGED | old `mock.ts:906-908`; current `adapter.ts:329-332` |
| 52 | Annual metric — Total Liabilities | not in the annual metric strip | `totalLiabilities` in Rp Trillion | NEW | current `adapter.ts:334-337` |
| 53 | Quarterly metric — Interest Expense | `"9,2"` | **not produced** (still present in the thesis table) | REMOVED | old `mock.ts:912-914`; current `adapter.ts:360-367` |
| 54 | Quarterly metric — Revenue | not in the quarterly metric strip | `revenue` | NEW | current `adapter.ts:361` |
| 55 | Quarterly metric — Gross Margin / Net Margin | `"15,1%"` / `"10,6%"` | computed from facts | DATA SOURCE CHANGED | old `mock.ts:916-922`; current `adapter.ts:362-363` |
| 56 | Quarterly metric — Operating Cash Flow | `"0,34"` | `OPERATING_CASH_FLOW` | DATA SOURCE CHANGED | old `mock.ts:924-926`; current `adapter.ts:364` |
| 57 | Quarterly metric — Total Liabilities / Total Equity | `"6,69"` / `"17,20"` | from facts | DATA SOURCE CHANGED | old `mock.ts:928-934`; current `adapter.ts:365-366` |
| 58 | Annual table rows | 11 rows: Revenue, Gross Profit, Operating Profit, Net Income, EPS, Total Assets, Total Equity, ROE, Gross Margin, Net Margin, BVPS | 5 rows: Revenue, Net Income, Gross Profit, Total Equity, Total Liabilities | REMOVED (6 rows) | old `mock.ts:940-995`; current `adapter.ts:213` |
| 59 | Quarterly table rows | Revenue, Gross Profit, Net Income, Operating Cash Flow, Total Equity (+1 truncated) | 2 rows: Revenue, Net Income | REMOVED (3+) | old `mock.ts:1000-1026`; current `adapter.ts:235` |
| 60 | Annual change column label | `"CAGR (5Y)"` | `"YoY Change"` (first vs last period) | RENAMED | old `mock.ts:938`; current `adapter.ts:212,221-224` |
| 61 | Quarterly change column label | `"YoY (Latest)"` | `"QoQ Change"`, value hardcoded `UNAVAILABLE` | RENAMED | old `mock.ts:999`; current `adapter.ts:234,240` |
| 62 | Interest Expense unit label | `"M Rp"` | `"Rp Billion"` (Financials) / `"(Rp Bn)"` (thesis row) | RENAMED | old `financials-tab-content.tsx:53`; current `financials-tab-content.tsx:54` + `adapter.ts:505` |
| 63 | Metric status classifier (`Expanding margin`, `Strong cash conversion`, …) | `classifyFinancialMetric(metric, table, quarterlyOcfRatio)` | identical function | SAME | `analysis/valuation.ts:36-61` unchanged; only the `quarterlyOcfRatio` input is now DB-derived (`financials-tab-content.tsx:82-84`) |
| 64 | Quarterly trend card CAGR label | `"Revenue YoY Growth"` / `"Net Income YoY Growth"` / `"OCF YoY Growth"` | `"YoY Growth"` (uniform) | RENAMED | old `mock.ts:840,856,872`; current `adapter.ts:269` |
| 65 | Quarterly trend card value | mock strings (`"19,3%"`, `"-51,9%"`) | computed vs prior-year quarter | LOGIC CHANGED | old `mock.ts:841,873`; current `adapter.ts:258-263` |


### 5.7 Growth tab

| # | Metric / UI field | Old sample-data frontend | Current frontend | Status | Evidence |
| --- | --- | --- | --- | --- | --- |
| 66 | Revenue CAGR (Historical) | `'4,32%'`, period `'2019 - 2024'` | `GROWTH_REVENUE_CAGR_LONG`, period `"Historical"` | DATA SOURCE CHANGED | old `mock.ts:585`; current `adapter.ts:925-928` |
| 67 | Revenue CAGR (5Y) | `'10,90%'` | `GROWTH_REVENUE_CAGR_SHORT`, period `"5 Year"` | DATA SOURCE CHANGED | old `mock.ts:586`; current `adapter.ts:929-932` |
| 68 | Revenue Growth (YoY) | `'4,37%'`, `'Latest annual (2025)'` | `GROWTH_REVENUE_YOY`, period `"YoY"` | DATA SOURCE CHANGED | old `mock.ts:587`; current `adapter.ts:933-936` |
| 69 | Revenue Momentum | `'Accelerating'`, tone positive | `QUALITY_REVENUE_MOMENTUM === 1 ? "Accelerating" : "Not available"` | LOGIC CHANGED | old `mock.ts:588`; current `adapter.ts:937-941` |
| 70 | EPS Growth (Historical) | `'19,97%'` | `GROWTH_EPS_CAGR_LONG` | DATA SOURCE CHANGED | old `mock.ts:589`; current `adapter.ts:942-945` |
| 71 | EPS Growth (5Y) | `'43255,73%'` | `GROWTH_EPS_CAGR_SHORT` | DATA SOURCE CHANGED | old `mock.ts:590`; current `adapter.ts:946-949` |
| 72 | EPS Momentum | `'Accelerating'`, tone positive | binary `1 → "Accelerating"` else `"Not available"` | LOGIC CHANGED | old `mock.ts:591`; current `adapter.ts:950-954` |
| 73 | Period selector options | `['All Years','5 Years','3 Years']`, default `'All Years'` | `["Quarterly"]`, default `"Quarterly"` | RENAMED | old `mock.ts:582-583`; current `adapter.ts:922-923` |
| 74 | Growth chart periods | `['2019' … '2025','2026P']` (incl. projection) | annual periods present in DB, no projection | DATA SOURCE CHANGED | old `mock.ts:594`; current `adapter.ts:383` |
| 75 | Growth chart unit | values in Rp Trillion (`19906.8`, `2205`) | `Rp Billion` (`incomeStatementUnit = 'Rp Billion'`) | RENAMED | old `mock.ts:595-600`; current `adapter.ts:385-386` + `growth-tab-content.tsx:294` |
| 76 | Growth-rate series | stored mock arrays, `0` for the first year, one `63500` spike | computed YoY, `null` for the first year | LOGIC CHANGED | old `mock.ts:601-604`; current `adapter.ts:404-409` |
| 77 | Forensic — Revenue Coverage | absent | `GROWTH_REVENUE_COV` as a multiple | NEW | current `adapter.ts:705-709` |
| 78 | Forensic — Asset Growth Gap | `'-7,90%'`, context `'No excessive current-asset growth signal'` | `GROWTH_ASSET_GROWTH_GAP`, context `"selisih pertumbuhan aset terhadap revenue"` | LOGIC CHANGED | old `mock.ts:609`; current `adapter.ts:711-715` |
| 79 | Forensic — Debt Growth Gap | absent | `FORENSIC_DEBT_GROWTH_GAP` | NEW | current `adapter.ts:717-721` |
| 80 | Forensic — Margin Spike | absent | `FORENSIC_MARGIN_SPIKE` | NEW | current `adapter.ts:723-727` |
| 81 | Forensic — Return on Equity (ROE) | `'13,39%'` | not produced | REMOVED | old `mock.ts:609`; current `adapter.ts:703-728` |
| 82 | Forensic — Gross Margin | `'15,1%'` | not produced | REMOVED | old `mock.ts:609`; current `adapter.ts:703-728` |
| 83 | Forensic — Quality: CF vs Net Income | `'Strong'` | not produced | REMOVED | old `mock.ts:609`; current `adapter.ts:703-728` |
| 84 | Forensic — ROE Trend | `'Improving'` | not produced | REMOVED | old `mock.ts:609`; current `adapter.ts:703-728` |
| 85 | Forensic — Equity Growth Consistency | `'Consistent'` | not produced | REMOVED | old `mock.ts:609`; current `adapter.ts:703-728` |
| 86 | Forensic — Current Asset Growth (YoY) | `'12,27%'` | not produced | REMOVED | old `mock.ts:609`; current `adapter.ts:703-728` |
| 87 | Forensic — NWC / Revenue (Latest) | `'27,38%'` | not produced | REMOVED | old `mock.ts:609`; current `adapter.ts:703-728` |
| 88 | Forensic — NWC Intensity Change (YoY) | `'+4,30 ppt'` | not produced | REMOVED | old `mock.ts:609`; current `adapter.ts:703-728` |
| 89 | Forensic — Cash Flow Check | `'OK'` | not produced | REMOVED | old `mock.ts:609`; current `adapter.ts:703-728` |
| 90 | Quarterly quality summary (`quarterlyMeaning`) | full sentence | `"No automatic quarterly quality summary for this ticker yet."` | REMOVED | old `mock.ts:610`; current `adapter.ts:960` |
| 91 | Health score / rating / clearance (`overall`) | `'80 / 100'`, `'Healthy'`, `'OK'`, `'No major red flag detected.'` | all four = `"Not available"` | REMOVED | old `mock.ts:611`; current `adapter.ts:961` |
| 92 | `profitability` block (6 metrics: ROE Avg, ROE Projected, ROE Trend, NPM Avg, NPM vs Avg, ROE StdDev) | populated in mock | `{ metrics: [] }` | REMOVED | old `mock.ts:607`; current `adapter.ts:957` |
| 93 | `cashFlow` block — Debt to Equity (DER) | `'0,33x'` | `{ metrics: [] }` | REMOVED | old `mock.ts:608`; current `adapter.ts:958` |
| 94 | `cashFlow` block — Current Ratio | `'2,21x'` | `{ metrics: [] }` | REMOVED | old `mock.ts:608`; current `adapter.ts:958` |
| 95 | `cashFlow` block — Interest Coverage | `'49,71x'` | `{ metrics: [] }` | REMOVED | old `mock.ts:608`; current `adapter.ts:958` |
| 96 | `cashFlow` block — Operating Cash Flow | `'Rp1.944 M'` | `{ metrics: [] }` | REMOVED | old `mock.ts:608`; current `adapter.ts:958` |
| 97 | `cashFlow` block — OCF / Net Income | `'88%'` | `{ metrics: [] }` | REMOVED | old `mock.ts:608`; current `adapter.ts:958` |
| 98 | Growth Summary — Revenue Growth (3Y CAGR) | `"8,6%"`, badge Positive | `GROWTH_REVENUE_CAGR_SHORT` | DATA SOURCE CHANGED | old `mock.ts:616-620`; current `adapter.ts:567-572` |
| 99 | Growth Summary — Net Income Growth (3Y CAGR) | `"11,2%"`, badge Positive | `"Not available"` (hardcoded) | REMOVED | old `mock.ts:621-626`; current `adapter.ts:573-578` |
| 100 | Growth Summary — EPS Growth (3Y CAGR) | `"10,8%"` | `GROWTH_EPS_CAGR_SHORT` | DATA SOURCE CHANGED | old `mock.ts:627-632`; current `adapter.ts:579-584` |


### 5.8 Thesis validator / Quarterly Growth Check

| # | Metric / UI field | Old sample-data frontend | Current frontend | Status | Evidence |
| --- | --- | --- | --- | --- | --- |
| 101 | Revenue YoY (%) row | mock `"5,1%" … "19,3%"` | `yoyForQuarter(label, "REVENUE")` from DB facts | DATA SOURCE CHANGED | old `mock.ts:695-703`; current `adapter.ts:464-472` |
| 102 | Net Income YoY (%) row | mock | `yoyForQuarter(label, "EARNINGS")` | DATA SOURCE CHANGED | old `mock.ts:713-721`; current `adapter.ts:473-481` |
| 103 | Gross Margin (Actual %) row | mock | `QUALITY_GROSS_MARGIN` | DATA SOURCE CHANGED | old `mock.ts:704-712`; current `adapter.ts:482-490` |
| 104 | OCF / NI Ratio (x) row | mock `"0,53x" … "0,57x"` | `QUALITY_OCF_TO_NET_INCOME` | DATA SOURCE CHANGED | old `mock.ts:722-730`; current `adapter.ts:491-499` |
| 105 | Interest Expense row label | `"Interest Expense (M Rp)"` | `"Interest Expense (Rp Bn)"` | RENAMED | old `mock.ts:732`; current `adapter.ts:505` |
| 106 | Interest Expense value | `"10,9"` (workbook units) | `value / 1e9` | LOGIC CHANGED | old `mock.ts:733`; current `adapter.ts:69-72,506-511` |
| 107 | Trend / STATUS column | prose (`"↑ Increased +19.3%"`, `"⚠ Moderate — 0.57x"`, `"↓ Decreased -15.3%"`) | signed percent only (`"+19,30%"` / `"Not available"`) | LOGIC CHANGED | old `mock.ts:701,711,720,728,737`; current `adapter.ts:470,488,497,510` |

### 5.9 Dividend

| # | Metric / UI field | Old sample-data frontend | Current frontend | Status | Evidence |
| --- | --- | --- | --- | --- | --- |
| 108 | Dividend Consistency — Dividend Yield | `yieldRow.p2026` = `"4,8%"` | `yieldRow?.p2026 ?? "—"`, and no `Yield [%]` row is produced → `"—"` | REMOVED | old `mock.ts:767-774`; current `adapter.ts:544-554`, `dividend-consistency-card.tsx:15,33` |
| 109 | Dividend Consistency — DPR | `"23,8%"` | no `DPR [%]` row produced → `"—"` | REMOVED | old `mock.ts:757-765`; current `adapter.ts:544-554`, `dividend-consistency-card.tsx:13,41` |
| 110 | Dividend Consistency — DPS | `"113,59"` | `dividend_facts.amount_per_share` (2 dp) | DATA SOURCE CHANGED | old `mock.ts:748-756`; current `adapter.ts:546-553` |
| 111 | Dividend Consistency — Avg (4Y) | `"136,92"` / `"33,3%"` / `"6,0%"` | `avg4Y: "Not available"` (hardcoded) | REMOVED | old `mock.ts:755,764,773`; current `adapter.ts:552` |
| 112 | Dividend Trend chart — Yield series | mock yield row | `yield_ratio`; runbook states `yield_ratio` is NULL for all rows | DATA SOURCE CHANGED | old `mock.ts:767-774`; current `adapter.ts:533-539`; `docs/SUPABASE_MANUAL_RUNBOOK.md:718` |
| 113 | Dividend callout | `"Dividend signal: … average 4Y DPR of 33.3%."` | `"Historical dividend per share is taken directly from the database. Projected DPR and yield are not available yet."` | LOGIC CHANGED | old `mock.ts:776-777`; current `adapter.ts:555-558` |


### 5.10 Backtest / Historical Evidence

| # | Metric / UI field | Old sample-data frontend | Current frontend | Status | Evidence |
| --- | --- | --- | --- | --- | --- |
| 114 | Historical Evidence preview (totals, verdictMethod, verdictMos, win rates) | always populated (18 cases; `4 / 14`, `10 / 8`, `100%`) | derived from the stored backtest cases for **every** ticker that has a backtest (`buildHistoricalEvidencePreview` → same `aggregateBacktestOverview` the Backtest tab renders); AUTO still falls back to the sample cases, flagged `isDemoData` → `DemoDataBadge`; a ticker with no backtest → `"Not available"` card | DATA SOURCE CHANGED (re-wired, see below) | old `mock.ts:635-662`; current `adapter.ts:663-668,836-841,988`, `analysis/historical-evidence.ts`, `historical-evidence-preview-card.tsx:12-34,80-172` |
| 115 | Backtest cases | 18 hardcoded `makeAutoBacktestCase(...)` seeds | `get_stock_backtest` RPC → `buildBacktestCase` | DATA SOURCE CHANGED | old `mock.ts:671-690`; current `backtest-adapter.ts:104-153` |
| 116 | Backtest compact table labels | `Jenis Saham`, `Kuartal`, `TGL ANALISIS`, `Harga Analisis` + 8 English | `Stock Type`, `Quarter`, `ANALYSIS DATE`, `Analysis Price` + 8 English | RENAMED | old `backtest-tab-content.tsx:231-234`; current `backtest-tab-content.tsx:291-294` |
| 117 | IV method columns | `IV Peter Lynch`, `IV Type & Sector`, `IV Mean Reversion PBV`, `IV DDM`, `IV Discounted Earnings` | same 5 | SAME | old `:162,181`; current `:222,241` |
| 118 | "IV DDM" column label | `"IV DIVIDEND DISCOUNT MODEL"` (DetailTableV2) | `"IV DDM"` | RENAMED | old `backtest-tab-content.tsx:181`; current `:241` |
| 119 | Undervalued Methods denominator | `value !== null && value > price` over all 5 slots | `null` **and `0`** excluded → `/3`, `/4`, or `/5` | LOGIC CHANGED | old `analysis/backtest.ts:23-30`; current `analysis/backtest.ts:30-41` |
| 120 | Consensus by Method | `UNDERVALUED` / `OVERVALUED_MIXED` | `UNDERVALUED` / `OVERVALUED` | RENAMED | old `analysis/backtest.ts:10,25-29`; current `:18,34-36` |
| 121 | Consensus by MoS | `MoS Main ≥ 30% → UNDERVALUED` else `OVERVALUED_MIXED` | same rule, else `OVERVALUED` | RENAMED | old `analysis/backtest.ts:56-60`; current `:61-65` |
| 122 | MoS Main / MoS Peter / MoS Weight | mock seeds (`0.3413`, `0.3413`, `0.0736`) | stored `mos_main` / `mos_peter` / `mos_weight` | DATA SOURCE CHANGED | old `mock.ts:441-443`; current `backtest-adapter.ts:117-119` |
| 123 | Ret 3M / 6M / 9M / 12M | recomputed from `pricePath` | stored `high_nm`/`low_nm` win whenever present | DATA SOURCE CHANGED | old `backtest-tab-content.tsx:164`; current `:102-135,257-260` |
| 124 | Price 3M / 6M / 9M / 12M | recomputed from `pricePath` | stored horizon high/low | DATA SOURCE CHANGED | old `backtest-tab-content.tsx:164`; current `:261-264` |
| 125 | Ret Peak / Peak Price / Peak Month | recomputed from `pricePath` | stored `peak_price` / `peak_month` (authoritative) | DATA SOURCE CHANGED | old `backtest-tab-content.tsx:164`; current `:265-267`; `mock.ts:405-421` (new `peakMonth`/`troughMonth`) |
| 126 | Ret Trough / Trough Price / Trough Month | recomputed from `pricePath` | stored `trough_price` / `trough_month` | DATA SOURCE CHANGED | old `backtest-tab-content.tsx:164`; current `:268-270` |
| 127 | Verdict by Method / Verdict by MoS | recomputed via `calculateSimulatedVerdict` | **displayed as stored**; `calculateSimulatedVerdict` deliberately not used | LOGIC CHANGED | old `backtest-tab-content.tsx:204`; current `backtest-adapter.ts:11-15`; `docs/BACKTEST_ARCHITECTURE.md:499` |
| 128 | WIN threshold pair | two pairs: undervalued `+20% / −15%`, overvalued-or-mixed `+15% / −10%` | one pair: `+20% / −15%` | LOGIC CHANGED | old `analysis/backtest.ts:6-7`; current `:12-13` |
| 129 | Simulated verdict vocabulary | `OBSERVE` for non-undervalued branches | `FLAT` / `WIN` / `RECOVERED` / `CONFIRMED` / `REPRICE` only | LOGIC CHANGED | old `analysis/backtest.ts:91-96`; current `:112-121` |
| 130 | Business signals (Yield %, Revenue YoY, Rev %, Net Income YoY, NI %, EPS Momentum, Revenue Momentum, ROE Trend) | mock seeds (`0.1934`, `"Accelerating"`, `"Improving"`, `yield: null`, `ocfNi: null`) | stored `context.*`, `"Not available"` fallback | DATA SOURCE CHANGED | old `mock.ts:453-461`; current `backtest-adapter.ts:143-151` |
| 131 | Backtest overview outcome panels (Valuation Signal, Undervalued/Overvalued Outcome, WIN/RECOVERED/FLAT/RISK, REPRICE/CONFIRMED/OBSERVE) | present | present; `backtest-overview.tsx` is **byte-identical** | SAME | `backtest-overview.tsx` absent from `git diff --name-status 2480f2b 80c3c1d -- frontend`; the `overvaluedMixed` field name survives at `backtest-overview.tsx:35` in both trees, only its value changes because `analysis/backtest.ts` now returns `OVERVALUED` instead of `OVERVALUED_MIXED` |
| 132 | "How the Backtest Works" 3 steps | fixed copy | identical copy | SAME | old `mock.ts:665-669`; current `adapter.ts:634-651` |

### 5.11 Market Overview

| # | Metric / UI field | Old sample-data frontend | Current frontend | Status | Evidence |
| --- | --- | --- | --- | --- | --- |
| 133 | Stock universe | 8 hardcoded rows (BBCA, AUTO, ERAA, SIDO, PTBA, WIFI, INDF, JSMR) | DB paged result set | DATA SOURCE CHANGED | old `mock.ts:246-367`; current `lib/stock-data.ts:543-555` |
| 134 | Pagination | client-side, `PAGE_SIZE = 5`, `totalPages` from array length | server-side `?page=&size=`, sizes `8/12/16/20`, default 8 | LOGIC CHANGED | old `market-overview-page.tsx:12,14,17`; current `market-page-size.ts:15-17`, `market-overview-page.tsx:38-53` |
| 135 | Verdict pill | `"Undervalued"` / `"Fairly Valued"` / `"Overvalued"` per row | `verdict: "Not available"` hardcoded in the mapper → every row | REMOVED | old `mock.ts:256,271,286,…`; current `lib/stock-data.ts:254` |
| 136 | MoS | mock `12.3`, `38.4`, `8.7`, … | `mos: null` → `UnavailableBadge` | REMOVED | old `mock.ts:257`; current `lib/stock-data.ts:256`, `market-overview-page.tsx:455-463` |
| 137 | Historical Evidence (wins / total) | `5 / 8`, `4 / 4`, … | `evidenceWins: null`, `evidenceTotal: null` → `UnavailableBadge` | REMOVED | old `mock.ts:258-259`; current `lib/stock-data.ts:257-258`, `market-overview-page.tsx:465-478` |
| 138 | `recommendationAvailable` | field did not exist | `false` (hardcoded) | NEW | current `lib/stock-data.ts:255`, `stock-types.ts:12` |
| 139 | Price / change / change% / sparkline / updatedAt | mock numbers and `"12 Sep 2026"` | `close_price`, `change_percent`, `sparkline`, `latest_trading_date` | DATA SOURCE CHANGED | old `mock.ts:252-260`; current `lib/stock-data.ts:240,252-253,259` |
| 140 | `mockMarketOverviewStocks` | the live data source | dead export (never imported) | REMOVED | `mockMarketOverviewStocks` appears only at its definition (`mock.ts:256`) |

## 6. Valuation comparison

| Aspect | `2480f2b` | `80c3c1d` |
| --- | --- | --- |
| Intrinsic value shown | `primaryMethod.intrinsicValue` from mock (`2780`) | `pickPrimaryMethod()` over `valuation_methods` rows: `TYPE_SECTOR_WEIGHTED` for `STALWART`/`FAST GROWER`, else `PETER_LYNCH`, requiring `calculationStatus = "VALID"` (`adapter.ts:24-34`) |
| Main-method rule | `getMainValuationMethod()` on `stockType` string (`"stalwart"` / `"fast grower"`) | same rule, now returning registry labels (`analysis/valuation.ts:1-8`) |
| Margin of safety | stored mock `29.9` | `(IV − currentPrice) / IV × 100` (`adapter.ts:36-39`) |
| Potential | stored mock string | `gapRatio × 100` or `(IV − price) / price × 100` — explicitly documented as a *different* figure from MoS (`adapter.ts:41-45,850-855`) |
| Method count | always 5 | only methods with a non-null IV and status `VALID`/`APPROXIMATED` (`adapter.ts:844-848`) |
| Per-share metrics | 6 (incl. PEG, Dividend Yield) | 4 (EPS TTM, BVPS, P/E, P/BV) |
| Method naming | product-specific (`Peter Lynch / Adaptive`, `Type & Sector Weighted`) | workbook-derived (`Peter Lynch`, `Weighted IV`, `Mean Reversion PBV [Asset]`, `Dividend Discount Model (Cash Flow)`, `Discounted Earnings Model (Growth)`) with a fixed display order (`valuation-methods.ts:23-29`) |
| Explanation copy | per-stock `explanations[]` | one static 3-lens module (`data/valuation-lenses.ts`) |

## 7. Health / growth / quality comparison

| Aspect | `2480f2b` | `80c3c1d` |
| --- | --- | --- |
| Health score | `overall.score = '80 / 100'`, `rating = 'Healthy'`, `clearance = 'OK'` in the data model | all four fields `"Not available"` (`adapter.ts:961`) |
| Health score rendering | **not rendered** — `overall` is referenced only in `mock.ts` and `adapter.ts`, never in a component | **not rendered** (same) |
| Profitability block (ROE avg/projected/trend, NPM avg, NPM vs avg, ROE StdDev) | 6 metrics in the data model; **not rendered** (no component reads `healthGrowth.profitability`) | `{ metrics: [] }` (`adapter.ts:957`) |
| Liquidity / leverage block (DER, Current Ratio, Interest Coverage, OCF, OCF/NI) | 5 metrics in the data model; **not rendered** (no component reads `healthGrowth.cashFlow`) | `{ metrics: [] }` (`adapter.ts:958`) |
| Forensic / growth-quality block | 10 metrics, rendered | 4 metrics, rendered (`Revenue Coverage`, `Asset Growth Gap`, `Debt Growth Gap`, `Margin Spike`) |
| Forensic context copy language | English | **Indonesian** (`"Periode …: selisih pertumbuhan aset terhadap revenue."`, `adapter.ts:707,713,719,725`) while the surrounding UI is English |
| Quarterly quality summary | real sentence | placeholder sentence (`adapter.ts:960`) |
| Growth metrics shown | 6 CAGR/YoY/momentum values | 6, of which Revenue & EPS come from DB and Net Income 3Y CAGR is hardcoded `"Not available"` |
| Momentum states | `Accelerating` with a tone | binary: `"Accelerating"` or `"Not available"` — no `Slowing`/`Stable` state is produced |
| Growth chart unit | Rp Trillion (mock values already scaled) | Rp Billion (`toBillion` = `/1e9`) |
| Projection period | `2026P` present in the chart | absent |

## 8. Consensus / verdict comparison

| Aspect | `2480f2b` | `80c3c1d` |
| --- | --- | --- |
| Type | `ValuationClassification = "UNDERVALUED" \| "OVERVALUED_MIXED"` | `"UNDERVALUED" \| "OVERVALUED"` (`analysis/backtest.ts:18`) |
| `BacktestConsensus` type | `"UNDERVALUED" \| "OVERVALUED" \| "MIXED"` | unchanged in `mock.ts:379`, but no producer returns `"MIXED"` any more |
| Method consensus rule | `≥ 3` values strictly above the analysis price, over **all** slots | `≥ 3` values strictly above, over **valid** slots only (`0` and `null` excluded) |
| Denominator | always 5 | 3, 4 or 5 depending on how many methods have a usable value |
| MoS consensus rule | `mosMain ≥ 0.30` | identical |
| Verdict source | recomputed in the browser (`calculateSimulatedVerdict`) | stored verdict shown as-is (`backtest-adapter.ts:11-15`) |
| Verdict vocabulary | `WIN, RISK, RECOVERED, FLAT, CONFIRMED, REPRICE, OBSERVE` | identical set, but `OBSERVE` is no longer produced by the simulation branch |
| Outcome panel labels | `Undervalued Outcome` / `Overvalued Outcome` with `WIN, RECOVERED, FLAT, RISK` and `REPRICE, CONFIRMED, OBSERVE` | identical |


## 9. Data-source comparison

| Surface | `2480f2b` source | `80c3c1d` source | Proven by |
| --- | --- | --- | --- |
| Stock detail object | `mock-stock-details.ts` → `mockStockDetails.AUTO` | RPC `get_stock_research_data` → `buildStockDetail` | `stock-research-page.tsx` (old) vs `app/market/[ticker]/page.tsx` |
| Price series | mock `priceChart.points` | `prices_daily.close_price` (≤260 rows, collapsed to months) | `adapter.ts:791-806` |
| Price extremes | mock `low52W` / `high52W` | `Math.min/max` over stored closes | `adapter.ts:833-835` |
| Valuation results | mock `currentValuation.methods` | `valuation_results` via the research RPC | `adapter.ts:838-865` |
| Financial statements | mock `financialHistory` tables | `financial_facts` per period | `adapter.ts:128-289` |
| Annual growth metrics | mock `healthGrowth.growth` | `GROWTH_*` annual metric codes | `adapter.ts:81-88,925-954` |
| Quarterly quality metrics | mock `thesisValidator.rows` | `QUALITY_*` quarterly metric codes | `adapter.ts:90-97,432-433` |
| Forensic metrics | mock strings | `GROWTH_REVENUE_COV`, `GROWTH_ASSET_GROWTH_GAP`, `FORENSIC_DEBT_GROWTH_GAP`, `FORENSIC_MARGIN_SPIKE` | `adapter.ts:676-728` |
| Dividends | mock `dividendConsistency` | `dividend_facts` | `adapter.ts:522-559` |
| Backtest cases | `makeAutoBacktestCase()` seeds | `get_stock_backtest` RPC | `backtest-adapter.ts` |
| Historical Evidence preview | mock `historicalEvidencePreview` (hand-written `4/14`, `10/8`, `100%`, median/best/worst) | **derived, not stored**: `buildHistoricalEvidencePreview(cases)` reuses `aggregateBacktestOverview`, so `totalCases` = the backtest case count and each panel shows `Undervalued` / `Overvalued` plus three rates that add up to 100%: `Win % = (WIN + RECOVERED) / Undervalued`, `Risk % = RISK / Undervalued`, `Flat % = FLAT / Undervalued`. The per-outcome counts, the `outcomeExplanation` banner (`buildBacktestOutcomeExplanation`, now deleted) and `medianReturn` / `bestResult` / `worstResult` / `positiveResults` / `cases` were dropped: no run stores the return statistics, and the rates carry the same information as the counts. | `analysis/historical-evidence.ts`; `adapter.ts:663-668,834-837` |
| Backtest / evidence fallback | n/a (mock was the only source) | `pickDemoBacktestData("AUTO")` only, marked `isDemoData`; its preview is computed from the same sample cases | `adapter.ts:663-688,836-841` |
| Market list | `mockMarketOverviewStocks` | `get_market_overview_page` RPC | `lib/stock-data.ts:543-555` |
| Workbook sample reference | did not exist | `data/workbook-sample-auto.ts` (read-only reference, "nothing here is fed into a calculation") | `workbook-sample-auto.ts:14-17` |

Derived frontend calculations that exist **only** in the current tree (they did not exist at `2480f2b`):
`computeMos`, `computeGap`, `formatCagr`, `badgeFromGrowth`, `buildFinancialHistory` (CAGR, EPS), `buildGrowthVisuals` (YoY), `buildValuationMetrics` (EPS/BVPS/multiples), `buildForensicMetrics`, `buildThesisValidator` (YoY), `buildDividendConsistency`, `buildMonthlyPricePoints`, `yoyForQuarter`, `formatInterestExpense` — all in `adapter.ts`; plus `classifyIntrinsicValuesAbovePrice` zero-exclusion and the single WIN threshold pair in `analysis/backtest.ts`.

## 10. Removed / added / renamed metrics

### Removed (no longer produced anywhere in the current frontend)
`Historical Evidence` key-metric value (wins/total) · `P/E (TTM)` chart stat · `PEG Ratio` · `Dividend Yield` (valuation metric) · valuation `readouts` bullets · Company Profile `listedDate` / `headquarters` / `website` · Financials annual `Operating Profit` · annual `Total Assets` · quarterly `Interest Expense` (metric strip) · annual table rows `Operating Profit`, `EPS`, `Total Assets`, `ROE`, `Gross Margin`, `Net Margin`, `BVPS` · quarterly table rows `Gross Profit`, `Operating Cash Flow`, `Total Equity` · `profitability` block (6 metrics) · `cashFlow` block (5 metrics incl. `Debt to Equity (DER)`, `Current Ratio`, `Interest Coverage`, `Operating Cash Flow`, `OCF / Net Income`) · forensic metrics `Return on Equity (ROE)`, `Gross Margin`, `Quality: CF vs Net Income`, `ROE Trend`, `Equity Growth Consistency`, `Current Asset Growth (YoY)`, `NWC / Revenue (Latest)`, `NWC Intensity Change (YoY)`, `Cash Flow Check` · `quarterlyMeaning` sentence · health score / rating / clearance · Growth Summary `Net Income Growth (3Y CAGR)` value · Dividend `DPR`, `Yield`, `Avg (4Y)`, yield chart series · Market Overview `Verdict`, `MoS`, `Historical Evidence` values · `2026P` projection period in growth visuals · `OBSERVE` as a produced verdict · `OVERVALUED_MIXED` classification.

### Added
`sample-comparison-card.tsx` + `lib/sample-comparison.ts` + `data/workbook-sample-auto.ts` · `UnavailableBadge` · `DemoDataBadge` · `ChartEmptyState` · `market/loading.tsx`, `market/[ticker]/loading.tsx`, `market/[ticker]/not-found.tsx` · `lib/stock-data.ts` · `lib/stock-detail-adapter.ts` · `lib/stock-types.ts` · `lib/valuation-methods.ts` · `lib/backtest-adapter.ts` · `lib/market-page-size.ts` · `utils/dates.ts` · Financials annual metrics `Revenue` and `Total Liabilities` · quarterly metric `Revenue` · forensic metrics `Revenue Coverage`, `Debt Growth Gap`, `Margin Spike` · `recommendationAvailable` flag · `isDemoData` flag · `BacktestCase.stored` / `peakMonth` / `troughMonth` / `methodCode` · server-side page-size control · `notFound()` on unknown ticker.

### Renamed
Valuation method labels (5) · `getMainValuationMethod` return values · Financials `M Rp` → `Rp Billion` / `(Rp Bn)` · annual change column `CAGR (5Y)` → `YoY Change` · quarterly change column `YoY (Latest)` → `QoQ Change` · quarterly trend card CAGR labels → `YoY Growth` · backtest compact headers `Jenis Saham`/`Kuartal`/`TGL ANALISIS`/`Harga Analisis` → `Stock Type`/`Quarter`/`ANALYSIS DATE`/`Analysis Price` · `IV DIVIDEND DISCOUNT MODEL` → `IV DDM` · `UNDERVALUED_MIXED` → `OVERVALUED` · Growth `periodOptions` `All Years/5 Years/3 Years` → `Quarterly` · growth chart unit `Rp Trillion` → `Rp Billion`.


## 11. Potential regressions

These are **differences a reader could reasonably read as breakage**, stated without judging whether the new behaviour is better.

1. **`YTD` now means day-over-day.** `priceChart.ytdPercent` is set from `changePercent`, which is last close vs previous close (`adapter.ts:824-825,901`). The label still reads `YTD`. In the sample data it was `-12.4` with the same label. Meaning changed while the label stayed.
2. **Market Overview Verdict / MoS / Historical Evidence are now always empty.** `lib/stock-data.ts:254-258` hardcodes `verdict: "Not available"`, `mos: null`, `evidenceWins: null`, `evidenceTotal: null`, so three of the four card blocks render `UnavailableBadge` for every row, including the AUTO row that has full research data.
3. **`Historical Evidence` key metric is always "Not available"** on the stock page, because `adapter.ts:882-883` sets both fields to `null` — even for AUTO, whose demo backtest data is loaded on the same page.
4. **`P/E (TTM)` is dead.** `adapter.ts:904` sets `peTTM: null` unconditionally, so the chart stat can never render a number.
5. **Health score, business quality, market mood, strategic target and ideal price have no producer.** `overall` is `Not available` (`adapter.ts:961`); `market_adj_price`, `quality_adj_target`, `mos_final` are out of scope by design (`docs/BACKTEST_ARCHITECTURE.md:594`; `docs/archive/PHASE4_CALCULATION_BLUEPRINT.md:1544`). None of these was rendered at `2480f2b` either, so the visible delta is limited to the emptied data model.
6. **DER, Current Ratio and Interest Coverage disappeared from the data model.** They existed only inside `healthGrowth.cashFlow`, which no component rendered at `2480f2b` either, and which is now `{ metrics: [] }` (`adapter.ts:958`). Liquidity/leverage therefore has no home in the current `StockDetail`.
7. **Forensic block shrank from 10 metrics to 4**, and the 4 new/kept ones carry **Indonesian** context strings while the rest of the UI is English (`adapter.ts:707,713,719,725`).
8. **Dividend DPR and Yield always render `—`** because the adapter emits only a `DPS [Rp]` row (`adapter.ts:544-554`) while `dividend-consistency-card.tsx:13-15` looks for `DPR [%]` and `Yield [%]`. The Growth-tab dividend chart's yield axis is consequently all-zero (`docs/SUPABASE_MANUAL_RUNBOOK.md:718`).
9. **Valuation tab lost two metrics** (`PEG Ratio`, `Dividend Yield`) and the per-method status is now a binary `UNDERVALUED`/`OVERVALUED`, so a "fair value" method can only be reported as one of two states.
10. **Financials tables lost most rows**: annual 11 → 5, quarterly 5+ → 2. `EPS`, `BVPS`, `ROE`, `Gross Margin`, `Net Margin`, `Operating Profit` and `Total Assets` are no longer tabulated, and the quarterly `QoQ Change` column is hardcoded `"Not available"` (`adapter.ts:240`).
11. **`Net Income Growth (3Y CAGR)` is hardcoded "Not available"** in the Growth Summary card (`adapter.ts:573-578`), so a headline card shows one blank of three.
12. **Momentum can only be "Accelerating" or "Not available"** (`adapter.ts:937-941,950-954`); the sample data had a real tone and other states existed conceptually.
13. **Growth visuals no longer include the projection year** and switched unit from Rp Trillion to Rp Billion, so the same card now shows numbers 1000× smaller with a different axis label.
14. **Backtest history exists only for AUTO.** `pickDemoBacktestData` returns nothing for any other ticker (`adapter.ts:665-667`), so every non-AUTO stock page shows an empty Backtest tab and a "Not available" Historical Evidence card.
15. **Backtest consensus denominator changed** from a fixed `/5` to `/3`, `/4` or `/5` depending on how many methods have a non-zero value. The displayed `x/y` is not comparable with the sample-data value for the same case.
16. **Backtest WIN thresholds changed** from two pairs to one pair (`+20%/−15%`), so the same historical case can change verdict.
17. **`recommendationAvailable: false`** is a new flag that no UI reads; it is a latent signal that recommendations are intentionally absent.
18. **`mockMarketOverviewStocks` and `mockStockDetails.AUTO` are now mostly dead code** (`mockMarketOverviewStocks` is never imported; `mockStockDetails` is read only through `pickDemoBacktestData`), so the file reads as a live data source while it is not.
19. **Unknown-ticker behaviour is stricter** (404 instead of silently rendering AUTO). Arguably a fix, listed here only because the user-visible behaviour for a mistyped ticker changed.


## 12. Unknown / unresolved differences

| # | Item | Why it cannot be resolved from the source alone |
| --- | --- | --- |
| U1 | Whether the market RPC can ever populate `verdict`, `mos`, `evidence_wins`, `evidence_total` | The mapper hardcodes them (`lib/stock-data.ts:254-258`) regardless of the row payload; the RPC body lives in `supabase/migrations`, not in the frontend. |
| U2 | Whether `yield_ratio` is genuinely NULL for every dividend row | `adapter.ts:533-539` reads it defensively; `docs/SUPABASE_MANUAL_RUNBOOK.md:718` states it is NULL for all rows at the time of writing. Needs a live query to confirm. |
| U3 | Whether any ticker other than AUTO has backtest rows today | `get_stock_backtest` is called for every ticker, but the sample fallback is AUTO-only; only the database can say which tickers have stored cases. |
| U4 | Why `P/E (TTM)` is pinned to `null` | `adapter.ts:904` has no comment explaining it; no P/E fact is requested from the RPC in `buildValuationMetrics`. |
| U5 | Whether the Indonesian forensic context strings are intended | `adapter.ts:707-725` is the only Indonesian copy in the stock-research components; the sample-comparison card is also Indonesian, so it may be deliberate for an Indonesian audience, but the rest of the page is English. |
| U6 | Whether `recommendationAvailable` is intended to gate a future UI | The field is set (`lib/stock-data.ts:255`) and typed (`stock-types.ts:12`) but read by nothing. |
| U7 | The exact unit convention that the old `"M Rp"` label intended | The old label said `M Rp` while `docs/reference/EXCEL_POSTGRES_VALIDATION.md` (cited in `adapter.ts:62-68`) states `1 template unit = 1,000,000,000 IDR`. The old value `9,2` for AUTO 2026-Q2 matches `9,224,000,000 IDR / 1e9`, so the old label was misleading rather than the number being wrong. |
| U8 | Whether `mockStockDetails` should be reduced to only the backtest demo slice | Both `mockMarketOverviewStocks` and the non-backtest parts of `mockStockDetails.AUTO` are unreferenced but still present. |

## 13. Recommended reconciliation areas

Neutral, evidence-based list. Nothing here is an instruction to change code.

1. **Label vs meaning for `YTD`.** Either the field should be renamed to reflect a day-over-day change, or it should be derived from a year-start close. Evidence: `adapter.ts:824-825,901`.
2. **Empty-but-visible market fields.** Decide whether `Verdict`, `MoS` and `Historical Evidence` should stay on the market card while the RPC never supplies them, or be removed from the card until a source exists. Evidence: `lib/stock-data.ts:254-258`.
3. **`Historical Evidence` on the stock page.** The page already loads AUTO's demo backtest; the key metric still reads `null`. Decide whether the metric should reflect the same `isDemoData` source the card uses. Evidence: `adapter.ts:813-816` vs `:882-883`.
4. **`P/E (TTM)`.** Either compute it (price ÷ derived EPS is already available) or drop the tile. Evidence: `adapter.ts:757,904`.
5. **Dividend DPR / Yield rows.** Align the card's row keys with what the adapter emits, or extend the adapter. Evidence: `adapter.ts:544-554` vs `dividend-consistency-card.tsx:13-15`.
6. **`profitability` and `cashFlow` blocks.** Decide whether DER / Current Ratio / Interest Coverage / ROE-average belong in the product; today they exist only as an emptied container and a dead mock string. Evidence: `adapter.ts:957-958`.
7. **Forensic metric language.** Unify the context strings to the language used by the rest of the page. Evidence: `adapter.ts:707,713,719,725`.
8. **Quarterly `QoQ Change` column.** It is currently a hardcoded `"Not available"`; either compute it or drop the column. Evidence: `adapter.ts:240`.
9. **`Net Income Growth (3Y CAGR)`.** A headline card metric that is hardcoded unavailable. Evidence: `adapter.ts:573-578`.
10. **Growth chart unit.** Confirm whether Rp Billion is the intended presentation unit, since the same card previously used Rp Trillion. Evidence: `adapter.ts:385-386`, `growth-tab-content.tsx:294`.
11. **Backtest coverage.** Confirm that an empty Backtest tab (and therefore an empty Historical Evidence preview) is the intended state for a ticker with no stored run. Evidence: `adapter.ts:677-682`. The preview now appears for every ticker that *does* have a backtest, not only AUTO.
12. **Consensus denominator documentation.** The `/3`, `/4`, `/5` behaviour is intentional and documented in code (`analysis/backtest.ts:38`); it may still deserve a visible note where the `x/y` figure is shown. Evidence: `analysis/backtest.ts:30-41`, `countMethodsAboveAnalysisPrice` at `:162-165`.
13. **Dead sample data.** Decide whether `mockMarketOverviewStocks` and the unused parts of `mockStockDetails.AUTO` should be reduced to the backtest demo slice so the file stops looking like a live source. Evidence: `mockMarketOverviewStocks` has no importer; `mockStockDetails` is imported only by `adapter.ts:4` for `pickDemoBacktestData`.
14. **Product-concept metrics with no producer.** `PRODUCT_CONTEXT.md` lists "valuation consensus" and the archive blueprint lists health score, business quality, market mood, strategic target and ideal price. None is currently produced. Evidence: `docs/PRODUCT_CONTEXT.md:96`, `docs/archive/PHASE4_CALCULATION_BLUEPRINT.md:660-663,1544`, `adapter.ts:961`.
15. **`recommendationAvailable`.** Either wire it up or remove it. Evidence: `lib/stock-data.ts:255`, `stock-types.ts:12`.


---

## Addendum — 2026-10-02: stock type per case (D7 closed)

The backtest now recomputes the stock type on **each case's own analysis date**
instead of copying today's snapshot to every case
(`docs/BACKTEST_ARCHITECTURE.md` D7, `docs/SUPABASE_MANUAL_RUNBOOK.md` 1.4.0).

Effect on this audit:

- **Row 115 (Backtest cases)** and **row 341 (Historical Evidence preview)** are
  unchanged as *contracts*: both still read `get_stock_backtest` and
  `buildBacktestCase`. What changes is the **value** of `stock_type` per case, and
  therefore the MoS / consensus / verdict / win-rate figures derived from it, for
  GOLD, WIFI, GEMA, INDF, JSMR, SIDO, INDS, UNTR and INKP.
- **No "not point-in-time" badge exists in the frontend.** `BacktestCaseData.flags`
  is carried through `lib/stock-data.ts:499` but nothing renders it
  (`stock-detail-adapter.ts:77` only mentions a flag name in a comment). Removing
  `STOCK_TYPE_LATEST_SNAPSHOT` therefore changes no markup: the array simply no
  longer contains that string on new rows. Stored rows keep it in their own
  `flags`.
- **Row 13 (Stock Character)** reads `stockType` from the newest *valuation*
  method row, not from the backtest, so it is unaffected by D7.
- A ticker whose classifier finds no matching rule on a case's date (GOLD, JSMR,
  INDF) now gets `stock_type = null` for that case and a `VALUATION_UNAVAILABLE`
  valuation, so its Backtest tab shows an empty case rather than a guessed type.
  Its price metrics are still present.

No frontend file was changed for this addendum.


---

## Addendum — 2026-10-02: Dividend DPR and Yield rows are now produced

Rows 108, 109, 111, 112, 113 and potential-regression 8/13 recorded that the
Dividend Consistency card could only ever render `—` for DPR and Yield, because
the adapter emitted a single `DPS [Rp]` row while the card looks for `DPR [%]`
and `Yield [%]`. That gap is now closed.

The two ratios are computed by the backend as **stored annual results**, not in
the browser:

| Item | Value | Where it comes from |
| --- | --- | --- |
| `DIVIDEND_PAYOUT_RATIO` | `DPS / EPS` | `calc_annual_growth_quality`, one row per annual snapshot. Excel `DataInput!B28` = `B26/B30`. |
| `DIVIDEND_YIELD` | `DPS / year-end close` | Same table. Excel `DataInput!B29` = `B26/B25`. |

They are stored rather than derived in the adapter because the yield denominator
is a **point-in-time year-end close** (blueprint §5.8 marks this *critical*), and
the research RPC only ships the trailing 260 price rows — for GEMA that window
starts in August 2025, so no 31 December close for 2022–2025 is present in the
payload at all.

Effect on this audit:

- **Row 108 (Dividend Yield)** and **row 109 (DPR)** move from REMOVED to
  **restored**, sourced from the calculation layer instead of the mock.
- **Row 111 (Avg (4Y))** is restored. The workbook's cell is the mean of the
  five displayed columns (projection + four fiscal years), verified against the
  sample workbooks: BIRD DPS `(85.988+120+91+72+60)/5 = 85.7977`.
- **Row 112 (Yield series)** no longer reads `dividend_facts.yield_ratio`
  (NULL for every row); it reads the stored `DIVIDEND_YIELD` metric, so the
  Growth-tab chart's yield axis is no longer all-zero.
- **Row 113 (callout)** is now generated from what the data actually holds, so
  it states plainly when a ratio could not be computed instead of a blanket
  "not available yet".
- **Unknown U2** (`yield_ratio` genuinely NULL) is answered: yes, it is NULL for
  all 101 rows, which is why the provider column is not used.
- **Recommended area 5** ("align the card's row keys or extend the adapter") is
  resolved by extending the adapter.

Verification against the workbook, GEMA:

| Year | DPS | DPR computed | DPR workbook | Yield computed | Yield workbook |
| --- | --- | --- | --- | --- | --- |
| 2024 | 5 | 43.6% | 43.6% | 3.09% | 3.1% |
| 2025 | 3 | 22.6% | 22.6% | 3.09% | 3.1% |
| 2020 | 5 | 632.9% | 634.6% | 1.45% | 1.4% |

The 2020 payout difference is the provider's rounded `OUTSTANDING_SHARES`
(the workbook EPS for that year is `0.8`), not a formula difference.

Two supporting changes were required and are documented in
`docs/SUPABASE_MANUAL_RUNBOOK.md` (section 1.5):

1. `populate_growth_quality.py` now reads `dividend_facts` and `prices_daily`
   and includes them in the run's `input_snapshot`, so a changed dividend or a
   restated price creates a new run instead of leaving the stored ratio stale.
2. `supabase/migrations/0028_stock_research_latest_growth_run.sql` pins the RPC's
   growth and quality reads to the newest `QUARTERLY_GROWTH_QUALITY` run. Without
   it, adding an input to the snapshot creates a *second* run and the RPC — which
   joined on `instrument_id` alone — would return every annual metric twice.
   This is the same defect `0021` fixed for valuations and `0026` for the
   backtest.

Frontend files changed: `frontend/src/lib/stock-detail-adapter.ts` only
(`buildDividendConsistency` and the new `buildDividendCallout`).


---

## Appendix A — File-level diff summary (`2480f2b` → `80c3c1d`, `frontend/` only)

39 files, 3760 insertions, 321 deletions. 17 added, 22 modified.

**Added (17):** `frontend/src/app/market/[ticker]/loading.tsx`, `frontend/src/app/market/[ticker]/not-found.tsx`, `frontend/src/app/market/loading.tsx`, `frontend/src/components/stock-research/sample-comparison-card.tsx`, `frontend/src/components/ui/chart-empty-state.tsx`, `frontend/src/components/ui/demo-data-badge.tsx`, `frontend/src/components/ui/unavailable-badge.tsx`, `frontend/src/data/valuation-lenses.ts`, `frontend/src/data/workbook-sample-auto.ts`, `frontend/src/lib/backtest-adapter.ts`, `frontend/src/lib/market-page-size.ts`, `frontend/src/lib/sample-comparison.ts`, `frontend/src/lib/stock-data.ts`, `frontend/src/lib/stock-detail-adapter.ts`, `frontend/src/lib/stock-types.ts`, `frontend/src/lib/valuation-methods.ts`, `frontend/src/utils/dates.ts`.

**Modified (22):** `frontend/package.json`, `frontend/package-lock.json`, `frontend/src/app/market/page.tsx`, `frontend/src/app/market/[ticker]/page.tsx`, `frontend/src/components/market-overview-page.tsx`, 13 files under `frontend/src/components/stock-research/` (`backtest-tab-content`, `current-valuation-card`, `financial-health-card`, `financial-trend-card`, `financials-tab-content`, `growth-tab-content`, `historical-evidence-preview-card`, `historical-growth-section`, `key-metric-card`, `price-chart-card`, `stock-header`, `stock-research-page`, `valuation-tab-content`), `frontend/src/data/mock-stock-details.ts`, `frontend/src/lib/analysis/backtest.ts`, `frontend/src/lib/analysis/valuation.ts`, `frontend/src/utils/currency.ts`.

**Unchanged** (present in both trees, absent from the diff): the 5 analysis modules were already in `lib/analysis/` at `2480f2b`, so `backtest-overview.ts`, `growth.ts` and `index.ts` are byte-identical; `backtest.ts` and `valuation.ts` changed only as recorded in rows 11 and 119-129. Stock-research components not touched by the diff: `backtest-overview.tsx`, `breadcrumb.tsx`, `company-profile-card.tsx`, `disclaimer-footer.tsx`, `dividend-consistency-card.tsx`, `financial-metrics-summary.tsx`, `growth-summary-card.tsx`, `historical-financial-table.tsx`, `overview-tab-content.tsx`, `research-summary-card.tsx`, `research-tabs.tsx`, `thesis-validator-card.tsx`. Shared UI not touched: `app-shell.tsx`, `components/ui/research-section.tsx`, `section-card.tsx`, `status-badge.tsx`.

## Appendix B — How to run both versions side by side (optional, not performed)

Both versions are Next.js apps under `frontend/` with the same `dev` script (`"dev": "next dev"`), so they can coexist from two worktrees. Nothing below was executed during this audit.

```powershell
# Historical (sample data) - read-only worktree, never checked out into the main tree
git worktree add "$env:TEMP\stocklens-hist" 2480f2b
cd "$env:TEMP\stocklens-hist\frontend"
npm install            # 2480f2b has no @supabase/supabase-js dependency
npm run dev -- -p 3001 # http://localhost:3001  (no .env needed: 100% mock data)

# Current (database-backed) - the existing working copy
cd "D:\Stock Analyzer\frontend"
npm install            # adds @supabase/supabase-js, server-only
npm run dev -- -p 3000 # http://localhost:3000  (requires .env with the Supabase URL + publishable key)
```

`git worktree add` creates a second working directory without touching the current tree, and `git worktree remove "$env:TEMP\stocklens-hist"` cleans it up. The current version cannot start without the Supabase environment variables because `lib/stock-data.ts` imports `server-only` and reads them at request time.

## Appendix C — Commands used (all read-only)

```text
git log --oneline --decorate --all -- frontend
git log --oneline --decorate --all -- frontend/src/data/mock-stock-details.ts
git log --oneline --all --diff-filter=A -- frontend/src/data/mock-stock-details.ts
git log --oneline --first-parent HEAD
git rev-list --parents -1 HEAD
git merge-base --is-ancestor <commit> HEAD
git ls-tree -r --name-only <commit> -- frontend
git show <commit>:<path>
git diff --name-status 2480f2b 80c3c1d -- frontend
git diff --stat 2480f2b 80c3c1d -- frontend
git grep -l -i supabase 2480f2b -- frontend
git archive --format=tar --output=<tmp> <commit> frontend   # then tar -xf
git status --short
```


