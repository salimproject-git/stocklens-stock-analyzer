"use client";

import React, { useState } from "react";
import { StockDetail } from "@/data/mock-stock-details";
import { FinancialTrendCard } from "./financial-trend-card";
import { FinancialMetricsSummary } from "./financial-metrics-summary";
import { HistoricalFinancialTable } from "./historical-financial-table";
import { classifyFinancialMetric } from "@/lib/analysis";

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

function getMetricContext(
  metric: FinancialMetric,
  table: FinancialTable | undefined,
  quarterlyOcfRatio?: string,
) {
  const status = classifyFinancialMetric(metric, table, quarterlyOcfRatio);
  if (status) {
    const labels = {
      EXPANDING: "Expanding margin",
      CONTRACTING: "Contracting margin",
      STABLE_MARGIN: "Stable margin",
      IMPROVING: "Improving margin",
      DECLINING: "Declining margin",
      STRONG_CASH_CONVERSION: "Strong cash conversion",
      MODERATE_CASH_CONVERSION: "Moderate cash conversion",
      WEAK_CASH_CONVERSION: "Weak cash conversion",
      ABOVE_AVERAGE: "Above 5-year average",
      BELOW_AVERAGE: "Below 5-year average",
      IN_LINE_WITH_AVERAGE: "In line with 5-year average",
    } as const;
    return labels[status];
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
