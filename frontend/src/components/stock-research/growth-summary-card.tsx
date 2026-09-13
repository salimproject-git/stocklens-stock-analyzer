import React from "react";
import { StockDetail } from "@/data/mock-stock-details";
import { SectionCard } from "@/components/ui/section-card";
import { StatusBadge } from "@/components/ui/status-badge";

export function GrowthSummaryCard({
  growth,
}: {
  growth: StockDetail["growthSummary"];
}) {
  return (
    <SectionCard
      icon={<TrendingUpIcon className="h-4 w-4" />}
      title="Growth Summary"
    >
      <div className="space-y-3">
        {growth.metrics.map((m) => {
          const tone =
            m.badge === "Positive"
              ? "positive"
              : m.badge === "Stable"
                ? "stable"
                : "caution";

          return (
            <div
              key={m.label}
              className="flex items-center justify-between gap-4 rounded-xl border border-white/6 bg-[#07111c]/60 p-3 text-xs"
            >
              <div className="flex items-center gap-3">
                <span className="w-44 font-medium text-[#8e9bb0]">{m.label}</span>
                <span className="w-16 font-semibold text-[#3ef0a9]">{m.value}</span>
                <StatusBadge tone={tone}>{m.badge}</StatusBadge>
              </div>
              <span className="text-[11px] text-[#7f8c9f]">{m.subtext}</span>
            </div>
          );
        })}
      </div>
    </SectionCard>
  );
}

function TrendingUpIcon({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className={className} aria-hidden="true">
      <polyline points="23 6 13.5 15.5 8.5 10.5 1 18" />
      <polyline points="17 6 23 6 23 12" />
    </svg>
  );
}

