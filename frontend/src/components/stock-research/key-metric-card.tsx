import React from "react";
import { StockDetail } from "@/data/mock-stock-details";
import { formatRupiah } from "@/utils/currency";

function getMainValuationMethod(stockType: string) {
  const normalizedStockType = stockType.trim().toLowerCase();
  return normalizedStockType === "stalwart" || normalizedStockType === "fast grower"
    ? "Type & Sector Weighted"
    : "Peter Lynch / Adaptive";
}
export function KeyMetricSummary({ stock }: { stock: StockDetail }) {
  return (
    <section className="mb-6 grid grid-cols-2 gap-4 md:grid-cols-3 xl:grid-cols-5">
      {/* 1. Current Price */}
      <KeyMetricCard
        label="Current Price"
        value={formatRupiah(stock.price)}
        subtext={`+${stock.changePercent.toFixed(2).replace(".", ",")}% today`}
        subtextTone="green"
        icon={<TrendingUpIcon className="h-4 w-4" />}
        iconTone="green"
      />

      {/* 2. Intrinsic Value */}
      <KeyMetricCard
        label="Intrinsic Value"
        value={formatRupiah(stock.intrinsicValue)}
        subtext="Estimated fair value"
        secondarySubtext={`Method: ${getMainValuationMethod(stock.stockType)}`}
        subtextTone="slate"
        icon={<DatabaseIcon className="h-4 w-4" />}
        iconTone="blue"
      />

      {/* 3. Margin of Safety */}
      <KeyMetricCard
        label="Margin of Safety"
        value={`${stock.mos.toFixed(1).replace(".", ",")}%`}
        subtext="Below intrinsic value"
        secondarySubtext={`Method: ${getMainValuationMethod(stock.stockType)}`}
        subtextTone="green"
        icon={<ShieldCheckIcon className="h-4 w-4" />}
        iconTone="green"
      />

      {/* 4. Stock Character */}
      <KeyMetricCard
        label="Stock Character"
        value={stock.stockCharacter}
        subtext={stock.stockCharacterDesc}
        subtextTone="slate"
        icon={<ActivityIcon className="h-4 w-4" />}
        iconTone="blue"
      />

      {/* 5. Historical Evidence */}
      <KeyMetricCard
        label="Historical Evidence"
        value={`${stock.evidenceWins} / ${stock.evidenceTotal}`}
        subtext="successful cases"
        secondarySubtext="Similar conditions in the past"
        subtextTone="slate"
        icon={<BarChartIcon className="h-4 w-4" />}
        iconTone="blue"
      />
    </section>
  );
}

function KeyMetricCard({
  label,
  value,
  subtext,
  secondarySubtext,
  subtextTone = "slate",
  icon,
  iconTone = "blue",
}: {
  label: string;
  value: string;
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
        <div className="mt-2.5 text-xl font-bold tracking-tight text-white">
          {value}
        </div>
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

function TrendingUpIcon({ className }: { className?: string }) {
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
      <polyline points="23 6 13.5 15.5 8.5 10.5 1 18" />
      <polyline points="17 6 23 6 23 12" />
    </svg>
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

