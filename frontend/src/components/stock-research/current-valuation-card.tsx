import React from "react";
import { StockDetail } from "@/data/mock-stock-details";
import { SectionCard } from "@/components/ui/section-card";
import { StatusBadge } from "@/components/ui/status-badge";
import { formatRupiah } from "@/utils/currency";
import { classifyCurrentValuationMos } from "@/lib/analysis";

export function CurrentValuationCard({
  valuation,
}: {
  valuation: StockDetail["currentValuation"];
}) {
  const currentRatio = valuation.currentPrice / valuation.intrinsicValue;
  const currentHeightPercent = Math.round(currentRatio * 100);

  const formattedMos = valuation.mos.toFixed(1).replace(".", ",");

  const verdictText =
    valuation.verdict.toLowerCase() === "undervalued"
      ? "Most valuation methods indicate the stock is trading below its estimated value"
      : "Most valuation methods indicate the stock is trading above its estimated value";

  const mosUndervalued = classifyCurrentValuationMos(valuation.mos) === "UNDERVALUED";

const mosText = mosUndervalued
  ? `Margin of safety is ${formattedMos}%, indicating undervalued with discount to intrinsic value.`
  : `Margin of safety is ${formattedMos}%, indicating overvalued with limited valuation cushion.`;

  return (
    <SectionCard
      icon={<LayersIcon className="h-4 w-4" />}
      title="Current Valuation"
      subtitle="Based on multiple valuation methods and margin of safety"
      actionSlot={
        <span className="text-xs font-semibold text-[#f4d18b]">
          View Valuation →
        </span>
      }
    >
      <div className="grid gap-4 lg:grid-cols-3">
  {/* Based Method */}
  <div className="rounded-xl border border-white/8 bg-[#07111c]/60 p-3.5">
    <div className="text-[12px] font-semibold text-[#d4dcec]">
      Based Method
    </div>

    <div className="mt-3">
      <StatusBadge tone="undervalued" className="text-xs">
        {valuation.verdict.toUpperCase()}
      </StatusBadge>
    </div>

    <p className="mt-3 text-[11px] leading-relaxed text-[#8e9bb0]">
      {verdictText}
    </p>
  </div>

  {/* Based MoS */}
  <div className="rounded-xl border border-white/8 bg-[#07111c]/60 p-3.5">
    <div className="text-[12px] font-semibold text-[#d4dcec]">
      Based MoS
    </div>

    <div className="mt-2">
  <StatusBadge
    tone={mosUndervalued ? "undervalued" : "overvalued"}
    className="text-xs"
  >
    {mosUndervalued ? "UNDERVALUED" : "OVERVALUED"}
  </StatusBadge>
</div>

    <p className="mt-3 text-[11px] leading-relaxed text-[#8e9bb0]">
      {mosText}
    </p>
  </div>

  {/* Valuation Comparison */}
  <div className="rounded-xl border border-white/8 bg-[#07111c]/60 p-4">
    <div className="flex items-end justify-center gap-10">
      {/* Current Price */}
      <div className="flex w-16 flex-col items-center">
        <span className="mb-2 text-center text-[12px] font-semibold text-[#b6c2d4]">
          {formatRupiah(valuation.currentPrice)}
        </span>

        <div className="flex h-[80px] w-14 items-end overflow-hidden rounded-t-md bg-white/5">
          <div
            className="w-full rounded-t-md bg-[#33465e]"
            style={{
              height: `${Math.max(currentHeightPercent, 8)}%`,
            }}
          />
        </div>

        <span className="mt-2 text-center text-[11px] text-[#7f8c9f]">
          Current Price
        </span>
      </div>

      {/* Intrinsic Value */}
      <div className="flex w-16 flex-col items-center">
        <span className="mb-2 text-center text-[12px] font-semibold text-[#f4d18b]">
          {formatRupiah(valuation.intrinsicValue)}
        </span>

        <div className="flex h-[80px] w-14 items-end overflow-hidden rounded-t-md bg-white/5">
          <div className="h-full w-full rounded-t-md bg-[linear-gradient(180deg,_#f5c15d,_#c28b2e)]" />
        </div>

        <span className="mt-2 text-center text-[11px] text-[#7f8c9f]">
          Intrinsic Value
        </span>
      </div>
    </div>
  </div>
</div>
    </SectionCard>
  );
}

function LayersIcon({ className }: { className?: string }) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      className={className}
      aria-hidden="true"
    >
      <polygon points="12 2 2 7 12 12 22 7 12 2" />
      <polyline points="2 17 12 22 22 17" />
      <polyline points="2 12 12 17 22 12" />
    </svg>
  );
}
