import React from "react";
import { StockDetail } from "@/data/mock-stock-details";
import { SectionCard } from "@/components/ui/section-card";

export function ThesisValidatorCard({
  validator,
}: {
  validator: StockDetail["thesisValidator"];
}) {
  const latestQuarter =
    validator.quarters[validator.quarters.length - 1] ?? "Latest";

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

  const getTrendClass = (
    tone: StockDetail["thesisValidator"]["rows"][number]["trendTone"],
  ) => {
    if (tone === "green") return "text-[#3ef0a9]";
    if (tone === "yellow") return "text-[#f59e0b]";
    if (tone === "red") return "text-[#ef4444]";
    return "text-[#b6c2d4]";
  };

  const translateTrend = (trend: string) => {
    return trend
      .replace("Naik", "Up")
      .replace("Turun", "Down")
      .replace("Stabil", "Stable")
      .replace("Cukup", "Fair");
  };

  const renderTrend = (
    row: StockDetail["thesisValidator"]["rows"][number] | undefined,
  ) => {
    if (!row) {
      return <span className="font-semibold text-white">—</span>;
    }

    return (
      <span className={`font-semibold ${getTrendClass(row.trendTone)}`}>
        {translateTrend(row.trend)}
      </span>
    );
  };

  return (
    <SectionCard
      icon={<SparklesIcon className="h-4 w-4" />}
      title="Thesis Validator"
      subtitle={`Latest Quarter · ${latestQuarter}`}
      actionSlot={
        <span className="text-xs font-semibold text-[#f4d18b]">
          Growth
        </span>
      }
    >
      <div className="grid grid-cols-2 gap-2.5">
        <div className="rounded-xl border border-white/6 bg-[#07111c]/60 p-3">
          <div className="text-[11px] text-[#8e9bb0]">Revenue YoY</div>

          <div className="mt-1">
            {renderTrend(revenueRow)}
          </div>
        </div>

        <div className="rounded-xl border border-white/6 bg-[#07111c]/60 p-3">
          <div className="text-[11px] text-[#8e9bb0]">Net Income YoY</div>

          <div className="mt-1">
            {renderTrend(netIncomeRow)}
          </div>
        </div>

        <div className="rounded-xl border border-white/6 bg-[#07111c]/60 p-3">
          <div className="text-[11px] text-[#8e9bb0]">Gross Margin</div>

          <div className="mt-1">
            {renderTrend(grossMarginRow)}
          </div>
        </div>

        <div className="rounded-xl border border-white/6 bg-[#07111c]/60 p-3">
          <div className="text-[11px] text-[#8e9bb0]">OCF / Net Income</div>

          <div className="mt-1">
            {renderTrend(ocfNetIncomeRow)}
          </div>
        </div>
      </div>
    </SectionCard>
  );
}

function SparklesIcon({ className }: { className?: string }) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      className={className}
      aria-hidden="true"
    >
      <path d="m12 3-1.9 5.8a2 2 0 0 1-1.3 1.3L3 12l5.8 1.9a2 2 0 0 1 1.3 1.3L12 21l1.9-5.8a2 2 0 0 1-1.3-1.3L21 12l-5.8-1.9a2 2 0 0 1-1.3-1.3L12 3Z" />
    </svg>
  );
}