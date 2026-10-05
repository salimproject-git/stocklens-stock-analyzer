import React from "react";
import { StockDetail } from "@/data/mock-stock-details";
import { formatRupiah } from "@/utils/currency";
import { EVIDENCE_RATE_UNAVAILABLE } from "@/lib/analysis";
import { valuationMethodLabel } from "@/lib/valuation-methods";
export function KeyMetricSummary({ stock }: { stock: StockDetail }) {
  // The label follows the row that actually supplies the headline figures, not
  // the stock type's preferred rule: when that rule values the company at or
  // below zero the headline comes from the other rule, and naming the wrong one
  // would misattribute the number.
  const mainMethodName = stock.currentValuation.mainMethodCode
    ? valuationMethodLabel(stock.currentValuation.mainMethodCode)
    : "Not available";

  // A margin of safety can be negative (the price sits above the intrinsic
  // value), so the subtext and its colour follow the sign instead of always
  // claiming a discount.
  const mos = stock.mos;
  const mosTone: "green" | "slate" | "red" = mos == null ? "slate" : mos >= 0 ? "green" : "red";
  const mosSubtext = mos == null ? "Not available" : mos >= 0 ? "Below intrinsic value" : "Above intrinsic value";

  return (
    <section className="mb-6 grid grid-cols-2 gap-4 md:grid-cols-3 xl:grid-cols-5">
      {/* 1. Intrinsic Value */}
      <KeyMetricCard
        label="Intrinsic Value"
        value={formatRupiah(stock.intrinsicValue)}
        subtext="Estimated fair value"
        secondarySubtext={`Method: ${mainMethodName}`}
        subtextTone="slate"
        icon={<DatabaseIcon className="h-4 w-4" />}
        iconTone="blue"
      />

      {/* 2. Margin of Safety */}
      <KeyMetricCard
        label="Margin of Safety"
        value={mos != null ? `${mos.toFixed(1).replace(".", ",")}%` : "Not available"}
        subtext={mosSubtext}
        secondarySubtext={`Method: ${mainMethodName}`}
        subtextTone={mosTone}
        icon={<ShieldCheckIcon className="h-4 w-4" />}
        iconTone={mosTone === "red" ? "gold" : "green"}
      />

      {/* 3. Stock Character */}
      <KeyMetricCard
        label="Stock Character"
        value={stock.stockCharacter}
        subtext={stock.stockCharacterDesc}
        subtextTone="slate"
        icon={<ActivityIcon className="h-4 w-4" />}
        iconTone="blue"
      />

      {/* 4. Undervalued Methods */}
      <KeyMetricCard
        label="Undervalued Methods"
        value={stock.undervaluedMethods}
        subtext="Active methods indicating undervalued"
        subtextTone="slate"
        icon={<LayersIcon className="h-4 w-4" />}
        iconTone="gold"
      />

      {/* 5. Historical Evidence */}
      <KeyMetricCard
        label="Historical Evidence"
        valueSlot={<EvidenceWinRates rates={stock.evidenceWinRates} />}
        subtext="Successful cases"
        secondarySubtext="Similar conditions in the past"
        subtextTone="slate"
        icon={<BarChartIcon className="h-4 w-4" />}
        iconTone="blue"
      />
    </section>
  );
}

/**
 * The two Historical Evidence win rates side by side.
 *
 * Both rules are shown because they disagree by design: the five-method
 * consensus and the `MoS Main >= 30%` rule flag different cases, so a single
 * figure would hide the other. Each figure keeps its own `by ...` label so
 * `100%` next to `47.1%` stays readable.
 */
function EvidenceWinRates({
  rates,
}: {
  rates: StockDetail["evidenceWinRates"];
}) {
  return (
    <div className="grid grid-cols-2 gap-3">
      <EvidenceRate label="by Method" value={rates.method} />
      <EvidenceRate label="by MoS" value={rates.mos} className="border-l border-white/10 pl-3" />
    </div>
  );
}

function EvidenceRate({
  label,
  value,
  className = "",
}: {
  label: string;
  value: string;
  className?: string;
}) {
  // "Not available" is a word, not a figure. At `text-xl` it wraps to two lines
  // in a half-width column and makes this card taller than the other four, so
  // the unavailable state drops a size and stays on one line.
  const isUnavailable = value === EVIDENCE_RATE_UNAVAILABLE;

  return (
    <div className={["min-w-0", className].join(" ")}>
      <div
        className={[
          "mt-1 font-bold tracking-tight",
          isUnavailable ? "text-[11px] text-[#8e9bb0]" : "text-xl text-white",
        ].join(" ")}
      >
        {value}
      </div>
      <div className="text-[10px] font-medium uppercase tracking-[0.08em] text-[#7f8c9f]">
        {label}
      </div>
    </div>
  );
}

function KeyMetricCard({
  label,
  value,
  valueSlot,
  subtext,
  secondarySubtext,
  subtextTone = "slate",
  icon,
  iconTone = "blue",
}: {
  label: string;
  /** Single-line value. Ignored when `valueSlot` is provided. */
  value?: string;
  /**
   * Custom value area for cards that need more than one figure (the two
   * Historical Evidence win rates). Replaces `value` so the other four cards
   * keep the shared `text-xl` treatment.
   */
  valueSlot?: React.ReactNode;
  subtext?: string;
  secondarySubtext?: string;
  subtextTone?: "green" | "slate" | "red";
  icon?: React.ReactNode;
  iconTone?: "green" | "blue" | "gold";
}) {
  const subtextClass =
    subtextTone === "green"
      ? "text-[#3ef0a9]"
      : subtextTone === "red"
        ? "text-[#ff5f73]"
        : "text-[#9aa9bf]";

  const iconBgClass =
    iconTone === "green"
      ? "border-[#1fcf86]/40 bg-[#1fcf86]/10 text-[#3ef0a9]"
      : iconTone === "gold"
        ? "border-[#d6a24d]/40 bg-[#f2bb5c]/10 text-[#f2bb5c]"
        : "border-[#3892d0]/40 bg-[#3892d0]/10 text-[#59b3f4]";

  return (
    <article className="flex flex-col justify-between rounded-2xl border border-white/10 bg-[linear-gradient(180deg,_rgba(11,23,37,0.92),_rgba(7,16,28,0.95))] p-4 shadow-md transition hover:border-white/16">
      <div>
        <div className="flex items-center justify-between gap-2">
          <span className="text-xs font-medium text-[#8e9bb0]">{label}</span>
          {icon && (
            <span
              className={[
                "flex h-7 w-7 items-center justify-center rounded-full border",
                iconBgClass,
              ].join(" ")}
            >
              {icon}
            </span>
          )}
        </div>
        {valueSlot ?? (
          <div className="mt-2.5 text-xl font-bold tracking-tight text-white">
            {value}
          </div>
        )}
      </div>
      {(subtext || secondarySubtext) && (
        <div className="mt-3">
          {subtext && (
            <div className={["text-xs font-medium", subtextClass].join(" ")}>
              {subtext}
            </div>
          )}
          {secondarySubtext && (
            <div className="mt-0.5 text-[11px] text-[#7f8c9f]">
              {secondarySubtext}
            </div>
          )}
        </div>
      )}
    </article>
  );
}

function DatabaseIcon({ className }: { className?: string }) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      className={className}
      aria-hidden="true"
    >
      <ellipse cx="12" cy="5" rx="9" ry="3" />
      <path d="M21 12c0 1.66-4 3-9 3s-9-1.34-9-3" />
      <path d="M3 5v14c0 1.66 4 3 9 3s9-1.34 9-3V5" />
    </svg>
  );
}

function ShieldCheckIcon({ className }: { className?: string }) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      className={className}
      aria-hidden="true"
    >
      <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
      <path d="m9 12 2 2 4-4" />
    </svg>
  );
}

function ActivityIcon({ className }: { className?: string }) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      className={className}
      aria-hidden="true"
    >
      <polyline points="22 12 18 12 15 21 9 3 6 12 2 12" />
    </svg>
  );
}

function BarChartIcon({ className }: { className?: string }) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      className={className}
      aria-hidden="true"
    >
      <line x1="12" y1="20" x2="12" y2="10" />
      <line x1="18" y1="20" x2="18" y2="4" />
      <line x1="6" y1="20" x2="6" y2="16" />
    </svg>
  );
}

function LayersIcon({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className={className} aria-hidden="true">
      <path d="m12 3 9 5-9 5-9-5 9-5Z" />
      <path d="m3 12 9 5 9-5M3 16l9 5 9-5" />
    </svg>
  );
}

