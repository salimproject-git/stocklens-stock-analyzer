"use client";

import { useMemo, useState } from "react";

type Verdict = "Undervalued" | "Fairly Valued" | "Overvalued";
type ViewMode = "grid" | "list";

type Stock = {
  ticker: string;
  companyName: string;
  sector: string;
  stockType: string;
  price: number;
  change: number;
  changePercent: number;
  sparkline: number[];
  verdict: Verdict;
  mos: number;
  evidenceWins: number;
  evidenceTotal: number;
  updatedAt: string;
};

const SIDEBAR_WIDTH = 240;
const PAGE_SIZE = 5;

const mockStocks: Stock[] = [
  {
    ticker: "BBCA",
    companyName: "Bank Central Asia Tbk",
    sector: "Financials",
    stockType: "Large Cap",
    price: 9200,
    change: 100,
    changePercent: 1.1,
    sparkline: [24, 29, 27, 34, 36, 35, 42, 40, 45, 51, 49, 55],
    verdict: "Fairly Valued",
    mos: 12.3,
    evidenceWins: 5,
    evidenceTotal: 8,
    updatedAt: "12 Sep 2026",
  },
  {
    ticker: "AUTO",
    companyName: "Astra Otoparts Tbk",
    sector: "Automotive",
    stockType: "Cyclical",
    price: 1950,
    change: 50,
    changePercent: 2.63,
    sparkline: [18, 21, 23, 27, 30, 29, 34, 35, 33, 38, 43, 46],
    verdict: "Undervalued",
    mos: 38.4,
    evidenceWins: 4,
    evidenceTotal: 4,
    updatedAt: "12 Sep 2026",
  },
  {
    ticker: "ERAA",
    companyName: "Erajaya Swasembada Tbk",
    sector: "Consumer Cyclical",
    stockType: "Mid Cap",
    price: 450,
    change: -10,
    changePercent: -2.17,
    sparkline: [44, 48, 45, 47, 43, 42, 44, 39, 41, 37, 36, 38],
    verdict: "Fairly Valued",
    mos: 8.7,
    evidenceWins: 3,
    evidenceTotal: 6,
    updatedAt: "12 Sep 2026",
  },
  {
    ticker: "SIDO",
    companyName: "Industri Jamu dan Farmasi Sido Muncul Tbk",
    sector: "Consumer Defensive",
    stockType: "Large Cap",
    price: 640,
    change: 15,
    changePercent: 2.4,
    sparkline: [20, 18, 22, 21, 24, 29, 33, 36, 35, 40, 45, 43],
    verdict: "Undervalued",
    mos: 28.1,
    evidenceWins: 6,
    evidenceTotal: 8,
    updatedAt: "12 Sep 2026",
  },
  {
    ticker: "PTBA",
    companyName: "Bukit Asam Tbk",
    sector: "Energy",
    stockType: "Cyclical",
    price: 2350,
    change: -40,
    changePercent: -1.67,
    sparkline: [40, 41, 39, 43, 42, 40, 38, 41, 45, 43, 37, 35],
    verdict: "Overvalued",
    mos: -12.4,
    evidenceWins: 2,
    evidenceTotal: 6,
    updatedAt: "12 Sep 2026",
  },
  {
    ticker: "WIFI",
    companyName: "Solusi Sinergi Digital Tbk",
    sector: "Telecommunication",
    stockType: "Growth",
    price: 1490,
    change: 80,
    changePercent: 5.67,
    sparkline: [16, 19, 22, 25, 30, 35, 34, 39, 44, 47, 49, 54],
    verdict: "Undervalued",
    mos: 31.6,
    evidenceWins: 4,
    evidenceTotal: 5,
    updatedAt: "11 Sep 2026",
  },
  {
    ticker: "INDF",
    companyName: "Indofood Sukses Makmur Tbk",
    sector: "Consumer Staples",
    stockType: "Large Cap",
    price: 6850,
    change: 75,
    changePercent: 1.11,
    sparkline: [31, 32, 30, 29, 33, 36, 39, 38, 40, 42, 43, 45],
    verdict: "Fairly Valued",
    mos: 10.4,
    evidenceWins: 5,
    evidenceTotal: 7,
    updatedAt: "11 Sep 2026",
  },
  {
    ticker: "JSMR",
    companyName: "Jasa Marga Tbk",
    sector: "Infrastructure",
    stockType: "Value",
    price: 4780,
    change: -60,
    changePercent: -1.24,
    sparkline: [45, 44, 46, 43, 42, 41, 40, 39, 38, 40, 37, 35],
    verdict: "Overvalued",
    mos: -6.8,
    evidenceWins: 2,
    evidenceTotal: 5,
    updatedAt: "10 Sep 2026",
  },
];

const totalPages = Math.ceil(mockStocks.length / PAGE_SIZE);

export function MarketOverviewPage() {
  const [currentPage, setCurrentPage] = useState(1);
  const [viewMode, setViewMode] = useState<ViewMode>("grid");

  const visibleStocks = useMemo(() => {
    const start = (currentPage - 1) * PAGE_SIZE;
    return mockStocks.slice(start, start + PAGE_SIZE);
  }, [currentPage]);

  const showingCount = visibleStocks.length;

  return (
    <div className="h-screen overflow-hidden bg-[radial-gradient(circle_at_top_right,_rgba(245,192,91,0.14),_transparent_24%),linear-gradient(180deg,_#06111d_0%,_#030914_100%)] text-[#f5f7fb]">
      <Sidebar />
      <div
        className="fixed inset-x-0 inset-y-0 overflow-hidden"
        style={{
          left: SIDEBAR_WIDTH,
        }}
      >
        <main className="h-full overflow-y-auto gold-scroll">
          <div className="min-h-full w-full max-w-[1800px] px-8 pb-12 pt-5">
            <PageIntro />
            <Toolbar
              showingCount={showingCount}
              totalCount={mockStocks.length}
              viewMode={viewMode}
              onViewModeChange={setViewMode}
            />
            <StockCollection
              stocks={visibleStocks}
              viewMode={viewMode}
              showDiscoveryCard={currentPage === 1}
            />
            <Pagination
              currentPage={currentPage}
              totalPages={totalPages}
              onPageChange={setCurrentPage}
            />
          </div>
        </main>
      </div>
    </div>
  );
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
}: {
  showingCount: number;
  totalCount: number;
  viewMode: ViewMode;
  onViewModeChange: (mode: ViewMode) => void;
}) {
  return (
    <section className="mt-4 flex items-center justify-between gap-4">
      <p className="shrink-0 whitespace-nowrap text-[13px] text-[#ced7e5]">
        Showing {showingCount} of {totalCount} stocks
      </p>
      <div className="flex min-w-0 items-center justify-end gap-2">
        <FilterPill label="All Sectors" />
        <FilterPill label="All Stock Type" size="wide" />
        <FilterPill label="Syariah" />
        <span className="shrink-0 whitespace-nowrap text-xs text-[#bcc8d8]">Sort by</span>
        <FilterPill label="Market Cap (Largest)" size="xwide" />
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

function FilterPill({
  label,
  size = "md",
}: {
  label: string;
  size?: "md" | "wide" | "xwide";
}) {
  const widthClass =
    size === "xwide" ? "w-[172px]" : size === "wide" ? "w-[134px]" : "w-[122px]";
  return (
    <button
      type="button"
      className={[
        "shrink-0 flex h-9 items-center justify-between rounded-xl border border-white/10 bg-[#091322]/80 px-3 !text-xs text-[#d9e1ed] shadow-[inset_0_1px_0_rgba(255,255,255,0.03)] transition hover:border-white/16 hover:bg-[#0c1728]",
        widthClass,
      ].join(" ")}
      style={{ fontSize: 12 }}
    >
      <span className="truncate">{label}</span>
      <ChevronDownIcon className="ml-3 h-3.5 w-3.5 shrink-0 text-[#8f9db1]" />
    </button>
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
  stocks: Stock[];
  viewMode: ViewMode;
  showDiscoveryCard: boolean;
}) {
  if (viewMode === "list") {
    return (
      <section className="mt-4 space-y-4">
        {stocks.map((stock) => (
          <StockCard key={stock.ticker} stock={stock} compact />
        ))}
        {showDiscoveryCard ? <DiscoveryCard compact /> : null}
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

function StockCard({ stock, compact = false }: { stock: Stock; compact?: boolean }) {
  const isPositive = stock.change >= 0;
  const priceTone = isPositive ? "text-[#49f3ae]" : "text-[#ff5967]";
  const sparklineTone = isPositive ? "#2de49d" : "#ff485f";
  const verdictTone =
    stock.verdict === "Undervalued"
      ? "border-[#1fcf86]/35 bg-[#0d2b22] text-[#3ef0a9]"
      : stock.verdict === "Overvalued"
        ? "border-[#ff4b5f]/30 bg-[#32161e] text-[#ff5f73]"
        : "border-[#c79d51]/35 bg-[#2f2717] text-[#f1c56d]";

  return (
    <article
      className={[
        "rounded-[20px] border border-white/10 bg-[radial-gradient(circle_at_top,_rgba(44,108,178,0.12),_transparent_35%),linear-gradient(180deg,_rgba(11,23,37,0.96),_rgba(7,16,28,0.96))] shadow-[0_24px_48px_rgba(0,0,0,0.28)]",
        compact ? "flex gap-5 p-5" : "p-[14px]",
      ].join(" ")}
    >
      <div className={compact ? "flex-1" : undefined}>
        <div className="flex items-start justify-between gap-3">
          <div>
            <h2 className="text-[16px] font-semibold tracking-[-0.02em] text-white md:text-[17px]">
              {stock.ticker}
            </h2>
            <p className="mt-1 line-clamp-2 text-[13px] leading-5 text-[#b6c2d4]">
              {stock.companyName}
            </p>
          </div>
          <button
            type="button"
            className="text-[#8999af] transition hover:text-white"
            aria-label={`Save ${stock.ticker}`}
          >
            <StarIcon className="h-5 w-5" />
          </button>
        </div>

        <div className="mt-2.5 flex flex-wrap gap-2">
          <TagChip label={stock.sector} tone="blue" />
          <TagChip label={stock.stockType} tone="slate" />
        </div>

        <div className={compact ? "mt-5 grid grid-cols-[minmax(0,180px)_minmax(0,1fr)] gap-5" : "mt-3.5"}>
          <div>
            <p className="text-[16px] font-semibold tracking-[-0.03em] text-white sm:text-[17px]">
              {formatRupiah(stock.price)}
            </p>
            <p className={["mt-1 text-[14px] font-semibold", priceTone].join(" ")}>
              {formatSignedRupiah(stock.change)} ({formatPercent(stock.changePercent)})
            </p>
          </div>
          <Sparkline
            className={compact ? "mt-0" : "mt-4"}
            points={stock.sparkline}
            stroke={sparklineTone}
          />
        </div>

        <div className="mt-4 grid grid-cols-3 overflow-hidden rounded-2xl border border-white/8 bg-[#07111c]/72">
          <MetricBlock label="Valuation">
            <span
              className={[
                "inline-flex rounded-[10px] border px-3 py-2 text-[13px] font-semibold",
                verdictTone,
              ].join(" ")}
            >
              {stock.verdict}
            </span>
          </MetricBlock>
          <MetricBlock label="MoS">
            <span className={["text-[16px] font-semibold", priceTone].join(" ")}>
              {formatSignedPercent(stock.mos)}
            </span>
          </MetricBlock>
          <MetricBlock label="Historical Evidence">
            <div className="text-[16px] font-semibold text-white">
              {stock.evidenceWins} / {stock.evidenceTotal}
            </div>
            <div className="mt-0.5 text-[11px] text-[#a4afbf]">successful cases</div>
          </MetricBlock>
        </div>

        <div className="mt-3.5 flex items-center justify-between gap-4 text-[12px] text-[#9eabbe]">
          <span>Updated {stock.updatedAt}</span>
          <button
            type="button"
            className="flex items-center gap-2 text-sm font-semibold text-[#efbf63] transition hover:text-[#ffd88a]"
          >
            View Analysis
            <ArrowRightIcon className="h-4 w-4" />
          </button>
        </div>
      </div>
    </article>
  );
}

function MetricBlock({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <div className="border-r border-white/8 px-3 py-2.5 last:border-r-0">
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
        "rounded-full px-3 py-1.5 text-[12px] font-medium",
        tone === "blue"
          ? "bg-[#123551] text-[#92cdf4]"
          : "bg-white/8 text-[#ced8e6]",
      ].join(" ")}
    >
      {label}
    </span>
  );
}

function DiscoveryCard({ compact = false }: { compact?: boolean }) {
  return (
    <article
      className={[
        "relative overflow-hidden rounded-[20px] border border-white/10 bg-[radial-gradient(circle_at_top,_rgba(242,187,92,0.12),_transparent_38%),linear-gradient(180deg,_rgba(12,22,35,0.96),_rgba(9,18,29,0.98))] shadow-[0_24px_48px_rgba(0,0,0,0.28)]",
        compact ? "p-5" : "min-h-[258px] p-6",
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
    <div className={["flex items-end justify-between gap-3", className ?? ""].join(" ")}>
      <svg
        width={width}
        height={height}
        viewBox={`0 0 ${width} ${height}`}
        className="overflow-visible"
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

function formatRupiah(value: number) {
  return `Rp ${new Intl.NumberFormat("id-ID").format(value)}`;
}

function formatSignedRupiah(value: number) {
  const sign = value > 0 ? "+" : "";
  return `${sign}${new Intl.NumberFormat("id-ID").format(value)}`;
}

function formatPercent(value: number) {
  const sign = value > 0 ? "+" : "";
  return `${sign}${new Intl.NumberFormat("id-ID", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(value)}%`;
}

function formatSignedPercent(value: number) {
  const sign = value > 0 ? "" : "";
  return `${sign}${new Intl.NumberFormat("id-ID", {
    minimumFractionDigits: 1,
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
