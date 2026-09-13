import React from "react";
import { StockDetail } from "@/data/mock-stock-details";
import { StatusBadge } from "@/components/ui/status-badge";

export function StockHeader({ stock }: { stock: StockDetail }) {
  const isPositive = stock.change >= 0;
  const changeTone = isPositive ? "text-[#49f3ae]" : "text-[#ff5967]";

  return (
    <section className="mb-6 flex flex-wrap items-start justify-between gap-6 rounded-[20px] border border-white/10 bg-[linear-gradient(180deg,_rgba(11,23,37,0.95),_rgba(7,16,28,0.97))] p-6 shadow-[0_24px_48px_rgba(0,0,0,0.28)]">
      {/* Left Identity Block */}
      <div className="flex items-center gap-5">
        {/* Logo Card */}
        <div className="flex h-16 w-20 shrink-0 items-center justify-center rounded-xl bg-white p-2 shadow-md">
          {stock.logoUrl ? (
            <img
              src={stock.logoUrl}
              alt={stock.companyName}
              className="max-h-full max-w-full object-contain"
            />
          ) : (
            <div className="flex flex-col items-center justify-center leading-none text-[#1b2b40]">
              <span className="text-xs font-black tracking-tighter text-[#cc0000]">
                ASTRA
              </span>
              <span className="text-[9px] font-semibold text-[#003399]">
                Otoparts
              </span>
            </div>
          )}
        </div>

        <div>
          <div className="flex items-center gap-3">
            <h1 className="text-3xl font-bold tracking-tight text-white">
              {stock.ticker}
            </h1>
            <button
              type="button"
              className="text-[#8999af] transition hover:text-white"
              aria-label="Add to watchlist"
            >
              <StarIcon className="h-5 w-5" />
            </button>
          </div>
          <p className="mt-1 text-sm text-[#b6c2d4]">{stock.companyName}</p>
          <div className="mt-2.5 flex flex-wrap gap-2">
            <span className="rounded-full bg-[#123551] px-3 py-1 text-xs font-medium text-[#92cdf4]">
              {stock.sector}
            </span>
            <span className="rounded-full bg-white/8 px-3 py-1 text-xs font-medium text-[#ced8e6]">
              {stock.stockType}
            </span>
          </div>
        </div>
      </div>

      {/* Right Price & Valuation Block */}
      <div className="flex flex-wrap items-center gap-6">
        {/* Price & Change */}
        <div className="text-right">
          <div className="text-3xl font-bold tracking-tight text-white">
            {formatRupiah(stock.price)}
          </div>
          <div className={["mt-1 text-sm font-semibold", changeTone].join(" ")}>
            {formatSignedRupiah(stock.change)} ({formatPercent(stock.changePercent)})
          </div>
          <div className="mt-1 text-xs text-[#8f9db1]">
            As of {stock.updatedAt}
          </div>
        </div>

        {/* Valuation Status Badge Box */}
        <div className="flex items-center gap-3 rounded-xl border border-[#1fcf86]/35 bg-[#0d2b22]/90 p-4 shadow-[inset_0_1px_0_rgba(255,255,255,0.06)]">
          <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg border border-[#1fcf86]/40 bg-[#1fcf86]/10 text-[#3ef0a9]">
            <ShieldCheckIcon className="h-5 w-5" />
          </div>
          <div>
            <div className="text-sm font-bold tracking-wider text-[#3ef0a9]">
              {stock.verdict.toUpperCase()}
            </div>
            <div className="mt-0.5 flex items-center gap-1.5 text-xs text-[#a3f3d3]">
              <span>{stock.verdictDescription}</span>
              <InfoIcon className="h-3.5 w-3.5 text-[#3ef0a9]" />
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}

function formatRupiah(val: number) {
  return `Rp ${new Intl.NumberFormat("id-ID").format(val)}`;
}

function formatSignedRupiah(val: number) {
  const sign = val > 0 ? "+" : "";
  return `${sign}${new Intl.NumberFormat("id-ID").format(val)}`;
}

function formatPercent(val: number) {
  const sign = val > 0 ? "+" : "";
  return `${sign}${new Intl.NumberFormat("id-ID", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(val)}%`;
}

function StarIcon({ className }: { className?: string }) {
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
      <path d="m12 3 2.7 5.6 6.2.9-4.5 4.4 1.1 6.1L12 17.1 6.5 20l1.1-6.1L3 9.5l6.2-.9L12 3Z" />
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

function InfoIcon({ className }: { className?: string }) {
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
      <circle cx="12" cy="12" r="10" />
      <path d="M12 16v-4" />
      <path d="M12 8h.01" />
    </svg>
  );
}

