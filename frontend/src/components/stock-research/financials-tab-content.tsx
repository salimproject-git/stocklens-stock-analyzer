"use client";

import React, { useState } from "react";
import { StockDetail } from "@/data/mock-stock-details";
import { FinancialTrendCard } from "./financial-trend-card";
import { FinancialMetricsSummary } from "./financial-metrics-summary";
import { HistoricalFinancialTable } from "./historical-financial-table";

type PeriodType = "annual" | "quarterly";

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

      {/* 3 Key Financial Trend Cards */}
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        {data.trendCards.map((card) => (
          <FinancialTrendCard key={card.id} card={card} />
        ))}
      </div>

      {/* Key Financial Metrics Section */}
      <FinancialMetricsSummary metrics={data.keyMetrics} />

      {/* Historical Financial Table */}
      <HistoricalFinancialTable table={data.table} />
    </div>
  );
}

