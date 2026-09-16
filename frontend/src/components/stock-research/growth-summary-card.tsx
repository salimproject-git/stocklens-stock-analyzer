import React from "react";
import { StockDetail } from "@/data/mock-stock-details";
import { SectionCard } from "@/components/ui/section-card";

export function GrowthSummaryCard({
  growth,
  validator,
}: {
  growth: StockDetail["growthSummary"];
  validator: StockDetail["thesisValidator"];
}) {
  const revenueRow = validator.rows.find(
    (row) => row.item === "Revenue YoY (%)",
  );

  const netIncomeRow = validator.rows.find(
    (row) => row.item === "Net Income YoY (%)",
  );

  const grossMarginRow = validator.rows.find(
    (row) => row.item === "Gross Margin (Actual %)",
  );

  const ocfNetIncomeRow = validator.rows.find(
    (row) => row.item === "OCF / NI Ratio (x)",
  );

  const revenueGrowth = growth.metrics.find(
    (metric) => metric.label === "Revenue Growth (3Y CAGR)",
  );

  const netIncomeGrowth = growth.metrics.find(
    (metric) => metric.label === "Net Income Growth (3Y CAGR)",
  );

  const epsGrowth = growth.metrics.find(
    (metric) => metric.label === "EPS Growth (3Y CAGR)",
  );

  const formatNumber = (value: string) => {
    return value.replace(",", ".");
  };

  const translateTrend = (trend: string) => {
    return trend
      .replace("Naik", "Up")
      .replace("Turun", "Down")
      .replace("Stabil", "Stable")
      .replace("Cukup", "Fair");
  };

  const getTrendClass = (
    tone: StockDetail["thesisValidator"]["rows"][number]["trendTone"],
  ) => {
    if (tone === "green") return "text-[#3ef0a9]";
    if (tone === "yellow") return "text-[#f59e0b]";
    if (tone === "red") return "text-[#ef4444]";
    return "text-[#b6c2d4]";
  };

  const renderTrend = (
    row: StockDetail["thesisValidator"]["rows"][number] | undefined,
  ) => {
    if (!row) {
      return <span className="font-semibold text-white">—</span>;
    }

    return (
      <span
        className={`font-semibold ${getTrendClass(row.trendTone)}`}
      >
        {translateTrend(row.trend).replace(",", ".")}
      </span>
    );
  };

  return (
    <SectionCard
      icon={<TrendingUpIcon className="h-4 w-4" />}
      title="Growth Summary"
      actionSlot={
        <span className="text-xs font-semibold text-[#f4d18b]">
          View Growth →
        </span>
      }
    >
      <div className="grid gap-3 sm:grid-cols-2">
        {/* Historical Growth */}
        <div className="rounded-xl border border-white/8 bg-[#07111c]/60 p-3.5">
          <div className="text-[12px] font-semibold text-[#d4dcec]">
            Historical Growth
          </div>

          <div className="mt-3 space-y-2 text-xs">
            <div className="flex items-center justify-between gap-3">
              <span className="text-[#8e9bb0]">Revenue CAGR</span>
              <span className="font-semibold text-white">
                {revenueGrowth
                  ? formatNumber(revenueGrowth.value)
                  : "—"}
              </span>
            </div>

            <div className="flex items-center justify-between gap-3">
              <span className="text-[#8e9bb0]">Net Income CAGR</span>
              <span className="font-semibold text-white">
                {netIncomeGrowth
                  ? formatNumber(netIncomeGrowth.value)
                  : "—"}
              </span>
            </div>

            <div className="flex items-center justify-between gap-3">
              <span className="text-[#8e9bb0]">EPS CAGR</span>
              <span className="font-semibold text-white">
                {epsGrowth ? formatNumber(epsGrowth.value) : "—"}
              </span>
            </div>
          </div>
        </div>

        {/* Latest Performance */}
        <div className="rounded-xl border border-white/8 bg-[#07111c]/60 p-3.5">
          <div className="text-[12px] font-semibold text-[#d4dcec]">
            Latest Performance
          </div>

          <div className="mt-3 space-y-2 text-xs">
            <div className="flex items-center justify-between gap-3">
              <span className="text-[#8e9bb0]">Revenue YoY</span>
              {renderTrend(revenueRow)}
            </div>

            <div className="flex items-center justify-between gap-3">
              <span className="text-[#8e9bb0]">Net Income YoY</span>
              {renderTrend(netIncomeRow)}
            </div>

            <div className="flex items-center justify-between gap-3">
              <span className="text-[#8e9bb0]">Gross Margin</span>
              {renderTrend(grossMarginRow)}
            </div>

            <div className="flex items-center justify-between gap-3">
              <span className="text-[#8e9bb0]">OCF / Net Income</span>
              {renderTrend(ocfNetIncomeRow)}
            </div>
          </div>
        </div>
      </div>
    </SectionCard>
  );
}

function TrendingUpIcon({ className }: { className?: string }) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      className={className}
      aria-hidden="true"
    >
      <polyline points="3 17 9 11 13 15 21 7" />
      <polyline points="14 7 21 7 21 14" />
    </svg>
  );
}