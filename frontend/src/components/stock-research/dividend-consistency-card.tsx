import React from "react";
import { StockDetail } from "@/data/mock-stock-details";
import { SectionCard } from "@/components/ui/section-card";
import { formatRupiahValue } from "@/utils/currency";

export function DividendConsistencyCard({
  dividend,
}: {
  dividend: StockDetail["dividendConsistency"];
}) {
  const dpsRow = dividend.rows.find((row) => row.item === "DPS [Rp]");

  const dprRow = dividend.rows.find((row) => row.item === "DPR [%]");

  const yieldRow = dividend.rows.find((row) => row.item === "Yield [%]");

  return (
    <SectionCard
      icon={<CoinsIcon className="h-4 w-4" />}
      title="Dividend Consistency"
      subtitle="Latest Projection · 2026"
      actionSlot={
        <span className="text-xs font-semibold text-[#f4d18b]">
          Valuation
        </span>
      }
    >
      <div className="grid grid-cols-3 gap-2.5">
        <div className="rounded-xl border border-white/6 bg-[#07111c]/60 p-3">
          <div className="text-[11px] text-[#8e9bb0]">Dividend Yield</div>

          <div className="mt-1 font-semibold text-[#3ef0a9]">
            {yieldRow?.p2026 ?? "—"}
          </div>
        </div>

        <div className="rounded-xl border border-white/6 bg-[#07111c]/60 p-3">
          <div className="text-[11px] text-[#8e9bb0]">DPR</div>

          <div className="mt-1 font-semibold text-white">
            {dprRow?.p2026 ?? "—"}
          </div>
        </div>

        <div className="rounded-xl border border-white/6 bg-[#07111c]/60 p-3">
          <div className="text-[11px] text-[#8e9bb0]">DPS</div>

          <div className="mt-1 font-semibold text-white">
            {dpsRow?.p2026 ? formatRupiahValue(dpsRow.p2026) : "—"}
          </div>
        </div>
      </div>

      <div className="mt-3 flex items-start gap-2.5 rounded-xl border border-[#d6a24d]/40 bg-[#2b2212]/80 p-3 text-[11px] leading-relaxed text-[#f4d18b]">
        <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full border border-[#d6a24d]/50 bg-[#f2bb5c]/20 text-xs">
          💰
        </span>

        <span>{dividend.callout}</span>
      </div>
    </SectionCard>
  );
}

function CoinsIcon({ className }: { className?: string }) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      className={className}
      aria-hidden="true"
    >
      <circle cx="8" cy="8" r="6" />
      <path d="M18 8a6 6 0 0 1-6 6" />
      <path d="M18 14a6 6 0 0 1-6 6" />
    </svg>
  );
}
