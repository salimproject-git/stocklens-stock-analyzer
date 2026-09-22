export function getMainValuationMethod(stockType: string) {
  const normalizedStockType = stockType.trim().toLowerCase();
  return normalizedStockType === "stalwart" || normalizedStockType === "fast grower"
    ? "Type & Sector Weighted"
    : "Peter Lynch / Adaptive";
}

export type FinancialMetricStatus = "EXPANDING" | "CONTRACTING" | "STABLE_MARGIN" | "IMPROVING" | "DECLINING" | "STRONG_CASH_CONVERSION" | "MODERATE_CASH_CONVERSION" | "WEAK_CASH_CONVERSION" | "ABOVE_AVERAGE" | "BELOW_AVERAGE" | "IN_LINE_WITH_AVERAGE";
type FinancialHistory = NonNullable<import("@/data/mock-stock-details").StockDetail["financialHistory"]>;
type FinancialMetric = FinancialHistory["annualMetrics"][number];
type FinancialTable = FinancialHistory["annualTable"];

function parseFinancialMetricValue(value: string | undefined) {
  return Number((value ?? "0").replace(",", ".").replace("%", "").replace("x", ""));
}

function getFinancialMetricRow(table: FinancialTable | undefined, label: string) {
  return table?.rows.find((row) => row.metric.startsWith(label));
}

function classifyMargin(table: FinancialTable | undefined, label: string, expandingStatus: "EXPANDING" | "IMPROVING") {
  const values = getFinancialMetricRow(table, label)?.values ?? [];
  const change = parseFinancialMetricValue(values.at(-1)) - parseFinancialMetricValue(values.at(-2));
  if (change > 0.5) return expandingStatus;
  if (change < -0.5) return expandingStatus === "EXPANDING" ? "CONTRACTING" : "DECLINING";
  return "STABLE_MARGIN";
}

function classifyCashConversion(value: string | undefined) {
  const ratio = parseFinancialMetricValue(value);
  if (ratio >= 1) return "STRONG_CASH_CONVERSION" as const;
  if (ratio >= 0.5) return "MODERATE_CASH_CONVERSION" as const;
  return "WEAK_CASH_CONVERSION" as const;
}

export function classifyFinancialMetric(metric: FinancialMetric, table: FinancialTable | undefined, quarterlyOcfRatio?: string): FinancialMetricStatus | null {
  if (metric.label === "Return on Equity (ROE)") {
    const values = getFinancialMetricRow(table, metric.label)?.values ?? [];
    const latestValue = parseFinancialMetricValue(values.at(-1));
    const previousValues = values.slice(0, -1).map(parseFinancialMetricValue);
    const fiveYearAverage = previousValues.reduce((sum, value) => sum + value, 0) / previousValues.length;
    if (latestValue > fiveYearAverage) return "ABOVE_AVERAGE";
    if (latestValue < fiveYearAverage) return "BELOW_AVERAGE";
    return "IN_LINE_WITH_AVERAGE";
  }
  if (metric.label === "Gross Margin") return classifyMargin(table, metric.label, "EXPANDING");
  if (metric.label === "Net Margin") return classifyMargin(table, metric.label, "IMPROVING");
  if (metric.label === "OCF / Net Income") return classifyCashConversion(metric.value);
  if (metric.label === "Operating Cash Flow") return classifyCashConversion(quarterlyOcfRatio);
  return null;
}

export function financialMetricStatusLabel(status: FinancialMetricStatus) {
  const labels: Record<FinancialMetricStatus, string> = {
    EXPANDING: "Expanding margin", CONTRACTING: "Contracting margin", STABLE_MARGIN: "Stable margin",
    IMPROVING: "Improving margin", DECLINING: "Declining margin", STRONG_CASH_CONVERSION: "Strong cash conversion",
    MODERATE_CASH_CONVERSION: "Moderate cash conversion", WEAK_CASH_CONVERSION: "Weak cash conversion",
    ABOVE_AVERAGE: "Above 5-year average", BELOW_AVERAGE: "Below 5-year average", IN_LINE_WITH_AVERAGE: "In line with 5-year average",
  };
  return labels[status];
}
