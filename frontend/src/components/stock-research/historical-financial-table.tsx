import React from "react";
import { StockDetail } from "@/data/mock-stock-details";
import { SectionCard } from "@/components/ui/section-card";

type FinancialTableData = NonNullable<StockDetail["financialHistory"]>["annualTable"];

export function HistoricalFinancialTable({ table }: { table: FinancialTableData }) {
  const latestPeriodIndex = table.periods.length - 1;

  return (
    <SectionCard
      icon={<TableIcon className="h-4 w-4" />}
      title="Financial History"
    >
      <div className="overflow-x-auto gold-scroll rounded-xl border border-white/8 bg-[#07111c]/60">
        <table className="w-full min-w-[700px] text-left text-xs">
          <thead className="border-b border-white/8 bg-white/4 text-[11px] font-semibold text-[#8e9bb0]">
            <tr>
              <th className="px-4 py-3 min-w-[200px]">METRIC</th>
              {table.periods.map((period) => (
                <th key={period} className="px-3 py-3 text-center">
                  {period}
                </th>
              ))}
              <th className="px-4 py-3 text-right">{table.changeLabel}</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-white/6 text-white">
            {table.rows.map((row) => (
              <tr
                key={row.metric}
                className="hover:bg-white/3 transition"
              >
                <td className="px-4 py-3 font-medium text-[#d4dcec]">
                  {row.metric}
                </td>
                {table.periods.map((period, index) => (
                  <td
                    key={period}
                    className={
                      index === latestPeriodIndex
                        ? "px-3 py-3 text-center font-semibold text-white"
                        : "px-3 py-3 text-center text-[#9aa9bf]"
                    }
                  >
                    {row.values[index] ?? "-"}
                  </td>
                ))}
                <td className="px-4 py-3 text-right font-semibold text-[#3ef0a9]">
                  {row.change}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </SectionCard>
  );
}

function TableIcon({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className={className} aria-hidden="true">
      <rect x="3" y="3" width="18" height="18" rx="2" />
      <path d="M3 9h18" />
      <path d="M3 15h18" />
      <path d="M9 3v18" />
    </svg>
  );
}
