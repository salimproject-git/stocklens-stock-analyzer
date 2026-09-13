import React from "react";
import { StockDetail } from "@/data/mock-stock-details";
import { SectionCard } from "@/components/ui/section-card";
import { StatusBadge } from "@/components/ui/status-badge";

export function FinancialHealthCard({
  health,
}: {
  health: StockDetail["financialHealth"];
}) {
  return (
    <SectionCard
      icon={<ActivityIcon className="h-4 w-4" />}
      title="Financial Health"
    >
      <div className="space-y-3">
        {health.metrics.map((m) => {
          const tone =
            m.badge === "Healthy"
              ? "healthy"
              : m.badge === "Stable"
                ? "stable"
                : "caution";

          return (
            <div
              key={m.label}
              className="flex items-center justify-between gap-4 rounded-xl border border-white/6 bg-[#07111c]/60 p-3 text-xs"
            >
              <div className="flex items-center gap-3">
                <span className="w-32 font-medium text-[#8e9bb0]">{m.label}</span>
                <span className="w-16 font-semibold text-white">{m.value}</span>
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

function ActivityIcon({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className={className} aria-hidden="true">
      <polyline points="22 12 18 12 15 21 9 3 6 12 2 12" />
    </svg>
  );
}

