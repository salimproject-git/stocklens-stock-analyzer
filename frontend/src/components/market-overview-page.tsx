"use client";

import { useRouter } from "next/navigation";
import { useState, useTransition } from "react";
import type { MarketOverviewStock } from "@/lib/stock-types";
import type { MarketOverviewData } from "@/lib/stock-data";
import {
  DEFAULT_MARKET_PAGE_SIZE,
  MARKET_PAGE_SIZE_OPTIONS,
  parseMarketPageSize,
  type MarketPageSize,
} from "@/lib/market-page-size";
import {
  MARKET_SORT_OPTIONS,
  MARKET_STOCK_TYPE_OPTIONS,
  type MarketFilterSelection,
  type MarketSort,
  type MarketStockType,
} from "@/lib/market-filters";
import { DisclaimerFooter } from "./stock-research/disclaimer-footer";
import { formatRupiah as formatCurrencyRupiah } from "@/utils/currency";

type ViewMode = "grid" | "list";

const SIDEBAR_WIDTH = 240;

type MarketOverviewPageProps = {
  initialData: MarketOverviewData;
  currentPage: number;
  sectors: string[];
  filters: MarketFilterSelection;
};

export function MarketOverviewPage({
  initialData,
  currentPage,
  sectors,
  filters,
}: MarketOverviewPageProps) {
  const router = useRouter();
  const [viewMode, setViewMode] = useState<ViewMode>("grid");
  // Seeded from the server so the picker reflects `?size=` on first paint, and
  // then owned by the client to keep the selection responsive while the next
  // page streams in.
  const [pageSize, setPageSize] = useState<MarketPageSize>(() =>
    parseMarketPageSize(initialData.pageSize),
  );
  // Screener state is owned by the URL, not by this component: the server does
  // the filtering, so every facet change is a navigation. The values are read
  // back from the props on the next render, which keeps the controls honest even
  // if the RPC rejects a value.
  const [isPending, startTransition] = useTransition();

  // Derived from the *returned* page size rather than a hardcoded constant, so
  // the page count cannot drift when the size changes.
  const effectivePageSize =
    initialData.pageSize > 0 ? initialData.pageSize : DEFAULT_MARKET_PAGE_SIZE;
  const totalPages = Math.max(1, Math.ceil(initialData.totalCount / effectivePageSize));
  const visibleStocks = initialData.stocks;
  const showingCount = visibleStocks.length;

  const handlePageChange = (page: number) => {
    router.push(buildMarketHref(page, pageSize, filters));
  };

  const handlePageSizeChange = (nextSize: MarketPageSize) => {
    setPageSize(nextSize);
    // Reset to page 1: page 3 of 5-per-page may not exist at 20-per-page, and
    // the server clamps out-of-range pages, so staying put would silently
    // renumber the view.
    router.push(buildMarketHref(1, nextSize, filters));
  };

  /**
   * Every facet change resets to page 1. Narrowing the screener shrinks the
   * result set, so the current page number may no longer exist; the server
   * clamps it too, but resetting here keeps the URL honest about what is shown.
   */
  const applyFilters = (patch: Partial<MarketFilterSelection>) => {
    const next = { ...filters, ...patch };
    startTransition(() => {
      router.push(buildMarketHref(1, pageSize, next));
    });
  };

  return (
    <>
      <PageIntro />
      <Toolbar
        showingCount={showingCount}
        totalCount={initialData.totalCount}
        viewMode={viewMode}
        onViewModeChange={setViewMode}
        pageSize={pageSize}
        onPageSizeChange={handlePageSizeChange}
        sectors={sectors}
        filters={filters}
        onFilterChange={applyFilters}
        isPending={isPending}
      />
      <StockCollection
        stocks={visibleStocks}
        viewMode={viewMode}
        showDiscoveryCard={currentPage >= totalPages}
      />
      <Pagination
        currentPage={currentPage}
        totalPages={totalPages}
        onPageChange={handlePageChange}
      />
      {/* This page surfaces derived signals (Signal, MoS, historical win rate),
          so the same "analysis, not advice" notice the research page carries
          belongs here too. */}
      <DisclaimerFooter />
    </>
  );
}

/**
 * Keeps every facet together so changing one never drops the others. Empty
 * facets are omitted rather than sent as `sector=`, so the URL stays readable
 * and the default view has no query noise.
 */
function buildMarketHref(
  page: number,
  size: MarketPageSize,
  filters: MarketFilterSelection,
) {
  const params = new URLSearchParams({ page: String(page), size: String(size) });
  if (filters.sector) params.set("sector", filters.sector);
  if (filters.stockType) params.set("type", filters.stockType);
  if (filters.sort !== "ticker") params.set("sort", filters.sort);
  return `/market?${params.toString()}`;
}

function Sidebar() {
  return (
    <aside
      className="fixed inset-y-0 left-0 z-20 flex flex-col border-r border-white/10 bg-[linear-gradient(180deg,_rgba(6,17,29,0.99),_rgba(4,12,22,0.98))] px-4 pb-5 pt-4"
      style={{
        width: SIDEBAR_WIDTH,
      }}
    >
      <div className="mb-5 px-2">
        <StockLensLogo />
      </div>
      <nav className="space-y-2.5">
        <NavItem label="Market Overview" active icon={<BarChartIcon className="h-4 w-4" />} />
        <NavItem label="Profile" icon={<UserIcon className="h-4 w-4" />} />
      </nav>

      <div className="mt-auto rounded-2xl border border-[#d6a24d]/65 bg-[linear-gradient(180deg,_rgba(255,197,92,0.05),_rgba(7,17,29,0.82))] p-4 shadow-[0_20px_60px_rgba(0,0,0,0.35)]">
        <div className="mb-4 flex items-start gap-3">
          <span className="mt-0.5 flex h-9 w-9 items-center justify-center rounded-full border border-[#d6a24d]/50 bg-[#f2bb5c]/10 text-[#f2bb5c]">
            <CapIcon className="h-4 w-4" />
          </span>
          <div>
            <p className="text-[15px] font-semibold text-white">Learn our data</p>
            <p className="mt-1 text-xs leading-5 text-[#9aa9bf]">
              Understand the data behind our stock analysis.
            </p>
          </div>
        </div>
        <button
          type="button"
          className="w-full rounded-xl border border-[#d6a24d]/80 px-3 py-2 text-sm font-semibold text-[#f2bb5c] transition hover:bg-[#f2bb5c]/8"
        >
          Visit Learning Center
        </button>
      </div>
    </aside>
  );
}

function NavItem({
  active = false,
  icon,
  label,
}: {
  active?: boolean;
  icon: React.ReactNode;
  label: string;
}) {
  return (
    <button
      type="button"
      className={[
        "flex min-h-[52px] w-full items-center gap-3 rounded-[14px] px-5 py-3 text-[15px] font-medium transition",
        active
          ? "border border-[#d1a14f]/55 bg-[linear-gradient(90deg,_rgba(242,187,92,0.24),_rgba(177,123,34,0.12))] text-[#f4d18b] shadow-[inset_0_1px_0_rgba(255,255,255,0.04)]"
          : "text-[#d4dcec] hover:bg-white/5 hover:text-white",
      ].join(" ")}
    >
      <span className={active ? "text-[#f4c46a]" : "text-[#b9c7d8]"}>{icon}</span>
      <span>{label}</span>
    </button>
  );
}

function PageIntro() {
  return (
    <section>
      <p className="text-[11px] font-semibold uppercase tracking-[0.28em] text-[#92a3ba]">
        Indonesia Stock Market
      </p>
      <h1 className="mt-1.5 text-[60px] font-semibold tracking-[-0.045em] text-white">
        Market Overview
      </h1>
      <p className="mt-2 max-w-4xl text-[17px] leading-7 text-[#aeb9ca]">
        Explore Indonesian stocks using fundamental analysis, valuation signals, and
        historical evidence.
      </p>
    </section>
  );
}

function Toolbar({
  showingCount,
  totalCount,
  viewMode,
  onViewModeChange,
  pageSize,
  onPageSizeChange,
  sectors,
  filters,
  onFilterChange,
  isPending,
}: {
  showingCount: number;
  totalCount: number;
  viewMode: ViewMode;
  onViewModeChange: (mode: ViewMode) => void;
  pageSize: MarketPageSize;
  onPageSizeChange: (size: MarketPageSize) => void;
  sectors: string[];
  filters: MarketFilterSelection;
  onFilterChange: (patch: Partial<MarketFilterSelection>) => void;
  isPending: boolean;
}) {
  return (
    <section className="mt-4 flex flex-wrap items-center justify-between gap-4">
      <p className="flex shrink-0 flex-wrap items-center gap-x-1.5 whitespace-nowrap text-[13px] text-[#ced7e5]">
        <span>Showing</span>
        <span className="font-semibold text-white">{showingCount}</span>
        <span>of {totalCount} stocks</span>
        {/* The page size is stated as a separate "per page" setting. Writing it
            as "Showing 8 of 4 stocks" (page size vs. filtered total) reads as a
            contradiction as soon as a filter narrows the set below one page. */}
        <span className="text-[#8f9db1]">·</span>
        <PageSizeSelect pageSize={pageSize} onPageSizeChange={onPageSizeChange} />
        <span className="text-[#8f9db1]">per page</span>
        {/* A screener that narrows silently looks broken when a filter is on, so
            the state is stated next to the count it produced. */}
        {filters.sector ? (
          <span className="text-[#f4d18b]">· {filters.sector}</span>
        ) : null}
        {filters.stockType ? (
          <span className="text-[#f4d18b]">· {filters.stockType}</span>
        ) : null}
        {isPending ? <span className="text-[#8f9db1]">· updating…</span> : null}
      </p>
      <div className="flex min-w-0 flex-wrap items-center justify-end gap-2">
        <ScreenerSelect
          label="All Sectors"
          value={filters.sector}
          widthClass="w-[168px]"
          options={[
            { value: "", label: "All Sectors" },
            ...sectors.map((sector) => ({ value: sector, label: sector })),
          ]}
          onChange={(value) => onFilterChange({ sector: value })}
        />
        <ScreenerSelect
          label="All Stock Type"
          value={filters.stockType}
          widthClass="w-[158px]"
          options={[
            { value: "", label: "All Stock Type" },
            ...MARKET_STOCK_TYPE_OPTIONS.map((type) => ({
              value: type,
              label: titleCase(type),
            })),
          ]}
          onChange={(value) =>
            onFilterChange({ stockType: value as MarketStockType | "" })
          }
        />
        <span className="shrink-0 whitespace-nowrap text-xs text-[#bcc8d8]">Sort by</span>
        <ScreenerSelect
          label="Sort by"
          value={filters.sort}
          widthClass="w-[184px]"
          options={MARKET_SORT_OPTIONS.map((option) => ({
            value: option.value,
            label: option.label,
          }))}
          onChange={(value) => onFilterChange({ sort: value as MarketSort })}
        />
        <ViewToggle viewMode={viewMode} onViewModeChange={onViewModeChange} />
        <button
          type="button"
          className="shrink-0 rounded-xl bg-[linear-gradient(180deg,_#f5c15d,_#e0a843)] px-5 py-2.5 text-[13px] font-semibold text-[#1d170f] shadow-[0_8px_20px_rgba(224,168,67,0.24)] transition hover:brightness-105"
        >
          Add Stock
        </button>
      </div>
    </section>
  );
}

/** `FAST GROWER` -> `Fast Grower`, for a label that reads as prose. */
function titleCase(value: string) {
  return value
    .toLowerCase()
    .split(" ")
    .map((word) => (word ? word[0].toUpperCase() + word.slice(1) : word))
    .join(" ");
}

/**
 * Inline page-size picker that sits inside the "Showing … of N stocks"
 * sentence. It keeps the sentence's own type size (13px) but is drawn as a
 * boxed control, so it reads as something clickable rather than as a plain
 * number.
 *
 * A native `<select>` is used on purpose: it already handles keyboard
 * navigation, focus and the mobile picker sheet, which a custom dropdown would
 * have to reimplement for four static options.
 */
function PageSizeSelect({
  pageSize,
  onPageSizeChange,
}: {
  pageSize: MarketPageSize;
  onPageSizeChange: (size: MarketPageSize) => void;
}) {
  return (
    <span className="relative inline-flex shrink-0 items-center">
      <select
        value={pageSize}
        onChange={(event) => onPageSizeChange(parseMarketPageSize(event.target.value))}
        aria-label="Stocks per page"
        title="Stocks per page"
        className="cursor-pointer appearance-none rounded-lg border border-white/15 bg-[#0c1728]/90 py-0.5 pl-2 pr-6 text-[13px] font-semibold text-white shadow-[inset_0_1px_0_rgba(255,255,255,0.04)] outline-none transition hover:border-[#f2bb5c]/50 hover:bg-[#12203a] focus-visible:border-[#f2bb5c]/70 focus-visible:ring-1 focus-visible:ring-[#f2bb5c]/40"
      >
        {MARKET_PAGE_SIZE_OPTIONS.map((option) => (
          <option key={option} value={option} className="bg-[#091322] text-[#d9e1ed]">
            {option}
          </option>
        ))}
      </select>
      <ChevronDownIcon className="pointer-events-none absolute right-1.5 h-3.5 w-3.5 text-[#8f9db1]" />
    </span>
  );
}

/**
 * A screener facet.
 *
 * This replaces the previous static pill, which looked like a dropdown but was
 * a `<button>` with no handler — the label could never change and the filter
 * could never apply. A native `<select>` is used for the same reason the page
 * size picker uses one: it already handles keyboard navigation, focus, and the
 * mobile picker sheet, which a custom listbox would have to reimplement.
 */
function ScreenerSelect({
  label,
  value,
  options,
  onChange,
  widthClass,
}: {
  label: string;
  value: string;
  options: { value: string; label: string }[];
  onChange: (value: string) => void;
  widthClass: string;
}) {
  return (
    <span className={["relative inline-flex shrink-0 items-center", widthClass].join(" ")}>
      <select
        value={value}
        onChange={(event) => onChange(event.target.value)}
        aria-label={label}
        title={label}
        className="h-9 w-full cursor-pointer appearance-none truncate rounded-xl border border-white/10 bg-[#091322]/80 py-0 pl-3 pr-8 text-xs text-[#d9e1ed] shadow-[inset_0_1px_0_rgba(255,255,255,0.03)] outline-none transition hover:border-white/16 hover:bg-[#0c1728] focus-visible:border-[#f2bb5c]/70 focus-visible:ring-1 focus-visible:ring-[#f2bb5c]/40"
      >
        {options.map((option) => (
          <option key={option.value} value={option.value} className="bg-[#091322] text-[#d9e1ed]">
            {option.label}
          </option>
        ))}
      </select>
      <ChevronDownIcon className="pointer-events-none absolute right-2.5 h-3.5 w-3.5 shrink-0 text-[#8f9db1]" />
    </span>
  );
}

function ViewToggle({
  viewMode,
  onViewModeChange,
}: {
  viewMode: ViewMode;
  onViewModeChange: (mode: ViewMode) => void;
}) {
  return (
    <div className="flex items-center gap-2 rounded-xl border border-white/10 bg-[#091322]/80 p-1">
      <button
        type="button"
        onClick={() => onViewModeChange("grid")}
        className={[
          "flex h-8 w-8 items-center justify-center rounded-lg transition",
          viewMode === "grid"
            ? "bg-[#f0ba58]/18 text-[#f4c96c]"
            : "text-[#9ba9bd] hover:bg-white/5 hover:text-white",
        ].join(" ")}
        aria-pressed={viewMode === "grid"}
      >
        <GridIcon className="h-3.5 w-3.5" />
      </button>
      <button
        type="button"
        onClick={() => onViewModeChange("list")}
        className={[
          "flex h-8 w-8 items-center justify-center rounded-lg transition",
          viewMode === "list"
            ? "bg-[#f0ba58]/18 text-[#f4c96c]"
            : "text-[#9ba9bd] hover:bg-white/5 hover:text-white",
        ].join(" ")}
        aria-pressed={viewMode === "list"}
      >
        <ListIcon className="h-3.5 w-3.5" />
      </button>
    </div>
  );
}

function StockCollection({
  stocks,
  viewMode,
  showDiscoveryCard,
}: {
  stocks: MarketOverviewStock[];
  viewMode: ViewMode;
  showDiscoveryCard: boolean;
}) {
  if (viewMode === "list") {
    return (
      <section className="mt-4 space-y-4">
        <StockTable stocks={stocks} />
        {showDiscoveryCard ? <DiscoveryCard /> : null}
      </section>
    );
  }

  return (
    <section className="mt-4 grid grid-cols-2 gap-4 md:grid-cols-3 xl:grid-cols-4">
      {stocks.map((stock) => (
        <StockCard key={stock.ticker} stock={stock} />
      ))}
      {showDiscoveryCard ? <DiscoveryCard /> : null}
    </section>
  );
}

/** Signal pill colours, shared by the grid card and the list table. */
function signalToneClass(signal: MarketOverviewStock["signal"]) {
  if (signal === "Undervalued") return "border-[#1fcf86]/35 bg-[#0d2b22] text-[#3ef0a9]";
  if (signal === "Overvalued") return "border-[#ff4b5f]/30 bg-[#32161e] text-[#ff5f73]";
  if (signal === "Mixed") return "border-[#c79d51]/35 bg-[#2f2717] text-[#f1c56d]";
  return "border-[#8f9db1]/30 bg-[#1a2332]/60 text-[#9aa9bf]";
}

function isPositiveMove(stock: MarketOverviewStock) {
  return (stock.change ?? 0) >= 0;
}

function mosToneClass(value: number | null) {
  if (value == null || !Number.isFinite(value) || value === 0) return "text-[#9aa9bf]";
  return value > 0 ? "text-[#49f3ae]" : "text-[#ff5967]";
}

/** The sparkline shows monthly closes for the last year, not today's move. */
function oneYearTrendTone(points: number[]) {
  if (points.length < 2) return "#8f9db1";
  const first = points[0];
  const latest = points[points.length - 1];
  if (latest > first) return "#2de49d";
  if (latest < first) return "#ff485f";
  return "#8f9db1";
}

function StockCard({ stock }: { stock: MarketOverviewStock }) {
  const router = useRouter();

  const mosTone = mosToneClass(stock.mos);
  const sparklineTone = oneYearTrendTone(stock.sparkline);
  const signalTone = signalToneClass(stock.signal);

  const handleCardClick = () => {
    router.push(`/market/${stock.ticker}`);
  };

  const handleCardKeyDown = (event: React.KeyboardEvent<HTMLElement>) => {
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      handleCardClick();
    }
  };

  const handleStarClick = (event: React.MouseEvent<HTMLButtonElement>) => {
    event.stopPropagation();
  };

  const handleStarKeyDown = (event: React.KeyboardEvent<HTMLButtonElement>) => {
    event.stopPropagation();
  };

  return (
    <article
      role="link"
      tabIndex={0}
      onClick={handleCardClick}
      onKeyDown={handleCardKeyDown}
      className={[
        "group cursor-pointer rounded-[20px] border border-white/10",
        "bg-[radial-gradient(circle_at_top,_rgba(44,108,178,0.12),_transparent_35%),linear-gradient(180deg,_rgba(11,23,37,0.96),_rgba(7,16,28,0.96))]",
        "shadow-[0_24px_48px_rgba(0,0,0,0.28)]",
        "transition duration-200 ease-out",
        "hover:-translate-y-0.5 hover:border-white/20 hover:shadow-[0_28px_56px_rgba(0,0,0,0.38)]",
        "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#f2bb5c]/60",
        "p-[14px]",
      ].join(" ")}
    >
      <div>
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0 flex-1">
            <h2 className="text-[16px] font-semibold tracking-[-0.02em] text-white md:text-[17px]">
              {stock.ticker}
            </h2>

            <p className="mt-1 truncate text-[13px] leading-5 text-[#b6c2d4]">
              {stock.companyName}
            </p>
          </div>

          <button
            type="button"
            onClick={handleStarClick}
            onKeyDown={handleStarKeyDown}
            className="relative z-10 text-[#8999af] transition hover:text-white"
            aria-label={`Save ${stock.ticker}`}
          >
            <StarIcon className="h-5 w-5" />
          </button>
        </div>

        <div className="mt-2.5 flex flex-wrap gap-2">
          <TagChip label={stock.sector === "Not available" ? "N/A" : stock.sector} tone="blue" />
          <TagChip label={stock.stockType === "Not available" ? "N/A" : stock.stockType} tone="slate" />
        </div>

        <div
          className={
            "mt-3.5 grid grid-cols-[minmax(0,0.85fr)_minmax(120px,1.15fr)] items-end gap-4"
          }
        >
          <div>
            <p className="text-[16px] font-semibold tracking-[-0.03em] text-white sm:text-[17px]">
              {formatRupiah(stock.price)}
            </p>
          </div>

          <Sparkline
            className="mt-0"
            points={stock.sparkline}
            stroke={sparklineTone}
          />
        </div>

        <div className="mt-4 grid grid-cols-2 overflow-hidden rounded-2xl border border-white/8 bg-[#07111c]/72">
          <MetricBlock label="Signal" className="border-r border-b border-white/8">
            {stock.signal === "Not available" ? (
              <span className="text-[16px] font-semibold text-white">N/A</span>
            ) : (
              <span
                className={[
                  "inline-flex rounded-[10px] border px-3 py-2 text-[13px] font-semibold",
                  signalTone,
                ].join(" ")}
              >
                {stock.signal}
              </span>
            )}
          </MetricBlock>

          <MetricBlock label="Win Rate" className="border-b border-white/8">
            {stock.winRatePercent != null && stock.winRateCases != null ? (
              <div className="flex flex-col items-start">
                <span className="text-[16px] font-semibold text-white">
                  {formatMarketPercent(stock.winRatePercent)}
                </span>
                <span className="mt-0.5 text-[11px] font-normal text-[#a4afbf]">
                  ({stock.winRateCases} {stock.winRateCases === 1 ? "Case" : "Cases"})
                </span>
              </div>
            ) : (
              <span className="text-[16px] font-semibold text-white">N/A</span>
            )}
          </MetricBlock>

          <MetricBlock label="MoS" className="border-r border-white/8">
            {stock.mos != null ? (
              <span className={["text-[16px] font-semibold", mosTone].join(" ")}>
                {formatMarketPercent(stock.mos)}
              </span>
            ) : (
              <span className="text-[16px] font-semibold text-white">N/A</span>
            )}
          </MetricBlock>

          <MetricBlock label="Valuation Methods">
            {stock.methodUndervalued != null && stock.methodValid != null ? (
              <div className="text-[16px] font-semibold text-white">
                {stock.methodUndervalued} / {stock.methodValid}
              </div>
            ) : (
              <span className="text-[16px] font-semibold text-white">N/A</span>
            )}
          </MetricBlock>
        </div>

        <div className="mt-3.5 flex items-center justify-between gap-4 text-[12px] text-[#9eabbe]">
          <span>Updated {stock.updatedAt ?? "N/A"}</span>

          <span className="flex items-center gap-1.5 text-[12px] font-semibold text-[#efbf63] transition group-hover:text-[#ffd88a]">
            View Analysis
            <ArrowRightIcon className="h-3.5 w-3.5 transition-transform duration-200 group-hover:translate-x-0.5" />
          </span>
        </div>
      </div>
    </article>
  );
}

/**
 * List view: the same fields the grid card shows, laid out as one wide table so
 * many stocks can be scanned down a single column each instead of across
 * separate cards.
 */
function StockTable({ stocks }: { stocks: MarketOverviewStock[] }) {
  const router = useRouter();

  const openStock = (ticker: string) => router.push(`/market/${ticker}`);
  const handleRowKeyDown = (
    event: React.KeyboardEvent<HTMLTableRowElement>,
    ticker: string,
  ) => {
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      openStock(ticker);
    }
  };

  return (
    <div className="overflow-x-auto rounded-2xl border border-white/10 bg-[linear-gradient(180deg,_rgba(11,23,37,0.94),_rgba(7,16,28,0.96))] shadow-[0_24px_48px_rgba(0,0,0,0.28)]">
      <table className="w-full min-w-[1100px] border-collapse text-left text-xs">
        <thead className="bg-[#081523] text-[10px] uppercase tracking-[0.1em] text-[#7f8fa6]">
          <tr>
            <th className="whitespace-nowrap px-4 py-3 font-semibold">Ticker</th>
            <th className="whitespace-nowrap px-4 py-3 font-semibold">Sector</th>
            <th className="whitespace-nowrap px-4 py-3 font-semibold">Stock Type</th>
            <th className="whitespace-nowrap px-4 py-3 font-semibold">Price</th>
            <th className="whitespace-nowrap px-4 py-3 font-semibold">1Y Trend</th>
            <th className="whitespace-nowrap px-4 py-3 font-semibold">Signal</th>
            <th className="whitespace-nowrap px-4 py-3 font-semibold">Win Rate</th>
            <th className="whitespace-nowrap px-4 py-3 font-semibold">MoS</th>
            <th className="whitespace-nowrap px-4 py-3 font-semibold">Valuation Methods</th>
            <th className="whitespace-nowrap px-4 py-3 font-semibold">Updated</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-white/[0.06]">
          {stocks.map((stock) => (
            <tr
              key={stock.ticker}
              role="link"
              tabIndex={0}
              onClick={() => openStock(stock.ticker)}
              onKeyDown={(event) => handleRowKeyDown(event, stock.ticker)}
              className="cursor-pointer transition hover:bg-white/[0.03] focus-visible:bg-white/[0.04] focus-visible:outline-none"
            >
              <td className="px-4 py-3 align-middle">
                <div className="text-[13px] font-semibold tracking-[-0.01em] text-white">
                  {stock.ticker}
                </div>
                <div className="mt-0.5 max-w-[220px] truncate text-[11px] leading-4 text-[#8f9db1]">
                  {stock.companyName}
                </div>
              </td>

              <td className="whitespace-nowrap px-4 py-3 align-middle">
                <TagChip label={stock.sector === "Not available" ? "N/A" : stock.sector} tone="blue" />
              </td>

              <td className="whitespace-nowrap px-4 py-3 align-middle">
                <TagChip label={stock.stockType === "Not available" ? "N/A" : stock.stockType} tone="slate" />
              </td>

              <td className="whitespace-nowrap px-4 py-3 align-middle">
                <span
                  className={[
                    "text-[13px] font-semibold",
                    isPositiveMove(stock) ? "text-[#49f3ae]" : "text-[#ff5967]",
                  ].join(" ")}
                >
                  {formatRupiah(stock.price)}
                </span>
              </td>

              <td className="w-[170px] px-4 py-3 align-middle">
                <Sparkline
                  className="max-w-[170px]"
                  points={stock.sparkline}
                  stroke={oneYearTrendTone(stock.sparkline)}
                />
              </td>

              <td className="whitespace-nowrap px-4 py-3 align-middle">
                {stock.signal === "Not available" ? (
                  <span className="text-[13px] font-semibold text-white">N/A</span>
                ) : (
                  <span
                    className={[
                      "inline-flex rounded-[10px] border px-2.5 py-1 text-[11px] font-semibold",
                      signalToneClass(stock.signal),
                    ].join(" ")}
                  >
                    {stock.signal}
                  </span>
                )}
              </td>

              <td className="whitespace-nowrap px-4 py-3 align-middle">
                {stock.winRatePercent != null && stock.winRateCases != null ? (
                  <span className="flex flex-col items-start text-[13px] font-semibold text-white">
                    <span>{formatMarketPercent(stock.winRatePercent)}</span>
                    <span className="mt-0.5 text-[10px] font-normal text-[#a4afbf]">
                      ({stock.winRateCases} {stock.winRateCases === 1 ? "Case" : "Cases"})
                    </span>
                  </span>
                ) : (
                  <span className="text-[13px] font-semibold text-white">N/A</span>
                )}
              </td>

              <td className="whitespace-nowrap px-4 py-3 align-middle">
                {stock.mos != null ? (
                  <span
                    className={[
                      "text-[13px] font-semibold",
                      mosToneClass(stock.mos),
                    ].join(" ")}
                  >
                    {formatMarketPercent(stock.mos)}
                  </span>
                ) : (
                  <span className="text-[13px] font-semibold text-white">N/A</span>
                )}
              </td>

              <td className="whitespace-nowrap px-4 py-3 align-middle">
                {stock.methodUndervalued != null && stock.methodValid != null ? (
                  <span className="text-[13px] font-semibold text-white">
                    {stock.methodUndervalued} / {stock.methodValid}
                  </span>
                ) : (
                  <span className="text-[13px] font-semibold text-white">N/A</span>
                )}
              </td>

              <td className="whitespace-nowrap px-4 py-3 align-middle text-[11px] text-[#9eabbe]">
                {stock.updatedAt ?? "N/A"}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function MetricBlock({
  label,
  children,
  className = "border-r border-white/8 last:border-r-0",
}: {
  label: string;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <div className={["px-3 py-2.5", className].join(" ")}>
      <div className="text-[11px] text-[#8e9bb0]">{label}</div>
      <div className="mt-1.5">{children}</div>
    </div>
  );
}

function TagChip({
  label,
  tone,
}: {
  label: string;
  tone: "blue" | "slate";
}) {
  return (
    <span
      className={[
        "rounded-full px-2 py-0.5 text-[10px] font-medium leading-4",
        tone === "blue"
          ? "bg-[#123551] text-[#92cdf4]"
          : "bg-white/8 text-[#ced8e6]",
      ].join(" ")}
    >
      {label}
    </span>
  );
}

function DiscoveryCard() {
  return (
    <article
      className={[
        "relative overflow-hidden rounded-[20px] border border-white/10 bg-[radial-gradient(circle_at_top,_rgba(242,187,92,0.12),_transparent_38%),linear-gradient(180deg,_rgba(12,22,35,0.96),_rgba(9,18,29,0.98))] shadow-[0_24px_48px_rgba(0,0,0,0.28)]",
        "min-h-[258px] p-6",
      ].join(" ")}
    >
      <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(circle_at_center,_rgba(242,187,92,0.08),_transparent_45%)]" />
      <div className="relative flex h-full flex-col items-center justify-center text-center">
        <span className="flex h-[76px] w-[76px] items-center justify-center rounded-full border border-[#d6a24d]/45 bg-[#f2bb5c]/8 text-[#f2bb5c] shadow-[0_0_30px_rgba(242,187,92,0.12)]">
          <BarChartIcon className="h-9 w-9" />
        </span>
        <h3 className="mt-6 text-[18px] font-semibold text-white">Discover more stocks</h3>
        <p className="mt-3 max-w-[270px] text-[15px] leading-7 text-[#b8c4d5]">
          Search or adjust your filters to find other stocks in our research database.
        </p>
        <button
          type="button"
          className="mt-6 rounded-xl border border-[#d6a24d]/85 px-5 py-3 text-sm font-semibold text-[#f3c76f] transition hover:bg-[#f2bb5c]/8"
        >
          Browse All Stocks
        </button>
      </div>
    </article>
  );
}

function Pagination({
  currentPage,
  totalPages,
  onPageChange,
}: {
  currentPage: number;
  totalPages: number;
  onPageChange: (page: number) => void;
}) {
  return (
    <div className="mt-9 flex items-center justify-center gap-3 text-sm">
      <PaginationArrow
        disabled={currentPage === 1}
        direction="left"
        onClick={() => onPageChange(Math.max(1, currentPage - 1))}
      />
      <div className="flex items-center gap-2 text-[#cbd6e5]">
        {Array.from({ length: totalPages }, (_, index) => {
          const page = index + 1;
          const active = currentPage === page;
          return (
            <button
              key={page}
              type="button"
              onClick={() => onPageChange(page)}
              className={[
                "flex h-8 w-8 items-center justify-center rounded-lg transition",
                active
                  ? "bg-[#f2bb5c] font-semibold text-[#1d170f]"
                  : "hover:bg-white/6 hover:text-white",
              ].join(" ")}
            >
              {page}
            </button>
          );
        })}
      </div>
      <PaginationArrow
        disabled={currentPage === totalPages}
        direction="right"
        onClick={() => onPageChange(Math.min(totalPages, currentPage + 1))}
      />
    </div>
  );
}

function PaginationArrow({
  direction,
  disabled,
  onClick,
}: {
  direction: "left" | "right";
  disabled: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      className="flex h-8 w-8 items-center justify-center rounded-lg border border-white/10 bg-[#0a1423] text-[#aeb9ca] transition hover:bg-white/6 hover:text-white disabled:cursor-not-allowed disabled:opacity-40"
    >
      {direction === "left" ? (
        <ChevronLeftIcon className="h-4 w-4" />
      ) : (
        <ChevronRightIcon className="h-4 w-4" />
      )}
    </button>
  );
}

function Sparkline({
  points,
  stroke,
  className,
}: {
  points: number[];
  stroke: string;
  className?: string;
}) {
  const width = 124;
  const height = 44;

  if (points.length < 2) {
    return (
      <div className={["flex min-w-0 w-full items-end justify-end gap-3", className ?? ""].join(" ")}>
        <span className="text-[16px] font-semibold text-white">N/A</span>
      </div>
    );
  }

  const max = Math.max(...points);
  const min = Math.min(...points);
  const range = max - min || 1;

  const polyline = points
    .map((point, index) => {
      const x = (index / (points.length - 1)) * width;
      const y = height - ((point - min) / range) * (height - 8) - 4;
      return `${x},${y}`;
    })
    .join(" ");

  const areaPath = `M 0 ${height} L ${polyline.replace(/ /g, " L ")} L ${width} ${height} Z`;

  return (
    <div className={["flex min-w-0 w-full items-end justify-end gap-3", className ?? ""].join(" ")}>
      <svg
        width={width}
        height={height}
        viewBox={`0 0 ${width} ${height}`}
        preserveAspectRatio="none"
        className="h-11 min-w-0 flex-1 overflow-visible"
        aria-hidden="true"
      >
        <defs>
          <linearGradient id={`spark-${stroke.replace("#", "")}`} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={stroke} stopOpacity="0.28" />
            <stop offset="100%" stopColor={stroke} stopOpacity="0" />
          </linearGradient>
        </defs>
        <path d={areaPath} fill={`url(#spark-${stroke.replace("#", "")})`} />
        <polyline
          fill="none"
          points={polyline}
          stroke={stroke}
          strokeWidth="2.2"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      </svg>
      <span className="text-xs text-[#b8c4d4]">1Y</span>
    </div>
  );
}

function formatRupiah(value: number | null) {
  if (value == null || !Number.isFinite(value)) return "N/A";
  return formatCurrencyRupiah(value);
}

function formatMarketPercent(value: number | null) {
  if (value == null || !Number.isFinite(value)) return "N/A";
  return `${new Intl.NumberFormat("id-ID", {
    minimumFractionDigits: 0,
    maximumFractionDigits: 1,
  }).format(value)}%`;
}

function StockLensLogo() {
  return (
    <div className="flex items-center gap-3">
      <span className="text-[#f2bb5c]">
        <LogoMark className="h-10 w-8" />
      </span>
      <div>
        <div className="text-[18px] font-semibold tracking-[-0.02em] text-white">StockLens</div>
        <div className="text-[11px] leading-4 text-[#b1bdd0]">Understand Indonesian Stocks</div>
      </div>
    </div>
  );
}

function Icon({
  className,
  children,
  viewBox = "0 0 24 24",
}: {
  className?: string;
  children: React.ReactNode;
  viewBox?: string;
}) {
  return (
    <svg
      viewBox={viewBox}
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
      className={className}
      aria-hidden="true"
    >
      {children}
    </svg>
  );
}

function LogoMark({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 36 44" className={className} aria-hidden="true">
      <rect x="2" y="24" width="6" height="16" rx="2" fill="currentColor" />
      <rect x="12" y="16" width="6" height="24" rx="2" fill="currentColor" opacity="0.9" />
      <rect x="22" y="9" width="6" height="31" rx="2" fill="currentColor" opacity="0.8" />
      <rect x="32" y="2" width="6" height="38" rx="2" fill="currentColor" opacity="0.7" />
    </svg>
  );
}

function BarChartIcon({ className }: { className?: string }) {
  return (
    <Icon className={className}>
      <path d="M4 20V10" />
      <path d="M10 20V4" />
      <path d="M16 20v-7" />
      <path d="M22 20V7" />
    </Icon>
  );
}

function UserIcon({ className }: { className?: string }) {
  return (
    <Icon className={className}>
      <path d="M12 12a4 4 0 1 0 0-8 4 4 0 0 0 0 8Z" />
      <path d="M4 20c1.7-3.2 4.3-4.8 8-4.8S18.3 16.8 20 20" />
    </Icon>
  );
}

function CapIcon({ className }: { className?: string }) {
  return (
    <Icon className={className}>
      <path d="m2 10 10-5 10 5-10 5-10-5Z" />
      <path d="M6 12v4c0 1.7 2.7 3 6 3s6-1.3 6-3v-4" />
    </Icon>
  );
}

function GridIcon({ className }: { className?: string }) {
  return (
    <Icon className={className}>
      <rect x="4" y="4" width="6" height="6" rx="1" />
      <rect x="14" y="4" width="6" height="6" rx="1" />
      <rect x="4" y="14" width="6" height="6" rx="1" />
      <rect x="14" y="14" width="6" height="6" rx="1" />
    </Icon>
  );
}

function ListIcon({ className }: { className?: string }) {
  return (
    <Icon className={className}>
      <path d="M8 7h12" />
      <path d="M8 12h12" />
      <path d="M8 17h12" />
      <path d="M4 7h.01" />
      <path d="M4 12h.01" />
      <path d="M4 17h.01" />
    </Icon>
  );
}

function StarIcon({ className }: { className?: string }) {
  return (
    <Icon className={className}>
      <path d="m12 3 2.7 5.6 6.2.9-4.5 4.4 1.1 6.1L12 17.1 6.5 20l1.1-6.1L3 9.5l6.2-.9L12 3Z" />
    </Icon>
  );
}

function ArrowRightIcon({ className }: { className?: string }) {
  return (
    <Icon className={className}>
      <path d="M5 12h14" />
      <path d="m13 6 6 6-6 6" />
    </Icon>
  );
}

function ChevronDownIcon({ className }: { className?: string }) {
  return (
    <Icon className={className}>
      <path d="m6 9 6 6 6-6" />
    </Icon>
  );
}

function ChevronLeftIcon({ className }: { className?: string }) {
  return (
    <Icon className={className}>
      <path d="m15 18-6-6 6-6" />
    </Icon>
  );
}

function ChevronRightIcon({ className }: { className?: string }) {
  return (
    <Icon className={className}>
      <path d="m9 18 6-6-6-6" />
    </Icon>
  );
}
