import React from "react";
import type { SampleComparison } from "@/lib/sample-comparison";
import { SectionCard } from "@/components/ui/section-card";

const statusTone: Record<string, string> = {
  MATCH: "border-[#1fcf86]/45 bg-[#0d2b22] text-[#3ef0a9]",
  MISMATCH: "border-[#d66f65]/50 bg-[#2b1614] text-[#ff8b82]",
  DB_MISSING: "border-[#8f9db1]/35 bg-[#1a2332]/70 text-[#9aa9bf]",
  NOT_EXPOSED: "border-[#d6a24d]/45 bg-[#2b2212]/70 text-[#f4d18b]",
};

const statusLabel: Record<string, string> = {
  MATCH: "COCOK",
  MISMATCH: "BEDA",
  DB_MISSING: "TABEL KOSONG",
  NOT_EXPOSED: "ADA, TIDAK DIEKSPOS",
};

/**
 * Side-by-side of the documented workbook sample and the database values.
 *
 * This card exists so a reader can verify the migration honestly: it shows the
 * workbook number and the table number next to each other, and states plainly
 * when the table has nothing to compare.
 */
export function SampleComparisonCard({ comparison }: { comparison?: SampleComparison }) {
  if (!comparison) return null;

  if (!comparison.available) {
    return (
      <SectionCard
        icon={<CompareIcon className="h-4 w-4" />}
        title="Workbook Sample vs Tabel"
        subtitle="Perbandingan data sampel dengan isi database"
      >
        <p className="text-xs leading-relaxed text-[#8e9bb0]">{comparison.note}</p>
      </SectionCard>
    );
  }

  const groups = [...new Set(comparison.rows.map((row) => row.group))];

  return (
    <SectionCard
      icon={<CompareIcon className="h-4 w-4" />}
      title="Workbook Sample vs Tabel"
      subtitle="Angka sampel workbook yang terdokumentasi dibandingkan dengan nilai database"
      actionSlot={
        <span className="flex flex-wrap items-center gap-2 text-[11px] font-semibold">
          <span className="rounded-md border border-[#1fcf86]/45 bg-[#0d2b22] px-2 py-1 text-[#3ef0a9]">
            {comparison.matchCount} cocok
          </span>
          {comparison.mismatchCount > 0 && (
            <span className="rounded-md border border-[#d66f65]/50 bg-[#2b1614] px-2 py-1 text-[#ff8b82]">
              {comparison.mismatchCount} beda
            </span>
          )}
          {comparison.missingCount > 0 && (
            <span className="rounded-md border border-[#8f9db1]/35 bg-[#1a2332]/70 px-2 py-1 text-[#9aa9bf]">
              {comparison.missingCount} kosong
            </span>
          )}
          {comparison.notExposedCount > 0 && (
            <span className="rounded-md border border-[#d6a24d]/45 bg-[#2b2212]/70 px-2 py-1 text-[#f4d18b]">
              {comparison.notExposedCount} tidak diekspos
            </span>
          )}
        </span>
      }
    >
      <p className="mb-4 text-[11px] leading-relaxed text-[#8e9bb0]">{comparison.note}</p>

      <div className="space-y-5">
        {groups.map((group) => (
          <div key={group}>
            <h4 className="mb-2 text-[11px] font-semibold uppercase tracking-[0.08em] text-[#8fa0b8]">
              {group}
            </h4>
            <div className="overflow-x-auto rounded-xl border border-white/[0.09]">
              <table className="w-full min-w-[680px] text-left text-xs">
                <thead className="bg-[#081523] text-[10px] uppercase tracking-[0.1em] text-[#7f8fa6]">
                  <tr>
                    <th className="px-3 py-2.5">Metrik</th>
                    <th className="px-3 py-2.5">Periode</th>
                    <th className="px-3 py-2.5 text-right">Sampel (workbook)</th>
                    <th className="px-3 py-2.5 text-right">Tabel (database)</th>
                    <th className="px-3 py-2.5">Status</th>
                    <th className="px-3 py-2.5">Sumber sampel</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-white/[0.06]">
                  {comparison.rows
                    .filter((row) => row.group === group)
                    .map((row) => (
                      <tr key={`${row.group}-${row.metric}-${row.period}`} className="text-white">
                        <td className="px-3 py-2.5 font-medium text-[#d4dcec]">{row.metric}</td>
                        <td className="whitespace-nowrap px-3 py-2.5 text-[#9aa9bf]">{row.period}</td>
                        <td className="whitespace-nowrap px-3 py-2.5 text-right font-semibold text-[#f2d18f]">
                          {row.sampleDisplay}
                        </td>
                        <td className="whitespace-nowrap px-3 py-2.5 text-right font-semibold text-white">
                          {row.dbDisplay}
                        </td>
                        <td className="whitespace-nowrap px-3 py-2.5">
                          <span
                            className={[
                              "inline-flex items-center rounded-md border px-2 py-0.5 text-[10px] font-semibold",
                              statusTone[row.status],
                            ].join(" ")}
                          >
                            {statusLabel[row.status]}
                          </span>
                        </td>
                        <td className="px-3 py-2.5 text-[10px] text-[#7f8fa6]">{row.source}</td>
                      </tr>
                    ))}
                </tbody>
              </table>
            </div>
          </div>
        ))}
      </div>
    </SectionCard>
  );
}

function CompareIcon({ className }: { className?: string }) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
      className={className}
      aria-hidden="true"
    >
      <path d="M12 4v16M7 8H4l3-4 3 4H7v8M17 8h3l-3-4-3 4h3v8" />
    </svg>
  );
}
