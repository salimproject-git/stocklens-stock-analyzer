import React from "react";
import { StockDetail } from "@/data/mock-stock-details";
import { SectionCard } from "@/components/ui/section-card";

export function HistoricalEvidencePreviewCard({
  evidence,
}: {
  evidence: StockDetail["historicalEvidencePreview"];
}) {
  return (
    <SectionCard
      icon={<HistoryIcon className="h-4 w-4" />}
      title="Historical Evidence"
      subtitle={`Similar valuation conditions · historical outcomes · ${evidence.totalCases} Cases`}
      actionSlot={
        <span className="text-xs font-semibold text-[#f4d18b]">
          View Backtest →
        </span>
      }
    >
      <div className="grid gap-3 sm:grid-cols-2">
        {/* Verdict Based Method */}
        <div className="rounded-xl border border-white/8 bg-[#07111c]/60 p-3.5">
          <div className="text-[12px] font-semibold text-[#d4dcec]">
            Verdict Based Method
          </div>

          <div className="mt-3 space-y-2 text-xs">
            <div className="flex items-center justify-between gap-3">
              <span className="text-[#8e9bb0]">Undervalued</span>
              <span className="font-semibold text-white">
                {evidence.verdictMethod.undervalued}
              </span>
            </div>

            <div className="flex items-center justify-between gap-3">
              <span className="text-[#8e9bb0]">Overvalued</span>
              <span className="font-semibold text-white">
                {evidence.verdictMethod.overvalued}
              </span>
            </div>
          </div>

          <div className="mt-3 border-t border-white/8 pt-2.5">
            <span className="text-xs font-semibold text-[#3ef0a9]">
              {evidence.verdictMethod.wins} WIN
            </span>
            <span className="ml-2 text-[11px] text-[#7f8c9f]">
              · {evidence.verdictMethod.winRate}
            </span>
          </div>
        </div>

        {/* Verdict Based MoS */}
        <div className="rounded-xl border border-white/8 bg-[#07111c]/60 p-3.5">
          <div className="text-[12px] font-semibold text-[#d4dcec]">
            Verdict Based MoS
          </div>

          <div className="mt-3 space-y-2 text-xs">
            <div className="flex items-center justify-between gap-3">
              <span className="text-[#8e9bb0]">Undervalued</span>
              <span className="font-semibold text-white">
                {evidence.verdictMos.undervalued}
              </span>
            </div>

            <div className="flex items-center justify-between gap-3">
              <span className="text-[#8e9bb0]">Overvalued</span>
              <span className="font-semibold text-white">
                {evidence.verdictMos.overvalued}
              </span>
            </div>
          </div>

          <div className="mt-3 border-t border-white/8 pt-2.5">
            <span className="text-xs font-semibold text-[#3ef0a9]">
              {evidence.verdictMos.wins} WIN
            </span>
            <span className="ml-2 text-[11px] text-[#7f8c9f]">
              · {evidence.verdictMos.winRate}
            </span>
          </div>
        </div>
      </div>

      <div className="mt-3 flex items-start gap-2.5 rounded-xl border border-[#d6a24d]/40 bg-[#2b2212]/80 p-3 text-[11px] leading-relaxed text-[#f4d18b]">
        <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full border border-[#d6a24d]/50 bg-[#f2bb5c]/20 text-xs">
          💡
        </span>

        <span>
          A WIN means an undervalued case reached the +20% target before the -20% downside
        </span>
      </div>
    </SectionCard>
  );
}

function HistoryIcon({ className }: { className?: string }) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      className={className}
      aria-hidden="true"
    >
      <path d="M3 12a9 9 0 1 0 3-6.7" />
      <polyline points="3 4 3 9 8 9" />
      <polyline points="12 7 12 12 15 14" />
    </svg>
  );
}