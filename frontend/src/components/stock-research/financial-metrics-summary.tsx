import React from "react";
import { StockDetail } from "@/data/mock-stock-details";

type KeyMetric = NonNullable<StockDetail["financialHistory"]>["keyMetrics"][number];

export function FinancialMetricsSummary({ metrics }: { metrics: KeyMetric[] }) {
  return (
    <section className="mb-6 grid grid-cols-2 gap-4 md:grid-cols-3 xl:grid-cols-6">
      {metrics.map((m) => (
        <div
          key={m.label}
          className="flex flex-col justify-between rounded-2xl border border-white/10 bg-[linear-gradient(180deg,_rgba(11,23,37,0.92),_rgba(7,16,28,0.95))] p-4 shadow-md transition hover:border-white/16"
        >
          <div>
            <div className="flex items-center justify-between gap-1 text-[11px] font-medium text-[#8e9bb0]">
              <span className="truncate">{m.label}</span>
              <InfoIcon className="h-3 w-3 shrink-0 text-[#7f8c9f]" />
            </div>
            <div className="mt-2 text-xl font-bold tracking-tight text-white">
              {m.value}
            </div>
          </div>
          <div className="mt-2 text-xs font-medium text-[#3ef0a9] truncate">
            {m.subtext}
          </div>
        </div>
      ))}
    </section>
  );
}

function InfoIcon({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className={className} aria-hidden="true">
      <circle cx="12" cy="12" r="10" />
      <line x1="12" y1="16" x2="12" y2="12" />
      <line x1="12" y1="8" x2="12.01" y2="8" />
    </svg>
  );
}

