import "server-only";

import type { BacktestCaseData } from "@/lib/stock-data";
import type { BacktestCase, BacktestVerdict } from "@/data/stock-detail-types";
import { valuationMethodLabel } from "@/lib/valuation-methods";

/**
 * Turn stored backtest rows into the `BacktestCase[]` shape the tab already
 * renders.
 *
 * The verdicts are **displayed as stored**: the stored verdict is the workbook
 * formula (docs section 5.4.1). The browser-side recomputation was removed with
 * the entry-price simulation (it disagreed on three branches, D4), so nothing in
 * the UI can resurrect the drift the backend verdict removed.
 *
 * The consensus badge is passed through for the same reason. The stored column
 * has three states (`UNDERVALUED`, `OVERVALUED`, `N/A`) while a two-branch
 * browser rule can only ever produce two, because the browser does not know the
 * "at least three valid methods" threshold. Recomputing it displayed the wrong
 * badge on 44 stored cases (docs/CONSENSUS_ARCHITECTURE.md section 2.3).
 */

/** Quarter format: stored `2022-Q1` -> displayed `2022 Q1`. */
function displayQuarter(caseQuarter: string): string {
  return caseQuarter.replace("-Q", " Q");
}

function toVerdict(value: string | null): BacktestVerdict {
  const allowed: BacktestVerdict[] = [
    "WIN", "RISK", "RECOVERED", "FLAT", "CONFIRMED", "REPRICE", "OBSERVE",
  ];
  return allowed.includes(value as BacktestVerdict) ? (value as BacktestVerdict) : "FLAT";
}

/**
 * Date `months` months after `analysisDate`, matching the UTC month arithmetic
 * `monthsBetween` in `@/lib/analysis/backtest` uses (it compares year/month
 * only, so the day-of-month is irrelevant to it).
 *
 * Day 15 is used for every offset except 0. The reason is the same one
 * `makeAutoBacktestCase` documents: an end-of-month analysis date such as
 * `2022-03-31` plus one month overflows into the next month, so a day that
 * cannot overflow keeps the arithmetic honest. Offset 0 is pushed one day
 * forward so it still counts as "after the analysis date" for the window filter.
 */
function dateAtMonthOffset(analysisDate: string, months: number): string {
  const start = new Date(`${analysisDate}T00:00:00Z`);
  if (months === 0) return new Date(start.getTime() + 24 * 60 * 60 * 1000).toISOString().slice(0, 10);
  return new Date(Date.UTC(start.getUTCFullYear(), start.getUTCMonth() + months, 15))
    .toISOString()
    .slice(0, 10);
}

/**
 * Build the price path the tab's helpers walk.
 *
 * The stored table keeps only the window extremes (four horizon high/low pairs,
 * the peak, and the trough), not the underlying daily bars. This rebuilds a
 * path from exactly those stored numbers so that everything the UI derives from
 * it comes back out equal to what is stored:
 *
 *   * one point per horizon (3/6/9/12M) carrying the stored `high_nm`/`low_nm`,
 *     which reproduces `Ret nM` and `Price nM`;
 *   * one point per extreme, dated at its stored month, which reproduces
 *     `Ret Peak`/`Ret Down`, `Peak Price`/`Trough Price`, `Peak Month`/`Trough Month`.
 *
 * Ties resolve correctly without extra work: `peak_month`/`trough_month` are the
 * months of the *first* date reaching the extreme, so sorting by date puts the
 * extreme point before any horizon point sharing its value, and the tab's
 * helpers take the first match.
 *
 * `close` is not stored per horizon. It is set to the horizon high, which only
 * affects the two legacy tables (`DetailTable`, `CompactTableLegacy*`) that are
 * no longer rendered.
 */
function buildPricePath(testCase: BacktestCaseData): BacktestCase["pricePath"] {
  const byDate = new Map<string, { high: number; low: number }>();
  const add = (months: number, high: number | null, low: number | null) => {
    if (high === null && low === null) return;
    const date = dateAtMonthOffset(testCase.analysisDate, months);
    const existing = byDate.get(date);
    byDate.set(date, {
      high: Math.max(existing?.high ?? -Infinity, high ?? -Infinity),
      low: Math.min(existing?.low ?? Infinity, low ?? Infinity),
    });
  };

  const horizons: [number, number | null, number | null][] = [
    [3, testCase.high3m, testCase.low3m],
    [6, testCase.high6m, testCase.low6m],
    [9, testCase.high9m, testCase.low9m],
    [12, testCase.high12m, testCase.low12m],
  ];
  for (const [months, high, low] of horizons) add(months, high, low);

  if (testCase.peakMonth !== null) add(testCase.peakMonth, testCase.peakPrice, null);
  if (testCase.troughMonth !== null) add(testCase.troughMonth, null, testCase.troughPrice);

  return [...byDate]
    .sort(([left], [right]) => left.localeCompare(right))
    .map(([date, value]) => ({
      date,
      high: Number.isFinite(value.high) ? value.high : (value.low as number),
      low: Number.isFinite(value.low) ? value.low : (value.high as number),
      close: Number.isFinite(value.high) ? value.high : (value.low as number),
    }));
}

export function buildBacktestCase(
  testCase: BacktestCaseData,
  ticker: string,
  sectorName: string | null,
): BacktestCase {
  return {
    id: testCase.caseId,
    ticker,
    quarter: displayQuarter(testCase.caseQuarter),
    analysisDate: testCase.analysisDate,
    analysisPrice: testCase.analysisPrice ?? 0,
    sector: sectorName ?? "Not available",
    stockType: testCase.stockType ?? "Not available",
    mosMain: testCase.mosMain,
    mosPeter: testCase.mosPeter,
    mosWeight: testCase.mosWeight,
    consensus: testCase.consensus,
    consensusUndervalued: testCase.consensusUndervalued,
    consensusValid: testCase.consensusValid,
    peakMonth: testCase.peakMonth,
    troughMonth: testCase.troughMonth,
    stored: {
      high3m: testCase.high3m,
      low3m: testCase.low3m,
      high6m: testCase.high6m,
      low6m: testCase.low6m,
      high9m: testCase.high9m,
      low9m: testCase.low9m,
      high12m: testCase.high12m,
      low12m: testCase.low12m,
      peakPrice: testCase.peakPrice,
      troughPrice: testCase.troughPrice,
      returnPeak: testCase.returnPeak,
      returnDown: testCase.returnDown,
    },
    verdict: toVerdict(testCase.verdict),
    verdictMos: toVerdict(testCase.verdictMos),
    methods: testCase.methods.map((method) => ({
      method: valuationMethodLabel(method.methodCode),
      methodCode: method.methodCode,
      intrinsicValue: method.intrinsicValue,
      calculationStatus: method.calculationStatus,
      flags: method.flags,
      details: method.details,
    })),
    context: {
      revenueYoY: testCase.context.revenueYoY,
      netIncomeYoY: testCase.context.netIncomeYoY,
      epsMomentum: testCase.context.epsMomentum ?? "Not available",
      revenueMomentum: testCase.context.revenueMomentum ?? "Not available",
      roeTrend: testCase.context.roeTrend ?? "Not available",
      yield: testCase.context.yield,
      ocfNi: testCase.context.ocfNi,
    },
    pricePath: buildPricePath(testCase),
  };
}

