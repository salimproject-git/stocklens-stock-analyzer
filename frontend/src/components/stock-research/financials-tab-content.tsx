"use client";

import React, { useState } from "react";
import { StockDetail } from "@/data/mock-stock-details";
import { FinancialTrendCard } from "./financial-trend-card";
import { FinancialMetricsSummary } from "./financial-metrics-summary";
import { HistoricalFinancialTable } from "./historical-financial-table";

type PeriodType = "annual" | "quarterly";
type FinancialMetric = NonNullable<StockDetail["financialHistory"]>["annualMetrics"][number];
type FinancialTable = NonNullable<StockDetail["financialHistory"]>["annualTable"];

function getQuarterIndex(label: string) {
  const match = label.match(/^Q([1-4])\s+(\d{4})$/);
  return match ? Number(match[2]) * 4 + Number(match[1]) : -1;
}

function getLatestQuarters<T extends { year: string }>(series: T[]) {
  return [...series]
    .sort((a, b) => getQuarterIndex(a.year) - getQuarterIndex(b.year))
    .slice(-5);
}

function parseMetricValue(value: string) {
  return Number(value.replace(",", ".").replace("%", "").replace("x", ""));
}

function getMetricRow(table: FinancialTable | undefined, label: string) {
  return table?.rows.find((row) => row.metric.startsWith(label));
}

function getMarginContext(table: FinancialTable | undefined, label: string, improvingLabel: string, decliningLabel: string) {
  const values = getMetricRow(table, label)?.values ?? [];
  const latestValue = parseMetricValue(values.at(-1) ?? "0");
  const previousValue = parseMetricValue(values.at(-2) ?? "0");
  const change = latestValue - previousValue;

  if (change > 0.5) return improvingLabel;
  if (change < -0.5) return decliningLabel;
  return "Stable margin";
}

function getCashConversionContext(ratioValue: string | undefined) {
  const ratio = parseMetricValue(ratioValue ?? "0");
  if (ratio >= 1) return "Strong cash conversion";
  if (ratio >= 0.5) return "Moderate cash conversion";
  return "Weak cash conversion";
}

function getMetricContext(
  metric: FinancialMetric,
  table: FinancialTable | undefined,
  quarterlyOcfRatio?: string,
) {
  if (metric.label === "Return on Equity (ROE)") {
    const values = getMetricRow(table, metric.label)?.values ?? [];
    const latestValue = parseMetricValue(values.at(-1) ?? "0");
    const previousValues = values.slice(0, -1).map(parseMetricValue);
    const fiveYearAverage = previousValues.reduce((sum, value) => sum + value, 0) / previousValues.length;

    if (latestValue > fiveYearAverage) return "Above 5-year average";
    if (latestValue < fiveYearAverage) return "Below 5-year average";
    return "In line with 5-year average";
  }

  if (metric.label === "Gross Margin") {
    return getMarginContext(table, metric.label, "Expanding margin", "Contracting margin");
  }

  if (metric.label === "Net Margin") {
    return getMarginContext(table, metric.label, "Improving margin", "Declining margin");
  }

  if (metric.label === "OCF / Net Income") {
    return getCashConversionContext(metric.value);
  }

  if (metric.label === "Operating Cash Flow") {
    return getCashConversionContext(quarterlyOcfRatio);
  }

  const units: Record<string, string> = {
    "Operating Profit": "Rp Trillion",
    "Total Assets": "Rp Trillion",
    "Total Equity": "Rp Trillion",
    "Total Liabilities": "Rp Trillion",
    "Interest Expense": "M Rp",
  };

  return units[metric.label] ?? metric.subtext;
}

export function FinancialsTabContent({ stock }: { stock: StockDetail }) {
  const [period, setPeriod] = useState<PeriodType>("annual");

  const data = stock.financialHistory;

  if (!data) {
    return (
      <div className="rounded-[20px] border border-white/10 bg-[#07111c]/80 p-8 text-center text-sm text-[#9aa9bf]">
        Financial history data is not available for {stock.ticker}.
      </div>
    );
  }

  const isAnnual = period === "annual";
  const trendCards = isAnnual
    ? data.annualTrendCards
    : data.quarterlyTrendCards.map((card) => ({
        ...card,
        series: getLatestQuarters(card.series),
      }));
  const table = isAnnual ? data.annualTable : data.quarterlyTable;
  const sourceMetrics = isAnnual ? data.annualMetrics : data.quarterlyMetrics;
  const quarterlyOcfRatio = stock.thesisValidator.rows.find(
    (row) => row.item === "OCF / NI Ratio (x)",
  )?.q2;
  const metrics = sourceMetrics.map((metric) => ({
    ...metric,
    subtext: getMetricContext(metric, table, quarterlyOcfRatio),
  }));

  return (
    <div className="space-y-6">
      {/* Header Section */}
      <div className="flex flex-col justify-between gap-4 md:flex-row md:items-center">
        <div>
          <h2 className="text-3xl font-bold tracking-tight text-white">
            Financial History
          </h2>

          <p className="mt-1 text-sm text-[#aeb9ca]">
            {data.subtitle}
          </p>
        </div>

        {/* Period Toggle */}
        <div className="flex items-center gap-1 self-start rounded-xl border border-white/10 bg-[#091322]/80 p-1 text-xs md:self-auto">
          <button
            type="button"
            onClick={() => setPeriod("annual")}
            className={[
              "rounded-lg px-4 py-1.5 font-semibold transition",
              period === "annual"
                ? "bg-[#f2bb5c] text-[#1d170f]"
                : "text-[#9aa9bf] hover:bg-white/5 hover:text-white",
            ].join(" ")}
          >
            Annual
          </button>

          <button
            type="button"
            onClick={() => setPeriod("quarterly")}
            className={[
              "rounded-lg px-4 py-1.5 font-semibold transition",
              period === "quarterly"
                ? "bg-[#f2bb5c] text-[#1d170f]"
                : "text-[#9aa9bf] hover:bg-white/5 hover:text-white",
            ].join(" ")}
          >
            Quarterly
          </button>
        </div>
      </div>

      {/* Primary Financial Trend Cards */}
      <div className="grid grid-cols-1 gap-6 sm:grid-cols-2 lg:grid-cols-3">
        {trendCards.map((card) => (
          <FinancialTrendCard key={card.id} card={card} />
        ))}
      </div>

      {/* Supporting Financial Metrics */}
      <FinancialMetricsSummary metrics={metrics} />

      {/* Historical Financial Table */}
      {table ? (
        <HistoricalFinancialTable table={table} />
      ) : (
        <div className="rounded-2xl border border-white/10 bg-[#07111c]/80 p-6 text-center text-sm text-[#9aa9bf]">
          {isAnnual ? "Annual" : "Quarterly"} financial history is not
          available for {stock.ticker}.
        </div>
      )}
    </div>
  );
}
