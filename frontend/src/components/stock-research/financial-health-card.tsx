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
      <div className="grid grid-cols-1 gap-2.5 sm:grid-cols-2">
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
              className="flex min-w-0 items-center justify-between gap-3 rounded-xl border border-white/6 bg-[#07111c]/60 p-3 text-xs"
            >
              <span className="min-w-0 font-medium text-[#8e9bb0]">
                {m.label}
              </span>

              <div className="flex shrink-0 items-center gap-2">
                <span className="font-semibold text-white">{m.value}</span>
                <StatusBadge tone={tone}>{m.badge}</StatusBadge>
              </div>
            </div>
          );
        })}
      </div>
    </SectionCard>
  );
}

function ActivityIcon({ className }: { className?: string }) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      className={className}
      aria-hidden="true"
    >
      <polyline points="22 12 18 12 15 21 9 3 6 12 2 12" />
    </svg>
  );
}