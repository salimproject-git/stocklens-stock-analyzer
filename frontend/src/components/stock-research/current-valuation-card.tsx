import React from "react";
import { StockDetail } from "@/data/mock-stock-details";
import { SectionCard } from "@/components/ui/section-card";
import { StatusBadge } from "@/components/ui/status-badge";

export function CurrentValuationCard({
  valuation,
}: {
  valuation: StockDetail["currentValuation"];
}) {
  const currentRatio = valuation.currentPrice / valuation.intrinsicValue;
  const currentHeightPercent = Math.round(currentRatio * 100);

  return (
    <SectionCard
      icon={<LayersIcon className="h-4 w-4" />}
      title="Current Valuation"
    >
      <div className="flex items-center justify-between gap-6">
        {/* Left Side: Summary metrics */}
        <div className="flex-1 space-y-3">
          <StatusBadge tone="undervalued" className="text-xs">
            {valuation.verdict.toUpperCase()}
          </StatusBadge>

          <div className="space-y-2 pt-1 text-xs">
            <div className="flex items-center justify-between">
              <span className="text-[#8e9bb0]">Current Price</span>
              <span className="font-semibold text-white">
                Rp {new Intl.NumberFormat("id-ID").format(valuation.currentPrice)}
              </span>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-[#8e9bb0]">Intrinsic Value</span>
              <span className="font-semibold text-white">
                Rp {new Intl.NumberFormat("id-ID").format(valuation.intrinsicValue)}
              </span>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-[#8e9bb0]">Margin of Safety</span>
              <span className="font-semibold text-[#3ef0a9]">
                {valuation.mos.toFixed(1).replace(".", ",")}%
              </span>
            </div>
          </div>
        </div>

        {/* Right Side: Visual Bar Chart comparison */}
        <div className="flex items-end gap-5 rounded-xl border border-white/8 bg-[#07111c]/80 p-4">
          {/* Current Price Bar */}
          <div className="flex flex-col items-center">
            <span className="mb-1 text-[11px] font-semibold text-[#b6c2d4]">
              {new Intl.NumberFormat("id-ID").format(valuation.currentPrice)}
            </span>
            <div className="h-28 w-10 overflow-hidden rounded-t-md bg-white/5 flex items-end">
              <div
                className="w-full rounded-t-md bg-[#33465e]"
                style={{ height: `${currentHeightPercent}%` }}
              />
            </div>
            <span className="mt-2 max-w-[60px] text-center text-[10px] text-[#7f8c9f]">
              Current Price
            </span>
          </div>

          {/* Intrinsic Value Bar */}
          <div className="flex flex-col items-center">
            <span className="mb-1 text-[11px] font-semibold text-[#f4d18b]">
              {new Intl.NumberFormat("id-ID").format(valuation.intrinsicValue)}
            </span>
            <div className="h-28 w-10 overflow-hidden rounded-t-md bg-white/5 flex items-end">
              <div className="h-full w-full rounded-t-md bg-[linear-gradient(180deg,_#f5c15d,_#c28b2e)]" />
            </div>
            <span className="mt-2 max-w-[60px] text-center text-[10px] text-[#7f8c9f]">
              Intrinsic Value
            </span>
          </div>
        </div>
      </div>
    </SectionCard>
  );
}

function LayersIcon({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className={className} aria-hidden="true">
      <polygon points="12 2 2 7 12 12 22 7 12 2" />
      <polyline points="2 17 12 22 22 17" />
      <polyline points="2 12 12 17 22 12" />
    </svg>
  );
}

