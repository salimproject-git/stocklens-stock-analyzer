import React from "react";
import { StockDetail, type EvidenceOutcomeBreakdown } from "@/data/mock-stock-details";
import { SectionCard } from "@/components/ui/section-card";
import { UnavailableBadge } from "@/components/ui/unavailable-badge";
import { DemoDataBadge } from "@/components/ui/demo-data-badge";

export function HistoricalEvidencePreviewCard({
  evidence,
}: {
  evidence?: StockDetail["historicalEvidencePreview"];
}) {
  if (!evidence) {
    return (
      <SectionCard
        icon={<HistoryIcon className="h-4 w-4" />}
        title="Historical Evidence"
        subtitle="Similar valuation conditions · historical outcomes"
        actionSlot={
          <span className="text-xs font-semibold text-[#f4d18b]">
            View Backtest →
          </span>
        }
        paddingClassName="p-5"
      >
        <div className="flex flex-col items-start gap-2.5">
          <UnavailableBadge label="Not available" />
          <p className="text-xs leading-relaxed text-[#8e9bb0]">
            Backtest and historical evidence are not stored in the database for
            this ticker yet. The figures will appear once the backtest process
            has run and its results are loaded into the database.
          </p>
        </div>
      </SectionCard>
    );
  }

  return (
    <SectionCard
      icon={<HistoryIcon className="h-4 w-4" />}
      title="Historical Evidence"
      subtitle={`Similar valuation conditions · historical outcomes · ${evidence.totalCases} Cases`}
      actionSlot={
        <span className="text-xs font-semibold text-[#f4d18b]">
          View Backtest →
        </span>
      }
      paddingClassName="p-5"
    >
      <div className="grid gap-3 sm:grid-cols-2">
        {evidence.isDemoData && (
          <div className="sm:col-span-2">
            <DemoDataBadge />
          </div>
        )}
        {/* Verdict Based Method */}
        <VerdictOutcomePanel
          title="Verdict Based Method"
          breakdown={evidence.verdictMethod}
        />

        {/* Verdict Based MoS */}
        <VerdictOutcomePanel
          title="Verdict Based MoS"
          breakdown={evidence.verdictMos}
        />
      </div>
    </SectionCard>
  );
}

function VerdictOutcomePanel({
  title,
  breakdown,
}: {
  title: string;
  breakdown: EvidenceOutcomeBreakdown;
}) {
  return (
    <div className="rounded-xl border border-white/8 bg-[#07111c]/60 p-3.5">
      <div className="text-[12px] font-semibold text-[#d4dcec]">{title}</div>

      <div className="mt-3 space-y-2 text-xs">
        <div className="flex items-center justify-between gap-3">
          <span className="text-[#8e9bb0]">Undervalued</span>
          <span className="font-semibold text-white">
            {breakdown.undervalued}
          </span>
        </div>

        <div className="flex items-center justify-between gap-3">
          <span className="text-[#8e9bb0]">Overvalued</span>
          <span className="font-semibold text-white">
            {breakdown.overvalued}
          </span>
        </div>
      </div>

      {/* The three rates cover every Undervalued case, so they add up to 100%.
          Each is labelled `<name> %` so the label and the figure need only one
          line, leaving the row below for what the rate actually counts. */}
      <div className="mt-3 grid grid-cols-3 gap-3 border-t border-white/8 pt-2.5">
        <RateBlock
          label="Win %"
          value={breakdown.winRate}
          note="WIN + RECOVERED"
          valueClassName="text-[#3ef0a9]"
        />

        <RateBlock
          label="Risk %"
          value={breakdown.riskRate}
          note="RISK"
          valueClassName="text-[#ff827d]"
          className="border-l border-white/10 pl-3"
        />

        <RateBlock
          label="Flat %"
          value={`${breakdown.flatRate}${breakdown.flatSuffix}`}
          note="FLAT"
          valueClassName="text-[#8290a4]"
          className="border-l border-white/10 pl-3"
        />
      </div>
    </div>
  );
}

function RateBlock({
  label,
  value,
  note,
  valueClassName,
  className = "",
}: {
  label: string;
  value: string;
  note: string;
  valueClassName: string;
  className?: string;
}) {
  return (
    <div className={["min-w-0", className].join(" ")}>
      <div className="text-[10px] font-medium uppercase tracking-[0.08em] text-[#7f8c9f]">
        {label}
      </div>

      <div
        className={[
          "mt-1 text-[18px] font-semibold leading-none",
          valueClassName,
        ].join(" ")}
      >
        {value}
      </div>

      {/* Smaller than the label and kept off the wrap path: "WIN + RECOVERED"
          is the longest of the three and still fits one line in the narrowest
          column, so a rate never pushes its panel to a second row. */}
      <div className="mt-1 whitespace-nowrap text-[9px] leading-tight text-[#7f8c9f]">
        {note}
      </div>
    </div>
  );
}

function HistoryIcon({ className }: { className?: string }) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      className={className}
      aria-hidden="true"
    >
      <path d="M3 12a9 9 0 1 0 3-6.7" />
      <polyline points="3 4 3 9 8 9" />
      <polyline points="12 7 12 12 15 14" />
    </svg>
  );
}
