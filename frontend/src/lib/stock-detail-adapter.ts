import "server-only";

import type { BacktestData, StockResearchData, FinancialPeriod, ValuationMethod, StockPrice } from "@/lib/stock-data";
import { mockStockDetails, type BacktestCase, type EvidenceOutcomeBreakdown, type StockDetail } from "@/data/mock-stock-details";
import { toMonthIndex, toMonthLabel } from "@/utils/dates";
import { sortValuationMethods, valuationMethodLabel, type ValuationMethodCode } from "@/lib/valuation-methods";
import { buildBacktestCase } from "@/lib/backtest-adapter";
import {
  buildHistoricalEvidencePreview,
  EVIDENCE_RATE_UNAVAILABLE,
  evidenceWinRatePercent,
  formatEvidencePercent,
  preferredMainMethodCode,
} from "@/lib/analysis";

const UNAVAILABLE = "Not available";

function mapVerdict(dbVerdict: string | undefined): StockDetail["verdict"] {
  switch (dbVerdict) {
    case "UNDERVALUED":
      return "Undervalued";
    case "OVERVALUED":
      return "Overvalued";
    case "AT_FAIR_VALUE":
      return "Fairly Valued";
    default:
      return "Not available";
  }
}

/**
 * Pick the row that carries the "Main" badge and supplies the headline IV / MoS.
 *
 * The workbook's main rule for the stock type wins when it has a usable value.
 * When it does not (`IV <= 0`), the **other** main-rule candidate takes over
 * instead of leaving the headline empty: the two candidates are the same pair
 * the workbook offers for `SUMMARY!B69`, so the fallback stays inside the
 * documented rule set rather than inventing a new one.
 *
 * GEMA is the case that motivated this: it is a `TURN AROUND`, so Peter Lynch is
 * its main rule, but Peter Lynch values it at `−22`. Its headline therefore comes
 * from Weighted IV (`32.74`), and the badge moves with it — otherwise the table
 * would show "Main" on a row whose number nothing else uses.
 *
 * A stock with no usable value from either candidate keeps `null`, so the screen
 * reports "not available" instead of picking a method at random.
 */
function pickMainMethod(
  methods: ValuationMethod[],
  stockType: string,
): ValuationMethod | null {
  const preferredCode = preferredMainMethodCode(stockType);
  const alternativeCode: ValuationMethodCode =
    preferredCode === "PETER_LYNCH" ? "TYPE_SECTOR_WEIGHTED" : "PETER_LYNCH";

  const usable = (method: ValuationMethod | undefined) =>
    method != null && method.intrinsicValue != null && method.intrinsicValue > 0;

  const byCode = (code: ValuationMethodCode) =>
    methods.find((method) => method.methodCode === code);

  if (usable(byCode(preferredCode))) return byCode(preferredCode) ?? null;
  if (usable(byCode(alternativeCode))) return byCode(alternativeCode) ?? null;

  // Neither main-rule candidate produced a value. Falling back to any other
  // method would change what "main" means, so the headline stays unavailable.
  return null;
}

/**
 * Margin of safety for one method: `(IV − price) / IV`, as a percentage.
 *
 * The divisor is the intrinsic value, not the price (workbook `SUMMARY`, D6), so
 * the ratio is only defined for a **positive** IV:
 *
 *   * `IV = 0` — undefined; the workbook writes `⚪ N/A (Skip)` and the backend
 *     flags `MOS_DENOMINATOR_ZERO`.
 *   * `IV < 0` — the divisor's sign flips the whole ratio. GEMA's Peter Lynch IV
 *     of `−22.03` against a price of `93` would produce `+522%`, which reads as a
 *     huge discount when the model actually values the company far *below* its
 *     price. The backend marks `IV <= 0` as `NOT_APPLICABLE` for the same reason.
 *
 * Returning `null` here is what makes the row render "Not available" instead of
 * a sign-flipped number. The backtest keeps negative IVs in its own consensus
 * (decision D5) through a separate code path, so this guard does not touch it.
 */
function computeMos(intrinsicValue: number | null, currentPrice: number | null): number | null {
  if (intrinsicValue == null || currentPrice == null) return null;
  if (intrinsicValue <= 0) return null;
  return ((intrinsicValue - currentPrice) / intrinsicValue) * 100;
}

function methodDisplayName(methodCode: string): string {
  return valuationMethodLabel(methodCode);
}

/**
 * Status shown for one valuation-method row.
 *
 * The two non-positive cases are treated **differently on purpose**, mirroring
 * the backtest engine (decision D5 in `docs/BACKTEST_ARCHITECTURE.md`):
 *
 *   * `IV = 0` — the model produced nothing (DDM for a company that has never
 *     paid a dividend), so it is `SKIPPED` and kept out of the comparison. The
 *     backtest drops these rows from its consensus denominator for the same
 *     reason: a stock without dividends yields `3|4`, not `3|5`.
 *   * `IV < 0` — the model *did* produce a value, and a negative one is a real
 *     statement (the company is worth less than nothing by that model), so it
 *     stays `OVERVALUED`. The backtest keeps these rows valid and counts them
 *     the same way.
 *
 * Only the margin of safety is withheld for `IV < 0`, because `(IV − price)/IV`
 * flips sign when the divisor is negative. The status is not withheld.
 */
function methodStatus(
  intrinsicValue: number,
  storedVerdict: string,
): import("@/data/mock-stock-details").ValuationMethodStatus {
  if (intrinsicValue === 0) return "SKIPPED";
  if (intrinsicValue < 0) return "OVERVALUED";
  if (storedVerdict === "NOT_APPLICABLE") return "SKIPPED";
  return storedVerdict === "UNDERVALUED" ? "UNDERVALUED" : "OVERVALUED";
}

/**
 * Display form of a Historical Evidence headline. `null` (no Undervalued case,
 * or no backtest at all) becomes `EVIDENCE_RATE_UNAVAILABLE` rather than `0%`,
 * which would read as "the thesis failed every time".
 */
function formatEvidenceWinRate(
  breakdown: EvidenceOutcomeBreakdown | undefined,
): string {
  if (!breakdown) return EVIDENCE_RATE_UNAVAILABLE;
  const percent = evidenceWinRatePercent(breakdown);
  return percent == null
    ? EVIDENCE_RATE_UNAVAILABLE
    : formatEvidencePercent(percent);
}

function formatPercentSigned(value: number | null): string {
  if (value == null || !Number.isFinite(value)) return UNAVAILABLE;
  const sign = value > 0 ? "+" : "";
  return `${sign}${value.toFixed(2).replace(".", ",")}%`;
}

function formatCagr(value: number | null): string {
  if (value == null || !Number.isFinite(value)) return UNAVAILABLE;
  return `${(value * 100).toFixed(1).replace(".", ",")}%`;
}

/**
 * Interest expense is stored in full IDR. The workbook's "M Rp" columns are
 * actually **billions** of IDR (see docs/reference/EXCEL_POSTGRES_VALIDATION.md
 * §"Unit reality check": `1 template unit = 1,000,000,000 IDR`), so the value is
 * scaled by 1e9 to reproduce the workbook number exactly — e.g. AUTO 2026-Q2
 * 9,224,000,000 IDR -> 9,224.
 */
function formatInterestExpense(value: number | null): string {
  if (value == null || !Number.isFinite(value)) return UNAVAILABLE;
  return (value / 1_000_000_000).toFixed(2).replace(".", ",");
}

function badgeFromGrowth(value: number | null): "Positive" | "Stable" | "Caution" {
  if (value == null) return "Stable";
  if (value > 0.05) return "Positive";
  if (value < 0) return "Caution";
  return "Stable";
}

function findAnnualMetric(
  data: StockResearchData,
  code: string,
): { value: number | null; periodLabel: string } {
  const rows = data.annualGrowth.filter((row) => row.metricCode === code);
  const latest = rows.at(-1);
  return { value: latest?.value ?? null, periodLabel: latest?.periodLabel ?? UNAVAILABLE };
}

function findQuarterlyMetric(
  data: StockResearchData,
  code: string,
): { value: number | null; periodLabel: string } {
  const rows = data.quarterlyQuality.filter((row) => row.metricCode === code);
  const latest = rows.at(-1);
  return { value: latest?.value ?? null, periodLabel: latest?.periodLabel ?? UNAVAILABLE };
}

function trendToneFromValue(value: number | null): "green" | "slate" | "yellow" | "red" {
  if (value == null) return "slate";
  if (value > 0) return "green";
  if (value < 0) return "red";
  return "slate";
}

const METRIC_LABELS: Record<string, string> = {
  REVENUE: "Revenue",
  EARNINGS: "Net Income",
  GROSS_PROFIT: "Gross Profit",
  COST_OF_REVENUE: "Cost of Revenue",
  OPERATING_CASH_FLOW: "Operating Cash Flow",
  TOTAL_CURRENT_ASSET: "Total Current Assets",
  CURRENT_LIABILITIES: "Current Liabilities",
  TOTAL_LIABILITIES: "Total Liabilities",
  TOTAL_EQUITY: "Total Equity",
  OUTSTANDING_SHARES: "Outstanding Shares",
};

function factValue(period: FinancialPeriod | undefined, code: string): number | null {
  return period?.facts.find((f) => f.metricCode === code)?.value ?? null;
}

function toRpTrillion(value: number | null): number {
  if (value == null) return 0;
  return value / 1_000_000_000_000;
}

function buildFinancialHistory(periods: FinancialPeriod[]): StockDetail["financialHistory"] {
  const annualPeriods = periods
    .filter((p) => p.periodType === "ANNUAL")
    .sort((a, b) => a.periodEnd.localeCompare(b.periodEnd));
  const quarterlyPeriods = periods
    .filter((p) => p.periodType === "QUARTER")
    .sort((a, b) => a.periodEnd.localeCompare(b.periodEnd))
    .slice(-8);

  if (annualPeriods.length === 0) return undefined;

  const yearLabel = (p: FinancialPeriod) => p.periodLabel;

  // A series only carries periods where the metric actually exists, so a chart
  // can never draw a fake zero for a year whose fact is missing.
  const buildSeries = (metricCode: string, source: FinancialPeriod[]) =>
    source
      .map((p) => ({ year: yearLabel(p), value: factValue(p, metricCode) }))
      .filter((point): point is { year: string; value: number } => point.value != null)
      .map((point) => ({ year: point.year, value: toRpTrillion(point.value) }));

  const latestAnnual = annualPeriods.at(-1)!;

  // The displayed window spans `length - 1` year-over-year steps, which is what
  // a CAGR must divide by. The label used to print `length` ("CAGR (7Y)" for six
  // steps), overstating every rate it described.
  const yearsSpanned = Math.max(annualPeriods.length - 1, 0);

  // Shares are carried forward from the most recent year that reported them,
  // mirroring `buildValuationMetrics` below and the backend's
  // `annual_share_count`. The provider leaves `OUTSTANDING_SHARES` null for some
  // tickers' latest year (BIRD 2025), and treating that as "no EPS/BVPS at all"
  // blanked a trend card and two table columns.
  const sharesForIndex = (index: number): number | null => {
    for (let i = index; i >= 0; i -= 1) {
      const shares = factValue(annualPeriods[i], "OUTSTANDING_SHARES");
      if (shares != null && shares > 0) return shares;
    }
    return null;
  };

  const perYear = (fn: (period: FinancialPeriod, index: number) => number | null) =>
    annualPeriods.map((period, index) => fn(period, index));

  /** A raw fact per year, e.g. revenue or total equity. */
  const factSeries = (metricCode: string) =>
    perYear((period) => factValue(period, metricCode));

  /** A ratio per year, refused when either side is absent or the divisor is 0. */
  const ratioSeries = (numeratorCode: string, denominatorCode: string) =>
    perYear((period) => {
      const numerator = factValue(period, numeratorCode);
      const denominator = factValue(period, denominatorCode);
      if (numerator == null || denominator == null || denominator === 0) return null;
      return numerator / denominator;
    });

  /** A per-share value per year, e.g. EPS = earnings / shares. */
  const perShareSeries = (metricCode: string) =>
    perYear((period, index) => {
      const value = factValue(period, metricCode);
      const shares = sharesForIndex(index);
      if (value == null || shares == null || shares <= 0) return null;
      return value / shares;
    });

  /**
   * CAGR across the displayed window. Both endpoints must be positive, so a
   * series that starts or ends in a loss reports "Not available" rather than an
   * imaginary root of a negative number.
   */
  const windowCagr = (series: (number | null)[]): string => {
    const first = series[0];
    const last = series[series.length - 1];
    if (
      first == null || last == null || first <= 0 || last <= 0 || yearsSpanned <= 0
    ) {
      return UNAVAILABLE;
    }
    return formatCagr(Math.pow(last / first, 1 / yearsSpanned) - 1);
  };

  const money = (value: number | null) =>
    value == null ? UNAVAILABLE : toRpTrillion(value).toFixed(2);
  const amount = (value: number | null) =>
    value == null ? UNAVAILABLE : value.toFixed(2);
  const percent1 = (value: number | null) =>
    value == null ? UNAVAILABLE : `${(value * 100).toFixed(1).replace(".", ",")}%`;

  // EPS is derived per year (earnings / outstanding shares). A year missing
  // either input is skipped, so the series can never claim a value it lacks.
  const epsValues = perShareSeries("EARNINGS");
  const epsSeries = annualPeriods
    .map((p, index) => ({ year: yearLabel(p), value: epsValues[index] }))
    .filter((point): point is { year: string; value: number } => point.value != null);
  const latestEps = epsValues.at(-1) ?? null;

  const cagrLabel = yearsSpanned > 0 ? `CAGR (${yearsSpanned}Y)` : "CAGR";

  const annualTrendCards: NonNullable<StockDetail["financialHistory"]>["annualTrendCards"] = [
    {
      id: "revenue",
      title: "Revenue",
      unit: "Rp Trillion",
      latestValue: toRpTrillion(factValue(latestAnnual, "REVENUE")).toFixed(2),
      cagrLabel,
      cagrValue: windowCagr(factSeries("REVENUE")),
      subtext: "Annual revenue trend",
      series: buildSeries("REVENUE", annualPeriods),
    },
    {
      id: "netIncome",
      title: "Net Income",
      unit: "Rp Trillion",
      latestValue: toRpTrillion(factValue(latestAnnual, "EARNINGS")).toFixed(2),
      cagrLabel,
      cagrValue: windowCagr(factSeries("EARNINGS")),
      subtext: "Annual net income trend",
      series: buildSeries("EARNINGS", annualPeriods),
    },
    {
      id: "eps",
      title: "Earnings per Share (EPS)",
      unit: "Rp per share",
      latestValue: latestEps == null ? UNAVAILABLE : latestEps.toFixed(2),
      cagrLabel,
      cagrValue: windowCagr(epsValues),
      subtext: "Earnings / outstanding shares",
      series: epsSeries,
    },
  ];

  // --- Annual table ---------------------------------------------------------
  // Rows follow the workbook template (income statement + balance sheet in
  // `DataInput`) instead of only the five raw facts the table used to show, so
  // the ratios the workbook reports - EPS, BVPS, ROE and the two margins - are
  // visible again.
  //
  // The right-hand column is a real CAGR over the displayed window. It used to
  // read "YoY Change" while actually computing the *total* change between the
  // first and last year: for ERAA revenue 2019 -> 2025 that printed +132,53%
  // under a year-over-year label, which is a different number.
  const seriesRow = (
    metric: string,
    series: (number | null)[],
    format: (value: number | null) => string,
    // A ratio is a level, not a stock, so the workbook leaves its CAGR blank.
    withCagr = true,
  ) => ({
    metric,
    values: series.map(format),
    change: withCagr ? windowCagr(series) : "-",
  });

  const annualTable: NonNullable<StockDetail["financialHistory"]>["annualTable"] = {
    periods: annualPeriods.map(yearLabel),
    changeLabel: yearsSpanned > 0 ? `CAGR (${yearsSpanned}Y)` : "CAGR",
    rows: [
      seriesRow("Revenue (Rp T)", factSeries("REVENUE"), money),
      seriesRow("Gross Profit (Rp T)", factSeries("GROSS_PROFIT"), money),
      seriesRow("Net Income (Rp T)", factSeries("EARNINGS"), money),
      seriesRow("EPS (Rp)", perShareSeries("EARNINGS"), amount),
      // Total assets is not stored as a fact; the balance sheet identity
      // `assets = liabilities + equity` holds for every canonical annual row,
      // so liabilities is shown instead of inventing a derived total.
      seriesRow("Total Liabilities (Rp T)", factSeries("TOTAL_LIABILITIES"), money),
      seriesRow("Total Equity (Rp T)", factSeries("TOTAL_EQUITY"), money),
      seriesRow("Return on Equity (ROE)", ratioSeries("EARNINGS", "TOTAL_EQUITY"), percent1, false),
      seriesRow("Gross Margin", ratioSeries("GROSS_PROFIT", "REVENUE"), percent1, false),
      seriesRow("Net Margin", ratioSeries("EARNINGS", "REVENUE"), percent1, false),
      seriesRow("Book Value per Share (BVPS) (Rp)", perShareSeries("TOTAL_EQUITY"), amount),
    ],
  };

  const quarterlyTable: NonNullable<StockDetail["financialHistory"]>["quarterlyTable"] =
    quarterlyPeriods.length > 0
      ? {
          periods: quarterlyPeriods.map(yearLabel),
          changeLabel: "QoQ Change",
          rows: (["REVENUE", "EARNINGS"] as const).map((code) => {
            const values = quarterlyPeriods.map((p) => {
              const v = factValue(p, code);
              return v == null ? UNAVAILABLE : toRpTrillion(v).toFixed(2);
            });
            return { metric: METRIC_LABELS[code] ?? code, values, change: UNAVAILABLE };
          }),
        }
      : undefined;

  // Quarterly trend cards mirror the annual ones so the Quarterly view of the
  // Financials tab has real charts instead of an empty grid.
  const quarterlyTrendCards: NonNullable<StockDetail["financialHistory"]>["quarterlyTrendCards"] =
    quarterlyPeriods.length > 0
      ? (
          [
            { id: "quarterlyRevenue", code: "REVENUE", title: "Revenue" },
            { id: "quarterlyNetIncome", code: "EARNINGS", title: "Net Income" },
            { id: "quarterlyOperatingCashFlow", code: "OPERATING_CASH_FLOW", title: "Operating Cash Flow" },
          ] as const
        ).map((card) => {
          const latest = quarterlyPeriods.at(-1)!;
          const latestValue = factValue(latest, card.code);
          const priorYear = quarterlyPeriods.at(-5);
          const priorValue = priorYear ? factValue(priorYear, card.code) : null;
          const growth =
            latestValue != null && priorValue != null && priorValue !== 0
              ? ((latestValue - priorValue) / Math.abs(priorValue)) * 100
              : null;
          return {
            id: card.id,
            title: card.title,
            unit: "Rp Trillion",
            latestValue: latestValue == null ? UNAVAILABLE : toRpTrillion(latestValue).toFixed(2),
            cagrLabel: "YoY Growth",
            cagrValue: formatPercentSigned(growth),
            subtext:
              priorYear != null
                ? `${yearLabel(latest)} vs ${yearLabel(priorYear)}`
                : "Prior-year quarter not available",
            series: buildSeries(card.code, quarterlyPeriods),
          };
        })
      : [];

  return {
    subtitle: `Historical annual and quarterly financials based on ${annualPeriods.length} reported annual period(s).`,
    annualTrendCards,
    quarterlyTrendCards,
    annualMetrics: buildAnnualMetrics(latestAnnual),
    quarterlyMetrics: quarterlyPeriods.length > 0 ? buildQuarterlyMetrics(quarterlyPeriods.at(-1)!) : [],
    annualTable,
    quarterlyTable,
  };
}

/** Key ratio cards for the Financials tab, built from the latest period's facts. */
function buildAnnualMetrics(period: FinancialPeriod): NonNullable<StockDetail["financialHistory"]>["annualMetrics"] {
  const revenue = factValue(period, "REVENUE");
  const earnings = factValue(period, "EARNINGS");
  const grossProfit = factValue(period, "GROSS_PROFIT");
  const equity = factValue(period, "TOTAL_EQUITY");
  const liabilities = factValue(period, "TOTAL_LIABILITIES");

  const percent = (value: number | null) =>
    value == null ? UNAVAILABLE : `${(value * 100).toFixed(2).replace(".", ",")}%`;

  const ratio = (numerator: number | null, denominator: number | null) =>
    numerator == null || denominator == null || denominator === 0
      ? null
      : numerator / denominator;

  return [
    {
      label: "Return on Equity (ROE)",
      value: percent(ratio(earnings, equity)),
      subtext: "Net income / total equity",
    },
    {
      label: "Gross Margin",
      value: percent(ratio(grossProfit, revenue)),
      subtext: "Gross profit / revenue",
    },
    {
      label: "Net Margin",
      value: percent(ratio(earnings, revenue)),
      subtext: "Net income / revenue",
    },
    {
      label: "Revenue",
      value: revenue == null ? UNAVAILABLE : toRpTrillion(revenue).toFixed(2),
      subtext: "Rp Trillion",
    },
    {
      label: "Total Equity",
      value: equity == null ? UNAVAILABLE : toRpTrillion(equity).toFixed(2),
      subtext: "Rp Trillion",
    },
    {
      label: "Total Liabilities",
      value: liabilities == null ? UNAVAILABLE : toRpTrillion(liabilities).toFixed(2),
      subtext: "Rp Trillion",
    },
  ];
}

function buildQuarterlyMetrics(period: FinancialPeriod): NonNullable<StockDetail["financialHistory"]>["quarterlyMetrics"] {
  const revenue = factValue(period, "REVENUE");
  const earnings = factValue(period, "EARNINGS");
  const grossProfit = factValue(period, "GROSS_PROFIT");
  const ocf = factValue(period, "OPERATING_CASH_FLOW");
  const liabilities = factValue(period, "TOTAL_LIABILITIES");
  const equity = factValue(period, "TOTAL_EQUITY");

  const percent = (value: number | null) =>
    value == null ? UNAVAILABLE : `${(value * 100).toFixed(2).replace(".", ",")}%`;

  const ratio = (numerator: number | null, denominator: number | null) =>
    numerator == null || denominator == null || denominator === 0
      ? null
      : numerator / denominator;

  const amount = (value: number | null) =>
    value == null ? UNAVAILABLE : toRpTrillion(value).toFixed(2);

  return [
    { label: "Revenue", value: amount(revenue), subtext: "Rp Trillion" },
    { label: "Gross Margin", value: percent(ratio(grossProfit, revenue)), subtext: "Gross profit / revenue" },
    { label: "Net Margin", value: percent(ratio(earnings, revenue)), subtext: "Net income / revenue" },
    { label: "Operating Cash Flow", value: amount(ocf), subtext: "Rp Trillion" },
    { label: "Total Liabilities", value: amount(liabilities), subtext: "Rp Trillion" },
    { label: "Total Equity", value: amount(equity), subtext: "Rp Trillion" },
  ];
}

/**
 * Build the Growth tab chart series from canonical annual facts.
 *
 * Values are converted to Rp Billion so the chart axis stays readable; EPS is
 * computed as earnings / outstanding shares. Everything is derived from stored
 * facts, and a metric that is missing for a year yields `null` in the series so
 * the chart can leave an honest gap instead of drawing a fake zero.
 */
function buildGrowthVisuals(data: StockResearchData): StockDetail["healthGrowth"]["growthVisuals"] {
  const annualPeriods = data.financialPeriods
    .filter((p) => p.periodType === "ANNUAL")
    .sort((a, b) => a.periodEnd.localeCompare(b.periodEnd));

  const periods = annualPeriods.map((p) => p.periodLabel);

  const toBillion = (value: number | null): number | null =>
    value == null ? null : value / 1_000_000_000;

  const series = (metricCode: string) =>
    annualPeriods.map((p) => toBillion(factValue(p, metricCode)));

  const revenue = series("REVENUE");
  const netIncome = series("EARNINGS");
  const operatingCashFlow = series("OPERATING_CASH_FLOW");

  const eps = annualPeriods.map((p) => {
    const earnings = factValue(p, "EARNINGS");
    const shares = factValue(p, "OUTSTANDING_SHARES");
    if (earnings == null || shares == null || shares <= 0) return null;
    return earnings / shares;
  });

  // Year-over-year growth in percent, relative to the previous year. The first
  // year has no prior period, so it is reported as unavailable rather than 0.
  const yoyPercent = (values: (number | null)[]) =>
    values.map((value, index) => {
      const prior = index > 0 ? values[index - 1] : null;
      if (value == null || prior == null || prior === 0) return null;
      return ((value - prior) / Math.abs(prior)) * 100;
    });

  return {
    periods,
    revenueNetIncome: { revenue, netIncome },
    operatingCashFlow,
    eps,
    growthRate: { revenue: yoyPercent(revenue), eps: yoyPercent(eps) },
    keyInsights: [],
  };
}

function buildThesisValidator(data: StockResearchData): StockDetail["thesisValidator"] {
  const quarterlyPeriods = [...new Set(data.quarterlyQuality.map((q) => q.periodLabel))]
    .sort((a, b) => a.localeCompare(b))
    .slice(-4);

  const periodsByLabel = new Map(
    data.financialPeriods
      .filter((p) => p.periodType === "QUARTER")
      .map((p) => [p.periodLabel, p] as const),
  );

  const grossMarginRows = data.quarterlyQuality.filter((q) => q.metricCode === "QUALITY_GROSS_MARGIN");
  const ocfNiRows = data.quarterlyQuality.filter((q) => q.metricCode === "QUALITY_OCF_TO_NET_INCOME");

  const valueForQuarter = (rows: typeof grossMarginRows, label: string, asPercent = true): string => {
    const row = rows.find((r) => r.periodLabel === label);
    if (row?.value == null) return UNAVAILABLE;
    return asPercent
      ? `${(row.value * 100).toFixed(1).replace(".", ",")}%`
      : `${row.value.toFixed(2).replace(".", ",")}x`;
  };

  const yoyForQuarter = (label: string, metricCode: string): number | null => {
    const parts = label.split("-Q");
    if (parts.length !== 2) return null;
    const year = Number(parts[0]);
    const quarter = Number(parts[1]);
    const currentPeriod = periodsByLabel.get(label);
    const priorPeriod = periodsByLabel.get(`${year - 1}-Q${quarter}`);
    if (!currentPeriod || !priorPeriod) return null;
    const current = factValue(currentPeriod, metricCode);
    const prior = factValue(priorPeriod, metricCode);
    if (current == null || prior == null || prior === 0) return null;
    return ((current - prior) / Math.abs(prior)) * 100;
  };

  const q = (idx: number) => quarterlyPeriods[idx] ?? "";

  // Resolve a quarter label back to its period so facts can be read from it.
  const interestExpenseFor = (label: string) =>
    formatInterestExpense(factValue(periodsByLabel.get(label), "INTEREST_EXPENSE_NON_OPERATING"));

  const rows: StockDetail["thesisValidator"]["rows"] = [
    {
      item: "Revenue YoY (%)",
      q3: formatPercentSigned(yoyForQuarter(q(0), "REVENUE")),
      q4: formatPercentSigned(yoyForQuarter(q(1), "REVENUE")),
      q1: formatPercentSigned(yoyForQuarter(q(2), "REVENUE")),
      q2: formatPercentSigned(yoyForQuarter(q(3), "REVENUE")),
      trend: formatPercentSigned(yoyForQuarter(q(3), "REVENUE")),
      trendTone: trendToneFromValue(yoyForQuarter(q(3), "REVENUE")),
    },
    {
      item: "Net Income YoY (%)",
      q3: formatPercentSigned(yoyForQuarter(q(0), "EARNINGS")),
      q4: formatPercentSigned(yoyForQuarter(q(1), "EARNINGS")),
      q1: formatPercentSigned(yoyForQuarter(q(2), "EARNINGS")),
      q2: formatPercentSigned(yoyForQuarter(q(3), "EARNINGS")),
      trend: formatPercentSigned(yoyForQuarter(q(3), "EARNINGS")),
      trendTone: trendToneFromValue(yoyForQuarter(q(3), "EARNINGS")),
    },
    {
      item: "Gross Margin (Actual %)",
      q3: valueForQuarter(grossMarginRows, q(0)),
      q4: valueForQuarter(grossMarginRows, q(1)),
      q1: valueForQuarter(grossMarginRows, q(2)),
      q2: valueForQuarter(grossMarginRows, q(3)),
      trend: valueForQuarter(grossMarginRows, q(3)),
      trendTone: "slate",
    },
    {
      item: "OCF / NI Ratio (x)",
      q3: valueForQuarter(ocfNiRows, q(0), false),
      q4: valueForQuarter(ocfNiRows, q(1), false),
      q1: valueForQuarter(ocfNiRows, q(2), false),
      q2: valueForQuarter(ocfNiRows, q(3), false),
      trend: valueForQuarter(ocfNiRows, q(3), false),
      trendTone: "slate",
    },
    {
      // Interest expense is a quarterly fact; missing quarters are reported as
      // unavailable rather than omitted, so the row always stays visible.
      // Unit is BILLIONS of IDR: the workbook's "M Rp" label is misleading (see
      // docs/reference/EXCEL_POSTGRES_VALIDATION.md §"Unit reality check").
      item: "Interest Expense (Rp Bn)",
      q3: interestExpenseFor(q(0)),
      q4: interestExpenseFor(q(1)),
      q1: interestExpenseFor(q(2)),
      q2: interestExpenseFor(q(3)),
      trend: interestExpenseFor(q(3)),
      trendTone: "slate",
    },
  ];

  return {
    quarters: quarterlyPeriods.length > 0 ? quarterlyPeriods : [UNAVAILABLE],
    rows,
    footnote: "Based on the quarterly financial statements available in the database.",
  };
}

function buildDividendConsistency(data: StockResearchData): StockDetail["dividendConsistency"] {
  const percent = (value: number | null): string =>
    value == null ? UNAVAILABLE : `${(value * 100).toFixed(1).replace(".", ",")}%`;

  // The workbook's "Avg (4Y)" cell is the mean of the five displayed columns
  // (projection + four fiscal years), verified against the sample workbooks:
  // BIRD DPS (85.988+120+91+72+60)/5 = 85.7977. Columns with no value are
  // excluded, and a row with no value at all stays "Not available".
  const average = (values: (number | null)[]): number | null => {
    const present = values.filter((value): value is number => value != null);
    if (present.length === 0) return null;
    return present.reduce((sum, value) => sum + value, 0) / present.length;
  };

  // DPS is indexed by fiscal year, never by position: a company that skipped a
  // year (GEMA paid nothing in 2021-2023 and 2026) would otherwise shift its
  // 2025 dividend into the 2026 column.
  const dpsByYear: Record<string, number | null> = {};
  for (const fact of data.dividends) {
    if (fact.periodYear == null) continue;
    dpsByYear[String(fact.periodYear)] = fact.amountPerShare;
  }

  // DPR and Dividend Yield are stored annual results (`DIVIDEND_PAYOUT_RATIO` /
  // `DIVIDEND_YIELD`, workbook DataInput!B28/B29). One snapshot per year carries
  // that year's own row, so index them by period label. They are read from the
  // database rather than recomputed here: the yield denominator is a
  // point-in-time year-end close the browser cannot reconstruct, because the
  // price payload only carries the trailing window.
  const ratioByYear = (metricCode: string): Record<string, number | null> => {
    const map: Record<string, number | null> = {};
    for (const row of data.annualGrowth) {
      if (row.metricCode === metricCode) map[row.periodLabel] = row.value;
    }
    return map;
  };
  const dprByYear = ratioByYear("DIVIDEND_PAYOUT_RATIO");
  const yieldByYear = ratioByYear("DIVIDEND_YIELD");

  // The projection column is the active scenario, not a stored annual snapshot:
  // `POTENTIAL_DPS` is the workbook's `Proj_DPS` (`B26 = IF(Proj_DPS="",0,...)`)
  // and `average_dpr_ratio` is `Proj_Dividend_Payout_Ratio` (`B28`). Projected
  // yield (`B29 = B26/B25`) divides by `Metric_Price_Current`, the latest close -
  // deliberately a different basis from the historical year-end column.
  const projection = data.projection;
  const projectedDps = projection
    ? projection.values.find((value) => value.metricCode === "POTENTIAL_DPS")?.value ?? null
    : null;
  const projectedDpr = projection?.averageDprRatio ?? null;
  const latestPrice = data.prices.at(-1)?.closePrice ?? null;
  const projectedYield =
    projectedDps == null || latestPrice == null || latestPrice === 0
      ? null
      : projectedDps / latestPrice;

  // Columns run from the projection year backwards, mirroring the workbook's
  // `RIGHT(Years_Base_Selected,4)-1` ... `-4` headers.
  const projectionYear = projection?.projectionYear ?? 2026;
  const columnYears = [0, 1, 2, 3, 4].map((offset) => projectionYear - offset);
  const PERIOD_KEYS = ["p2026", "y2025", "y2024", "y2023", "y2022"] as const;

  const row = (
    item: string,
    values: (number | null)[],
    formatter: (value: number | null) => string,
  ): StockDetail["dividendConsistency"]["rows"][number] => {
    const cells = PERIOD_KEYS.map((_, index) => values[index] ?? null);
    return {
      item,
      p2026: formatter(cells[0]),
      y2025: formatter(cells[1]),
      y2024: formatter(cells[2]),
      y2023: formatter(cells[3]),
      y2022: formatter(cells[4]),
      avg4Y: formatter(average(cells)),
    };
  };

  const amount = (value: number | null): string =>
    value == null ? UNAVAILABLE : value.toFixed(2);

  const dpsValues = columnYears.map((year, index) =>
    index === 0 ? projectedDps : dpsByYear[String(year)] ?? null,
  );
  const dprValues = columnYears.map((year, index) =>
    index === 0 ? projectedDpr : dprByYear[String(year)] ?? null,
  );
  const yieldValues = columnYears.map((year, index) =>
    index === 0 ? projectedYield : yieldByYear[String(year)] ?? null,
  );

  const dpsRow = row("DPS [Rp]", dpsValues, amount);
  const dprRow = row("DPR [%]", dprValues, percent);
  const yieldRow = row("Yield [%]", yieldValues, percent);

  return {
    // The card's headline yield is the same "Avg (4Y)" the table shows, so the
    // two can never disagree.
    averageYield: yieldRow.avg4Y,
    years: [
      ...columnYears.map((year, index) =>
        index === 0 ? `${year} (Proyeksi)` : String(year),
      ),
      "Avg (4Y)",
    ],
    rows: [dpsRow, dprRow, yieldRow],
    callout: buildDividendCallout({
      hasDividends: data.dividends.length > 0,
      hasDpr: dprValues.some((value) => value != null),
      hasYield: yieldValues.some((value) => value != null),
    }),
  };
}

/**
 * The dividend card's callout. It only claims what the database actually holds,
 * so a ticker whose dividend ratios could not be computed (missing DPS or no
 * year-end price) says so instead of showing a silent gap.
 */
function buildDividendCallout({
  hasDividends,
  hasDpr,
  hasYield,
}: {
  hasDividends: boolean;
  hasDpr: boolean;
  hasYield: boolean;
}): string {
  if (!hasDividends) return "No historical dividend data for this ticker.";
  if (hasDpr && hasYield) {
    return "DPS, DPR and dividend yield are stored calculation results. Yield uses the point-in-time year-end close, not the latest price.";
  }
  if (hasDpr || hasYield) {
    return "DPS is stored directly; only one of DPR or dividend yield could be computed for this ticker because an input is missing.";
  }
  return "DPS is stored directly. DPR and dividend yield need a recorded dividend and a year-end price, which are not available for this ticker yet.";
}

function buildGrowthSummary(data: StockResearchData): StockDetail["growthSummary"] {
  const revenueCagrShort = findAnnualMetric(data, "GROWTH_REVENUE_CAGR_SHORT").value;
  const epsCagrShort = findAnnualMetric(data, "GROWTH_EPS_CAGR_SHORT").value;

  const metrics: StockDetail["growthSummary"]["metrics"] = [
    {
      label: "Revenue Growth (3Y CAGR)",
      value: formatCagr(revenueCagrShort),
      badge: badgeFromGrowth(revenueCagrShort),
      subtext: "Calculated from historical data in the database",
    },
    {
      label: "Net Income Growth (3Y CAGR)",
      value: UNAVAILABLE,
      badge: "Stable",
      subtext: "Net income CAGR has not been calculated yet",
    },
    {
      label: "EPS Growth (3Y CAGR)",
      value: formatCagr(epsCagrShort),
      badge: badgeFromGrowth(epsCagrShort),
      subtext: "Calculated from historical data in the database",
    },
  ];

  return { metrics };
}

function buildFinancialHealth(data: StockResearchData): StockDetail["financialHealth"] {
  const roe = findQuarterlyMetric(data, "QUALITY_ROE").value;
  const ocfNi = findQuarterlyMetric(data, "QUALITY_OCF_TO_NET_INCOME").value;
  const grossMargin = findQuarterlyMetric(data, "QUALITY_GROSS_MARGIN").value;

  const metrics: NonNullable<StockDetail["financialHealth"]>["metrics"] = [
    {
      label: "Return on Equity (ROE)",
      value: roe != null ? `${(roe * 100).toFixed(2).replace(".", ",")}%` : UNAVAILABLE,
      badge: roe != null && roe > 0.1 ? "Healthy" : roe != null ? "Stable" : "Caution",
      subtext: "Latest quarter from the database",
    },
    {
      label: "Gross Margin",
      value: grossMargin != null ? `${(grossMargin * 100).toFixed(2).replace(".", ",")}%` : UNAVAILABLE,
      badge: grossMargin != null ? "Stable" : "Caution",
      subtext: "Latest quarter from the database",
    },
    {
      label: "OCF / Net Income",
      value: ocfNi != null ? `${ocfNi.toFixed(2).replace(".", ",")}x` : UNAVAILABLE,
      badge: ocfNi != null && ocfNi >= 1 ? "Healthy" : ocfNi != null ? "Stable" : "Caution",
      subtext: "Latest quarter from the database",
    },
  ];

  return { metrics };
}

/**
 * Build the backtest tab payload from stored results.
 *
 * Replaces the sample dataset. `isDemoData` is deliberately NOT set, so the
 * "Demo Data" badge disappears on its own once the numbers are real (section
 * 5.2 of the architecture doc) instead of needing a second flag to keep in sync.
 */
function buildBacktest(data: BacktestData | null | undefined): StockDetail["backtest"] {
  if (!data || data.cases.length === 0) return undefined;

  return {
    cases: data.cases.map((testCase) =>
      buildBacktestCase(testCase, data.ticker, data.sectorName),
    ),
    methodology: {
      processSteps: [
        {
          number: "01",
          title: "Identify the Condition",
          text: "Each historical quarter is classified as Undervalued, Overvalued, or Mixed using the valuation framework available on the analysis date.",
        },
        {
          number: "02",
          title: "Track Price Movement",
          text: "After the analysis date, price movement is observed for up to 12 months against predefined upside and downside thresholds.",
        },
        {
          number: "03",
          title: "Determine the Outcome",
          text: "The first threshold reached determines the historical outcome. This is evidence of past behavior, not a prediction or recommendation.",
        },
      ],
    },
  };
}

/**
 * Build the sample-data version of the Historical Evidence preview.
 *
 * The sample backtest cases stay the single source of truth for the demo
 * ticker, so the preview is computed from them with the same aggregation the
 * stored path uses instead of being a second set of hand-written numbers that
 * could drift from the tab next to it.
 */
function buildDemoEvidencePreview(
  cases: BacktestCase[],
): StockDetail["historicalEvidencePreview"] {
  const preview = buildHistoricalEvidencePreview(cases);
  return preview ? { ...preview, isDemoData: true } : undefined;
}

/**
 * Backtest history and the "Historical Evidence" preview have no backing
 * database table yet. To keep the existing UI demo-able without pretending the
 * numbers are real, we expose the sample dataset for the single ticker that
 * ships with it (AUTO) and mark it with `isDemoData: true` so the UI can label
 * it. Every other ticker gets nothing and renders the "Not available" state.
 */
function pickDemoBacktestData(
  ticker: string,
): Pick<StockDetail, "backtest" | "historicalEvidencePreview"> {
  if (ticker.toUpperCase() !== "AUTO") {
    return { backtest: undefined, historicalEvidencePreview: undefined };
  }

  const demo = mockStockDetails.AUTO;
  return {
    backtest: demo.backtest,
    historicalEvidencePreview: buildDemoEvidencePreview(demo.backtest?.cases ?? []),
  };
}

/** Growth-quality / forensic cards from the stored annual growth metrics. */
function buildForensicMetrics(
  data: StockResearchData,
): StockDetail["healthGrowth"]["forensic"]["metrics"] {
  const latest = (code: string) => findAnnualMetric(data, code);

  const revenueCov = latest("GROWTH_REVENUE_COV");
  const assetGap = latest("GROWTH_ASSET_GROWTH_GAP");
  const debtGap = latest("FORENSIC_DEBT_GROWTH_GAP");
  const marginSpike = latest("FORENSIC_MARGIN_SPIKE");

  const percent = (value: number | null) =>
    value == null ? UNAVAILABLE : `${(value * 100).toFixed(2).replace(".", ",")}%`;

  // Revenue coverage is a coverage ratio (revenue growth / asset growth), so it
  // reads as a multiple; the gap metrics are differences of growth ratios and
  // read as percentage points.
  const multiple = (value: number | null) =>
    value == null ? UNAVAILABLE : `${value.toFixed(2).replace(".", ",")}x`;

  const tone = (value: number | null): "positive" | "neutral" | "negative" => {
    if (value == null) return "neutral";
    if (value > 0) return "positive";
    if (value < 0) return "negative";
    return "neutral";
  };

  return [
    {
      label: "Revenue Coverage",
      value: multiple(revenueCov.value),
      context: `Periode ${revenueCov.periodLabel}: rasio pertumbuhan revenue terhadap pertumbuhan aset.`,
      tone: tone(revenueCov.value),
    },
    {
      label: "Asset Growth Gap",
      value: percent(assetGap.value),
      context: `Periode ${assetGap.periodLabel}: selisih pertumbuhan aset terhadap revenue.`,
      tone: tone(assetGap.value),
    },
    {
      label: "Debt Growth Gap",
      value: percent(debtGap.value),
      context: `Periode ${debtGap.periodLabel}: pertumbuhan liabilitas terhadap revenue.`,
      tone: tone(debtGap.value),
    },
    {
      label: "Margin Spike",
      value: percent(marginSpike.value),
      context: `Periode ${marginSpike.periodLabel}: perubahan margin terhadap rata-rata historis.`,
      tone: tone(marginSpike.value),
    },
  ];
}

/** Key per-share valuation metrics for the Valuation tab, from stored facts. */
function buildValuationMetrics(
  data: StockResearchData,
  currentPrice: number | null,
): StockDetail["currentValuation"]["metrics"] {
  const annualPeriods = data.financialPeriods
    .filter((p) => p.periodType === "ANNUAL")
    .sort((a, b) => a.periodEnd.localeCompare(b.periodEnd));
  const latestAnnual = annualPeriods.at(-1);

  const earnings = latestAnnual ? factValue(latestAnnual, "EARNINGS") : null;
  const equity = latestAnnual ? factValue(latestAnnual, "TOTAL_EQUITY") : null;

  // Shares are carried forward from the most recent year that reported them.
  // The provider leaves `OUTSTANDING_SHARES` null for some tickers' latest year
  // (BIRD 2025 is one), and treating that as "no EPS/BVPS at all" hid four
  // metrics behind a null that has a perfectly good prior value. This mirrors
  // the backend's `annual_share_count`, which walks backwards for the same
  // reason, and is flagged below so the approximation is visible.
  const sharePeriod = [...annualPeriods]
    .reverse()
    .find((p) => (factValue(p, "OUTSTANDING_SHARES") ?? 0) > 0);
  const shares = sharePeriod ? factValue(sharePeriod, "OUTSTANDING_SHARES") : null;
  const sharesAreCarried =
    sharePeriod != null && sharePeriod.periodEnd !== latestAnnual?.periodEnd;

  const eps = earnings != null && shares != null && shares > 0 ? earnings / shares : null;
  const bvps = equity != null && shares != null && shares > 0 ? equity / shares : null;

  const multiple = (numerator: number | null, denominator: number | null) =>
    numerator == null || denominator == null || denominator <= 0
      ? UNAVAILABLE
      : `${(numerator / denominator).toFixed(2).replace(".", ",")}x`;

  const sharesNote = sharesAreCarried
    ? ` (shares from ${sharePeriod.periodEnd.slice(0, 4)}; latest year not reported)`
    : "";

  return [
    {
      label: "EPS (TTM)",
      value: eps ?? UNAVAILABLE,
      note: `Earnings / outstanding shares${sharesNote}`,
    },
    {
      label: "BVPS",
      value: bvps ?? UNAVAILABLE,
      note: `Total equity / outstanding shares${sharesNote}`,
    },
    { label: "P/E Ratio", value: multiple(currentPrice, eps), note: "Price / EPS" },
    { label: "P/BV Ratio", value: multiple(currentPrice, bvps), note: "Price / BVPS" },
  ];
}

/**
 * The price RPC returns up to 260 rows of **daily** closes. The chart works in
 * months (3M/6M/9M/12M), so the series is collapsed to one point per calendar
 * month using the last close of that month. Rows without a usable date are
 * skipped instead of being mislabelled.
 */
function buildMonthlyPricePoints(prices: StockPrice[]): { date: string; value: number }[] {
  const lastCloseByMonth = new Map<string, number>();

  for (const price of prices) {
    if (price.closePrice == null) continue;
    const label = toMonthLabel(price.tradingDate);
    if (label == null) continue;
    // Rows arrive oldest-first, so later rows overwrite earlier ones and the
    // map keeps the final close of each month.
    lastCloseByMonth.set(label, price.closePrice);
  }

  return [...lastCloseByMonth]
    .map(([date, value]) => ({ date, value }))
    .sort((a, b) => (toMonthIndex(a.date) ?? 0) - (toMonthIndex(b.date) ?? 0));
}

export function buildStockDetail(data: StockResearchData, backtest?: BacktestData | null): StockDetail {
  const storedBacktest = buildBacktest(backtest);
  // Stored results win. The sample dataset is only a fallback so the tab stays
  // demo-able for the one ticker that ships with it, and it keeps its
  // `isDemoData` badge so it can never be mistaken for stored history.
  const demoBacktest = storedBacktest
    ? { backtest: undefined, historicalEvidencePreview: undefined }
    : pickDemoBacktestData(data.instrument.ticker);
  const backtestSection = storedBacktest ?? demoBacktest.backtest;
  // The Overview preview reads the same cases the Backtest tab does, so both
  // screens report one set of numbers.
  const evidencePreview =
    buildHistoricalEvidencePreview(backtestSection?.cases ?? []) ??
    demoBacktest.historicalEvidencePreview;
  // The Key Metric headline figures are the win rates of both rules, read from
  // the same preview the Overview panel renders so the top row and the panel
  // cannot drift apart.
  const evidenceWinRates = {
    method: formatEvidenceWinRate(evidencePreview?.verdictMethod),
    mos: formatEvidenceWinRate(evidencePreview?.verdictMos),
  };
  // Stock type comes from the stored rows, not from the chosen main method, so
  // the fallback below cannot change what type the ticker is.
  const stockType = data.valuationMethods[0]?.stockType ?? UNAVAILABLE;
  const mainMethod = pickMainMethod(data.valuationMethods, stockType);
  const latestPrice = data.prices.at(-1);
  const previousPrice = data.prices.at(-2);

  const price = latestPrice?.closePrice ?? null;
  const change =
    price != null && previousPrice?.closePrice != null ? price - previousPrice.closePrice : null;
  const changePercent =
    change != null && previousPrice?.closePrice ? (change / previousPrice.closePrice) * 100 : null;

  const intrinsicValue = mainMethod?.intrinsicValue ?? null;
  const currentPrice = mainMethod?.currentPrice ?? price;
  const mos = computeMos(intrinsicValue, currentPrice);
  const verdict = mapVerdict(mainMethod?.verdict);

  const prices52w = data.prices.filter((p) => p.closePrice != null).map((p) => p.closePrice as number);
  const low52W = prices52w.length > 0 ? Math.min(...prices52w) : null;
  const high52W = prices52w.length > 0 ? Math.max(...prices52w) : null;
  const latestMarketCap = latestPrice?.marketCap ?? null;

  const methods: import("@/data/mock-stock-details").ValuationMethodResult[] = sortValuationMethods(
    data.valuationMethods
      // `APPROXIMATED` rows carry a real computed intrinsic value (the engine only
      // proxied an input, e.g. quarterly shares -> latest annual figure), so they
      // must be shown. Dropping them hid the whole Mean Reversion PBV method.
      // `UNAVAILABLE` rows have no value and stay out.
      .filter(
        (m) =>
          m.intrinsicValue != null &&
          (m.calculationStatus === "VALID" || m.calculationStatus === "APPROXIMATED"),
      ),
  ).map((m) => {
    const marginOfSafety = computeMos(m.intrinsicValue, m.currentPrice);
    return {
      method: methodDisplayName(m.methodCode),
      methodCode: m.methodCode,
      intrinsicValue: m.intrinsicValue as number,
      marginOfSafety: formatPercentSigned(marginOfSafety),
      // The stored verdict already says NOT_APPLICABLE for every `IV <= 0` row,
      // so it is read rather than re-derived. Forcing the leftover values to
      // OVERVALUED is what used to label a skipped DDM as "overvalued".
      status: methodStatus(m.intrinsicValue as number, m.verdict),
      description: methodDisplayName(m.methodCode),
    };
  });

  return {
    ticker: data.instrument.ticker,
    companyName: data.instrument.companyName ?? data.instrument.ticker,
    sector: data.instrument.sectorName ?? UNAVAILABLE,
    stockType,
    price,
    change,
    changePercent,
    updatedAt: latestPrice?.tradingDate ?? UNAVAILABLE,
    verdict,
    verdictDescription: mainMethod ? "Based on the database valuation model" : "No stored valuation result yet",
    intrinsicValue,
    mos,
    stockCharacter: stockType,
    stockCharacterDesc: stockType !== UNAVAILABLE ? "Stock type classification from the database" : UNAVAILABLE,
    evidenceWinRates,
    researchSummary: mainMethod
      ? `${data.instrument.ticker} was evaluated using the ${methodDisplayName(mainMethod.methodCode)} valuation model based on the latest database data.`
      : `No stored valuation result for ${data.instrument.ticker} in the database.`,
    methodologyUrl: "#",
    companyProfile: {
      description: `${data.instrument.companyName ?? data.instrument.ticker} — the full company description is not available in the database yet.`,
      sector: data.instrument.sectorName ?? UNAVAILABLE,
      stockType,
      listedDate: UNAVAILABLE,
      headquarters: UNAVAILABLE,
      website: UNAVAILABLE,
    },
    priceChart: {
      timeframe: "1Y",
      points: buildMonthlyPricePoints(data.prices),
      low52W,
      high52W,
      ytdPercent: changePercent,
      marketCap:
        latestMarketCap != null ? `Rp${(latestMarketCap / 1_000_000_000_000).toFixed(2)} T` : UNAVAILABLE,
      peTTM: null,
    },
    currentValuation: {
      verdict,
      currentPrice,
      intrinsicValue,
      mos,
      metrics: buildValuationMetrics(data, currentPrice),
      methods,
      mainMethodCode: mainMethod ? (mainMethod.methodCode as ValuationMethodCode) : null,
      comparison: {
        takeaway: mainMethod
          ? "Comparison of the current price against the intrinsic value estimates from the valuation methods stored in the database."
          : "No stored valuation result for this ticker.",
        readouts: [],
      },
    },
    financialHealth: buildFinancialHealth(data),
    healthGrowth: {
      periodOptions: ["Quarterly"],
      defaultPeriod: "Quarterly",
      growth: {
        revenueHistorical: {
          value: formatCagr(findAnnualMetric(data, "GROWTH_REVENUE_CAGR_LONG").value),
          period: "Historical",
        },
        revenueFiveYear: {
          value: formatCagr(findAnnualMetric(data, "GROWTH_REVENUE_CAGR_SHORT").value),
          period: "5 Year",
        },
        revenueYoY: {
          value: formatCagr(findAnnualMetric(data, "GROWTH_REVENUE_YOY").value),
          period: "YoY",
        },
        revenueMomentum: {
          value: findAnnualMetric(data, "QUALITY_REVENUE_MOMENTUM").value === 1 ? "Accelerating" : UNAVAILABLE,
          period: "Current",
          tone: findAnnualMetric(data, "QUALITY_REVENUE_MOMENTUM").value === 1 ? "positive" : "neutral",
        },
        epsHistorical: {
          value: formatCagr(findAnnualMetric(data, "GROWTH_EPS_CAGR_LONG").value),
          period: "Historical",
        },
        epsFiveYear: {
          value: formatCagr(findAnnualMetric(data, "GROWTH_EPS_CAGR_SHORT").value),
          period: "5 Year",
        },
        epsMomentum: {
          value: findAnnualMetric(data, "QUALITY_EPS_MOMENTUM").value === 1 ? "Accelerating" : UNAVAILABLE,
          period: "Current",
          tone: findAnnualMetric(data, "QUALITY_EPS_MOMENTUM").value === 1 ? "positive" : "neutral",
        },
      },
      growthVisuals: buildGrowthVisuals(data),
      profitability: { metrics: [] },
      cashFlow: { metrics: [] },
      forensic: { metrics: buildForensicMetrics(data) },
      quarterlyMeaning: "No automatic quarterly quality summary for this ticker yet.",
      overall: { score: UNAVAILABLE, rating: UNAVAILABLE, clearance: UNAVAILABLE, context: UNAVAILABLE },
    },
    growthSummary: buildGrowthSummary(data),
    historicalEvidencePreview: evidencePreview,
    backtest: backtestSection,
    thesisValidator: buildThesisValidator(data),
    dividendConsistency: buildDividendConsistency(data),
    financialHistory: buildFinancialHistory(data.financialPeriods),
  };
}
