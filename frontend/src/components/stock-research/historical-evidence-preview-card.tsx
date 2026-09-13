import React from "react";
import { StockDetail } from "@/data/mock-stock-details";
import { SectionCard } from "@/components/ui/section-card";

export function HistoricalEvidencePreviewCard({
  evidence,
}: {
  evidence: StockDetail["historicalEvidencePreview"];
}) {
  const maxReturn = 60;

  return (
    <SectionCard
      icon={<ClockIcon className="h-4 w-4" />}
      title="Historical Evidence Preview"
      subtitle="Similar valuation conditions · Historical results over the next 12 months"
      actionSlot={
        <a
          href="#backtest"
          className="flex items-center gap-1 text-xs font-semibold text-[#f2bb5c] transition hover:text-[#ffd68a]"
        >
          <span>View Backtest</span>
          <ArrowRightIcon className="h-3.5 w-3.5" />
        </a>
      }
    >
      <div className="flex items-start justify-between gap-6">
        {/* Left Stats Column */}
        <div className="w-48 space-y-2 text-xs">
          <div className="flex items-center justify-between">
            <span className="text-[#8e9bb0]">Total cases</span>
            <span className="font-semibold text-white">{evidence.totalCases}</span>
          </div>
          <div className="flex items-center justify-between">
            <span className="text-[#8e9bb0]">Positive results</span>
            <span className="font-semibold text-white">{evidence.positiveResults}</span>
          </div>
          <div className="flex items-center justify-between">
            <span className="text-[#8e9bb0]">Median return</span>
            <span className="font-semibold text-[#3ef0a9]">
              +{evidence.medianReturn.toFixed(1).replace(".", ",")}%
            </span>
          </div>
          <div className="flex items-center justify-between">
            <span className="text-[#8e9bb0]">Worst result</span>
            <span className="font-semibold text-[#3ef0a9]">
              +{evidence.worstResult.toFixed(1).replace(".", ",")}%
            </span>
          </div>
          <div className="flex items-center justify-between">
            <span className="text-[#8e9bb0]">Best result</span>
            <span className="font-semibold text-[#3ef0a9]">
              +{evidence.bestResult.toFixed(1).replace(".", ",")}%
            </span>
          </div>
        </div>

        {/* Right Bar Chart Column */}
        <div className="relative flex-1 rounded-xl border border-white/8 bg-[#07111c]/80 p-4">
          <div className="flex h-28 items-end justify-around border-b border-white/10 pb-2">
            {evidence.cases.map((c) => {
              const heightPct = Math.round((c.returnPercent / maxReturn) * 100);
              return (
                <div key={c.caseName} className="flex flex-col items-center gap-1">
                  <div className="h-20 w-8 flex items-end justify-center rounded-t bg-white/5">
                    <div
                      className="w-full rounded-t bg-[#3ef0a9]"
                      style={{ height: `${heightPct}%` }}
                    />
                  </div>
                  <span className="text-[10px] text-[#7f8c9f]">{c.caseName}</span>
                </div>
              );
            })}
          </div>

          {/* Y Axis Ticks */}
          <div className="mt-1 flex justify-between text-[9px] text-[#7f8c9f]">
            <span>-30%</span>
            <span>0%</span>
            <span>30%</span>
            <span>60%</span>
          </div>
        </div>
      </div>
    </SectionCard>
  );
}

function ClockIcon({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className={className} aria-hidden="true">
      <circle cx="12" cy="12" r="10" />
      <polyline points="12 6 12 12 16 14" />
    </svg>
  );
}

function ArrowRightIcon({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className={className} aria-hidden="true">
      <line x1="5" y1="12" x2="19" y2="12" />
      <polyline points="12 5 19 12 12 19" />
    </svg>
  );
}

