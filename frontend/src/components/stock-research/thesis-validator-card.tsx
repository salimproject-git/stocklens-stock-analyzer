import React from "react";
import { StockDetail } from "@/data/mock-stock-details";
import { SectionCard } from "@/components/ui/section-card";

export function ThesisValidatorCard({
  validator,
}: {
  validator: StockDetail["thesisValidator"];
}) {
  return (
    <SectionCard
      icon={<SparklesIcon className="h-4 w-4" />}
      title="Thesis Validator"
      subtitle="Quarterly YoY Performance"
    >
      <div className="overflow-x-auto gold-scroll rounded-xl border border-white/8 bg-[#07111c]/60">
        <table className="w-full min-w-[520px] text-left text-xs">
          <thead className="border-b border-white/8 bg-white/4 text-[11px] font-semibold text-[#8e9bb0]">
            <tr>
              <th className="px-3.5 py-2.5">ITEM</th>
              {validator.quarters.map((q) => (
                <th key={q} className="px-3 py-2.5 text-center">
                  {q}
                </th>
              ))}
              <th className="px-3.5 py-2.5 text-right">TREND / RESULT</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-white/6 text-white">
            {validator.rows.map((row) => {
              const trendClass =
                row.trendTone === "green"
                  ? "text-[#3ef0a9]"
                  : row.trendTone === "yellow"
                    ? "text-[#f59e0b]"
                    : "text-[#b6c2d4]";

              return (
                <tr key={row.item} className="hover:bg-white/3">
                  <td className="px-3.5 py-2.5 font-medium text-[#d4dcec]">
                    {row.item}
                  </td>
                  <td className="px-3 py-2.5 text-center text-[#9aa9bf]">{row.q3}</td>
                  <td className="px-3 py-2.5 text-center text-[#9aa9bf]">{row.q4}</td>
                  <td className="px-3 py-2.5 text-center text-[#9aa9bf]">{row.q1}</td>
                  <td className="px-3 py-2.5 text-center font-semibold text-white">
                    {row.q2}
                  </td>
                  <td className={["px-3.5 py-2.5 text-right font-semibold", trendClass].join(" ")}>
                    {row.trend}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {/* Footnote */}
      <div className="mt-3.5 flex items-start gap-2.5 rounded-xl border border-white/8 bg-[#091424]/90 p-3 text-[11px] leading-relaxed text-[#9aa9bf]">
        <span>💡</span>
        <span>{validator.footnote}</span>
      </div>
    </SectionCard>
  );
}

function SparklesIcon({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className={className} aria-hidden="true">
      <path d="m12 3-1.9 5.8a2 2 0 0 1-1.3 1.3L3 12l5.8 1.9a2 2 0 0 1 1.3 1.3L12 21l1.9-5.8a2 2 0 0 1 1.3-1.3L21 12l-5.8-1.9a2 2 0 0 1-1.3-1.3L12 3Z" />
    </svg>
  );
}

