import "server-only";

import type { BacktestData, StockResearchData, FinancialPeriod, ValuationMethod, StockPrice } from "@/lib/stock-data";
import { mockStockDetails, type StockDetail } from "@/data/mock-stock-details";
import { toMonthIndex, toMonthLabel } from "@/utils/dates";
import { sortValuationMethods, valuationMethodLabel } from "@/lib/valuation-methods";
import { buildBacktestCase } from "@/lib/backtest-adapter";

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

function pickPrimaryMethod(methods: ValuationMethod[]): ValuationMethod | null {
  if (methods.length === 0) return null;
  const stockType = (methods[0].stockType ?? "").toUpperCase();
  const preferredCode =
    stockType === "STALWART" || stockType === "FAST GROWER" ? "TYPE_SECTOR_WEIGHTED" : "PETER_LYNCH";
  return (
    methods.find((m) => m.methodCode === preferredCode && m.calculationStatus === "VALID") ??
    methods.find((m) => m.calculationStatus === "VALID") ??
    null
  );
}

function computeMos(intrinsicValue: number | null, currentPrice: number | null): number | null {
  if (intrinsicValue == null || currentPrice == null || intrinsicValue === 0) return null;
  return ((intrinsicValue - currentPrice) / intrinsicValue) * 100;
}

/** Gap against the current price — the template's "Potential (Gain/Loss)". */
function computeGap(intrinsicValue: number | null, currentPrice: number | null): number | null {
  if (intrinsicValue == null || currentPrice == null || currentPrice === 0) return null;
  return ((intrinsicValue - currentPrice) / currentPrice) * 100;
}

function methodDisplayName(methodCode: string): string {
  return valuationMethodLabel(methodCode);
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
  const cagr = (metricCode: string): string => {
    const first = factValue(annualPeriods[0], metricCode);
    const last = factValue(latestAnnual, metricCode);
    const years = annualPeriods.length - 1;
    if (first == null || last == null || first <= 0 || years <= 0) return UNAVAILABLE;
    const rate = Math.pow(last / first, 1 / years) - 1;
    return formatCagr(rate);
  };

  // EPS is derived per year (earnings / outstanding shares). A year missing
  // either input is skipped, so the series can never claim a value it lacks.
  const epsValues = annualPeriods.map((p) => {
    const earnings = factValue(p, "EARNINGS");
    const shares = factValue(p, "OUTSTANDING_SHARES");
    if (earnings == null || shares == null || shares <= 0) return null;
    return earnings / shares;
  });
  const epsSeries = annualPeriods
    .map((p, index) => ({ year: yearLabel(p), value: epsValues[index] }))
    .filter((point): point is { year: string; value: number } => point.value != null);
  const validEps = epsValues.filter((value): value is number => value != null && value > 0);
  const latestEps = epsValues.at(-1) ?? null;
  const epsCagr =
    validEps.length >= 2 && validEps[0] > 0
      ? Math.pow(validEps.at(-1)! / validEps[0], 1 / (validEps.length - 1)) - 1
      : null;

  const annualTrendCards: NonNullable<StockDetail["financialHistory"]>["annualTrendCards"] = [
    {
      id: "revenue",
      title: "Revenue",
      unit: "Rp Trillion",
      latestValue: toRpTrillion(factValue(latestAnnual, "REVENUE")).toFixed(2),
      cagrLabel: `CAGR (${annualPeriods.length}Y)`,
      cagrValue: cagr("REVENUE"),
      subtext: "Annual revenue trend",
      series: buildSeries("REVENUE", annualPeriods),
    },
    {
      id: "netIncome",
      title: "Net Income",
      unit: "Rp Trillion",
      latestValue: toRpTrillion(factValue(latestAnnual, "EARNINGS")).toFixed(2),
      cagrLabel: `CAGR (${annualPeriods.length}Y)`,
      cagrValue: cagr("EARNINGS"),
      subtext: "Annual net income trend",
      series: buildSeries("EARNINGS", annualPeriods),
    },
    {
      id: "eps",
      title: "Earnings per Share (EPS)",
      unit: "Rp per share",
      latestValue: latestEps == null ? UNAVAILABLE : latestEps.toFixed(2),
      cagrLabel: `CAGR (${annualPeriods.length}Y)`,
      cagrValue: formatPercentSigned(epsCagr),
      subtext: "Earnings / outstanding shares",
      series: epsSeries,
    },
  ];

  const annualTable: NonNullable<StockDetail["financialHistory"]>["annualTable"] = {
    periods: annualPeriods.map(yearLabel),
    changeLabel: "YoY Change",
    rows: (["REVENUE", "EARNINGS", "GROSS_PROFIT", "TOTAL_EQUITY", "TOTAL_LIABILITIES"] as const).map(
      (code) => {
        const values = annualPeriods.map((p) => {
          const v = factValue(p, code);
          return v == null ? UNAVAILABLE : toRpTrillion(v).toFixed(2);
        });
        const firstV = factValue(annualPeriods[0], code);
        const lastV = factValue(latestAnnual, code);
        const change =
          firstV != null && lastV != null && annualPeriods.length > 1
            ? formatPercentSigned(((lastV - firstV) / Math.abs(firstV)) * 100)
            : UNAVAILABLE;
        return { metric: METRIC_LABELS[code] ?? code, values, change };
      },
    ),
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
  const sorted = [...data.dividends].sort((a, b) => (b.periodYear ?? 0) - (a.periodYear ?? 0));
  const latest5 = sorted.slice(0, 5);
  const years = latest5.map((d) => (d.periodYear != null ? String(d.periodYear) : UNAVAILABLE));

  const dpsValues: Record<string, string> = {};
  latest5.forEach((d, idx) => {
    const key = (["p2026", "y2025", "y2024", "y2023", "y2022"] as const)[idx];
    if (key) dpsValues[key] = d.amountPerShare != null ? d.amountPerShare.toFixed(2) : UNAVAILABLE;
  });

  const validYields = data.dividends.filter((d) => d.yieldRatio != null);
  const avgYield =
    validYields.length > 0
      ? `${((validYields.reduce((sum, d) => sum + (d.yieldRatio ?? 0), 0) / validYields.length) * 100)
          .toFixed(2)
          .replace(".", ",")}%`
      : UNAVAILABLE;

  return {
    averageYield: avgYield,
    years: years.length > 0 ? years : [UNAVAILABLE],
    rows: [
      {
        item: "DPS [Rp]",
        p2026: dpsValues.p2026 ?? UNAVAILABLE,
        y2025: dpsValues.y2025 ?? UNAVAILABLE,
        y2024: dpsValues.y2024 ?? UNAVAILABLE,
        y2023: dpsValues.y2023 ?? UNAVAILABLE,
        y2022: dpsValues.y2022 ?? UNAVAILABLE,
        avg4Y: UNAVAILABLE,
      },
    ],
    callout:
      data.dividends.length > 0
        ? "Historical dividend per share is taken directly from the database. Projected DPR and yield are not available yet."
        : "No historical dividend data for this ticker.",
  };
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
    historicalEvidencePreview: demo.historicalEvidencePreview,
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
  const primaryMethod = pickPrimaryMethod(data.valuationMethods);
  const latestPrice = data.prices.at(-1);
  const previousPrice = data.prices.at(-2);

  const price = latestPrice?.closePrice ?? null;
  const change =
    price != null && previousPrice?.closePrice != null ? price - previousPrice.closePrice : null;
  const changePercent =
    change != null && previousPrice?.closePrice ? (change / previousPrice.closePrice) * 100 : null;

  const intrinsicValue = primaryMethod?.intrinsicValue ?? null;
  const currentPrice = primaryMethod?.currentPrice ?? price;
  const mos = computeMos(intrinsicValue, currentPrice);
  const verdict = mapVerdict(primaryMethod?.verdict);
  const stockType = primaryMethod?.stockType ?? UNAVAILABLE;

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
    // "Potential" and "Margin of Safety" are different figures in the template
    // (`SUMMARY`): Potential measures the gap against the *current price*, while
    // MoS measures the same gap against the *intrinsic value*. Both are shown as
    // percentages, so they must not reuse the same number.
    const potential = m.gapRatio != null ? m.gapRatio * 100 : computeGap(m.intrinsicValue, m.currentPrice);
    const marginOfSafety = computeMos(m.intrinsicValue, m.currentPrice);
    return {
      method: methodDisplayName(m.methodCode),
      methodCode: m.methodCode,
      intrinsicValue: m.intrinsicValue as number,
      potential: formatPercentSigned(potential),
      marginOfSafety: formatPercentSigned(marginOfSafety),
      status: m.verdict === "UNDERVALUED" ? ("UNDERVALUED" as const) : ("OVERVALUED" as const),
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
    verdictDescription: primaryMethod ? "Based on the database valuation model" : "No stored valuation result yet",
    intrinsicValue,
    mos,
    stockCharacter: stockType,
    stockCharacterDesc: stockType !== UNAVAILABLE ? "Stock type classification from the database" : UNAVAILABLE,
    evidenceWins: null,
    evidenceTotal: null,
    researchSummary: primaryMethod
      ? `${data.instrument.ticker} was evaluated using the ${methodDisplayName(primaryMethod.methodCode)} valuation model based on the latest database data.`
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
      comparison: {
        takeaway: primaryMethod
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
    historicalEvidencePreview: demoBacktest.historicalEvidencePreview,
    backtest: backtestSection,
    thesisValidator: buildThesisValidator(data),
    dividendConsistency: buildDividendConsistency(data),
    financialHistory: buildFinancialHistory(data.financialPeriods),
  };
}
