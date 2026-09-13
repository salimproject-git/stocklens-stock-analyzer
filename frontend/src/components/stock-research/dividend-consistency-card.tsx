import React from "react";
import { StockDetail } from "@/data/mock-stock-details";
import { SectionCard } from "@/components/ui/section-card";

export function DividendConsistencyCard({
  dividend,
}: {
  dividend: StockDetail["dividendConsistency"];
}) {
  return (
    <SectionCard
      icon={<CoinsIcon className="h-4 w-4" />}
      title="Dividend Consistency"
      subtitle="Annual Performance"
      actionSlot={
        <div className="text-xs font-semibold text-[#f4d18b]">
          <span className="text-[#8e9bb0]">Avg. 4Y </span>
          <span>{dividend.averageYield}</span>
          <span className="text-[#8e9bb0]"> Dividend Yield</span>
        </div>
      }
    >
      <div className="overflow-x-auto gold-scroll rounded-xl border border-white/8 bg-[#07111c]/60">
        <table className="w-full min-w-[520px] text-left text-xs">
          <thead className="border-b border-white/8 bg-white/4 text-[11px] font-semibold text-[#8e9bb0]">
            <tr>
              <th className="px-3.5 py-2.5">ITEM</th>
              {dividend.years.map((y) => (
                <th
                  key={y}
                  className={[
                    "px-3 py-2.5 text-center",
                    y.includes("Proyeksi") ? "text-[#f4d18b]" : "",
                  ].join(" ")}
                >
                  {y}
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-white/6 text-white">
            {dividend.rows.map((row) => (
              <tr key={row.item} className="hover:bg-white/3">
                <td className="px-3.5 py-2.5 font-medium text-[#d4dcec]">
                  {row.item}
                </td>
                <td className="px-3 py-2.5 text-center font-semibold text-[#3ef0a9]">
                  {row.p2026}
                </td>
                <td className="px-3 py-2.5 text-center text-[#9aa9bf]">{row.y2025}</td>
                <td className="px-3 py-2.5 text-center text-[#9aa9bf]">{row.y2024}</td>
                <td className="px-3 py-2.5 text-center text-[#9aa9bf]">{row.y2023}</td>
                <td className="px-3 py-2.5 text-center text-[#9aa9bf]">{row.y2022}</td>
                <td className="px-3 py-2.5 text-center font-semibold text-[#f4d18b]">
                  {row.avg4Y}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Callout Box */}
      <div className="mt-3.5 flex items-start gap-2.5 rounded-xl border border-[#d6a24d]/40 bg-[#2b2212]/80 p-3 text-[11px] leading-relaxed text-[#f4d18b]">
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
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className={className} aria-hidden="true">
      <circle cx="8" cy="8" r="6" />
      <path d="M18 8a6 6 0 0 1-6 6" />
      <path d="M18 14a6 6 0 0 1-6 6" />
    </svg>
  );
}

