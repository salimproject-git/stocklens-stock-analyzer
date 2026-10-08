import React from "react";
import { StockDetail } from "@/data/stock-detail-types";
import { formatDecimal, parseSignedNumber } from "@/utils/currency";

type TrendCardData = NonNullable<StockDetail["financialHistory"]>["annualTrendCards"][number];

export function FinancialTrendCard({ card }: { card: TrendCardData }) {
  const values = card.series.map((s) => s.value);
  const max = Math.max(...values) || 1;

  // The footer shows a growth rate (CAGR / YoY). Its sign drives both the colour
  // and the arrow: negative reads red and points down, zero/positive reads green
  // and points up. A value with no number falls back to the neutral tone with no
  // arrow, instead of always claiming an increase.
  const growth = parseSignedNumber(card.cagrValue);
  const hasDirection = Number.isFinite(growth);
  const isNegative = hasDirection && growth < 0;
  const growthToneClass = !hasDirection
    ? "text-[#9aa9bf]"
    : isNegative
      ? "text-[#ff8b82]"
      : "text-[#3ef0a9]";
  const growthBadgeClass = !hasDirection
    ? "bg-white/5 text-[#9aa9bf]"
    : isNegative
      ? "bg-[#ff7168]/10 text-[#ff8b82]"
      : "bg-[#1fcf86]/10 text-[#3ef0a9]";

  return (
    <article className="flex flex-col justify-between rounded-[20px] border border-white/10 bg-[linear-gradient(180deg,_rgba(11,23,37,0.95),_rgba(7,16,28,0.97))] p-5 shadow-[0_24px_48px_rgba(0,0,0,0.28)]">
      <div>
        {/* Header */}
        <div className="flex items-start justify-between gap-2">
          <div>
            <div className="flex items-center gap-1.5 text-base font-semibold text-white">
              <span>{card.title}</span>
              <InfoIcon className="h-3.5 w-3.5 text-[#8e9bb0]" />
            </div>
            <div className="mt-0.5 text-xs text-[#7f8c9f]">{card.unit}</div>
          </div>
        </div>

        {/* SVG Mini Bar Chart */}
        <div className="mt-4 flex h-36 items-end justify-between gap-2 rounded-xl border border-white/6 bg-[#07111c]/60 p-3 pb-2">
          {card.series.map((item, idx) => {
            const heightPct = Math.max(12, Math.round((item.value / max) * 100));
            const isLatest = idx === card.series.length - 1;

            return (
              <div key={item.year} className="flex h-full flex-1 flex-col items-center gap-1">
                {/* The value row is reserved for every column so the bar tracks
                    stay the same height; otherwise the labelled (latest) bar
                    would be drawn on a shorter track and look like a decline. */}
                <span className="flex h-4 items-center text-[10px] font-bold text-[#f4d18b]">
                  {isLatest ? formatDecimal(item.value) : ""}
                </span>
                <div className="flex w-full min-h-0 max-w-[28px] flex-1 items-end rounded-t bg-white/5">
                  <div
                    className={[
                      "w-full rounded-t transition-all",
                      isLatest
                        ? "bg-[linear-gradient(180deg,_#3892d0,_#1d6092)]"
                        : "bg-[linear-gradient(180deg,_rgba(56,146,208,0.6),_rgba(29,96,146,0.3))]",
                    ].join(" ")}
                    style={{ height: `${heightPct}%` }}
                  />
                </div>
                <span className="text-[10px] text-[#7f8c9f]">{item.year}</span>
              </div>
            );
          })}
        </div>
      </div>

      {/* Footer CAGR Block */}
      <div className="mt-4 pt-3 border-t border-white/8">
        <div className="text-[11px] font-medium text-[#8e9bb0]">{card.cagrLabel}</div>
        <div className="mt-1 flex items-center gap-2">
          <span className={`text-lg font-bold ${growthToneClass}`}>
            {card.cagrValue}
          </span>
          {hasDirection && (
            <span className={`flex h-5 w-5 items-center justify-center rounded-full ${growthBadgeClass}`}>
              {isNegative ? <TrendingDownIcon className="h-3 w-3" /> : <TrendingUpIcon className="h-3 w-3" />}
            </span>
          )}
        </div>
        <div className="mt-0.5 text-xs text-[#9aa9bf]">{card.subtext}</div>
      </div>
    </article>
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

function TrendingUpIcon({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className={className} aria-hidden="true">
      <polyline points="23 6 13.5 15.5 8.5 10.5 1 18" />
      <polyline points="17 6 23 6 23 12" />
    </svg>
  );
}

function TrendingDownIcon({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className={className} aria-hidden="true">
      <polyline points="23 18 13.5 8.5 8.5 13.5 1 6" />
      <polyline points="17 18 23 18 23 12" />
    </svg>
  );
}

