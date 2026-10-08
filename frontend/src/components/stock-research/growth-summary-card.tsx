import React from "react";
import { StockDetail } from "@/data/stock-detail-types";
import { SectionCard } from "@/components/ui/section-card";

export function GrowthSummaryCard({
  growth,
}: {
  growth: StockDetail["growthSummary"];
}) {
  const revenueGrowth = growth.metrics.find(
    (metric) => metric.label === "Revenue Growth (3Y CAGR)",
  );

  const netIncomeGrowth = growth.metrics.find(
    (metric) => metric.label === "Net Income Growth (3Y CAGR)",
  );

  const epsGrowth = growth.metrics.find(
    (metric) => metric.label === "EPS Growth (3Y CAGR)",
  );

  const formatNumber = (value: string) => value.replace(",", ".");

  const annual = growth.annualPerformance;

  return (
    <SectionCard
      icon={<TrendingUpIcon className="h-4 w-4" />}
      title="Financial Summary"
      actionSlot={
        <a
          href="#financials"
          className="text-xs font-semibold text-[#f4d18b] transition hover:text-[#ffd68a]"
        >
          View Financials →
        </a>
      }
    >
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
        {/* Historical Growth */}
        <div className="rounded-xl border border-white/8 bg-[#07111c]/60 p-3.5 lg:col-span-2">
          <div className="text-[12px] font-semibold text-[#d4dcec]">
            Historical Growth
          </div>

          <div className="mt-3 space-y-2 text-xs">
            <div className="flex items-center justify-between gap-3">
              <span className="text-[#8e9bb0]">Revenue CAGR</span>
              <span className="font-semibold text-white">
                {revenueGrowth
                  ? formatNumber(revenueGrowth.value)
                  : "â€”"}
              </span>
            </div>

            <div className="flex items-center justify-between gap-3">
              <span className="text-[#8e9bb0]">Net Income CAGR</span>
              <span className="font-semibold text-white">
                {netIncomeGrowth
                  ? formatNumber(netIncomeGrowth.value)
                  : "â€”"}
              </span>
            </div>

            <div className="flex items-center justify-between gap-3">
              <span className="text-[#8e9bb0]">EPS CAGR</span>
              <span className="font-semibold text-white">
                {epsGrowth ? formatNumber(epsGrowth.value) : "â€”"}
              </span>
            </div>
          </div>
        </div>

        {/* Latest Annual Performance */}
        <div className="rounded-xl border border-white/8 bg-[#07111c]/60 p-3.5 lg:col-span-3">
          <div className="flex items-baseline justify-between gap-2">
            <div className="text-[12px] font-semibold text-[#d4dcec]">
              Latest Annual Performance
            </div>
            <div className="shrink-0 text-[10px] text-[#8090a7]">{annual.period}</div>
          </div>

          <div className="mt-3 space-y-2 text-xs">
            <div className="flex items-center justify-between gap-3">
              <span className="text-[#8e9bb0]">Revenue Growth</span>
              <span className="font-semibold text-white">{formatNumber(annual.revenueGrowth)}</span>
            </div>

            <div className="flex items-center justify-between gap-3">
              <span className="text-[#8e9bb0]">Net Income Growth</span>
              <span className="font-semibold text-white">{formatNumber(annual.netIncomeGrowth)}</span>
            </div>

            <div className="flex items-center justify-between gap-3">
              <span className="text-[#8e9bb0]">Gross Margin</span>
              <span className="font-semibold text-white">{formatNumber(annual.grossMargin)}</span>
            </div>

            <div className="flex items-center justify-between gap-3">
              <span className="text-[#8e9bb0]">OCF / Net Income</span>
              <span className="font-semibold text-white">{formatNumber(annual.ocfNetIncome)}</span>
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
