"use client";

import React, { useEffect, useMemo, useState } from "react";
import { createPortal } from "react-dom";
import type { BacktestCase, BacktestConsensus, BacktestVerdict, StockDetail } from "@/data/mock-stock-details";
import { SectionCard } from "@/components/ui/section-card";
import { StatusBadge } from "@/components/ui/status-badge";
import { formatRupiah } from "@/utils/currency";
import {
  aggregateBacktestOverview,
  backtestConsensusDescription,
  backtestMethodology,
  calculateBacktestMetrics,
  classifyMethodsAbovePrice,
  classifyMosMain,
  countMethodsAboveAnalysisPrice,
} from "@/lib/analysis";
import { BacktestOverview, BacktestOverviewIcon } from "./backtest-overview";

type ViewMode = "compact" | "detail";
const numberFormat = new Intl.NumberFormat("id-ID", { maximumFractionDigits: 2 });

function percent(value: number | null | undefined) {
  return value === null || value === undefined || !Number.isFinite(value) ? "N/A" : `${numberFormat.format(value * 100)}%`;
}

function price(value: number | null | undefined) {
  return value === null || value === undefined || !Number.isFinite(value) ? "N/A" : formatRupiah(value);
}

function badgeTone(value: BacktestConsensus | BacktestVerdict) {
  if (value === "UNDERVALUED" || value === "WIN" || value === "RECOVERED") return "positive" as const;
  if (value === "OVERVALUED" || value === "CONFIRMED" || value === "REPRICE") return "info" as const;
  if (value === "RISK") return "overvalued" as const;
  if (value === "MIXED" || value === "FLAT" || value === "OBSERVE") return "stable" as const;
  // `N/A` is "not applicable", not a verdict: the neutral tone keeps it from
  // reading as either Undervalued or Overvalued.
  if (value === "N/A") return "skipped" as const;
  return "caution" as const;
}

function Icon({ kind }: { kind: "list" | "up" | "down" | "target" | "close" }) {
  const paths = {
    list: <><rect x="4" y="4" width="16" height="16" rx="2" /><path d="M8 9h8M8 13h8M8 17h5" /></>,
    up: <><path d="M4 17 10 11l4 3 6-7" /><path d="M15 7h5v5" /></>,
    down: <><path d="M4 7 10 13l4-3 6 7" /><path d="M15 17h5v-5" /></>,
    target: <><circle cx="12" cy="12" r="8" /><circle cx="12" cy="12" r="4" /><path d="m12 12 4-4" /></>,
    close: <><path d="m6 6 12 12M18 6 6 18" /></>,
  };
  return <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" className="h-4 w-4" aria-hidden="true">{paths[kind]}</svg>;
}

function rangeText(range: ReturnType<typeof calculateBacktestMetrics>["ranges"][number]) {
  return <span className="inline-flex items-center gap-1.5"><span className="font-semibold text-[#3ef0a9]">▲ {percent(range.highReturn)}</span><span className="text-[#607086]">||</span><span className="font-semibold text-[#ff8b82]">▼ {percent(range.lowReturn)}</span></span>;
}

function priceRangeText(range: ReturnType<typeof calculateBacktestMetrics>["ranges"][number]) {
  return <span className="inline-flex items-center gap-1.5"><span className="font-semibold text-[#3ef0a9]">▲ {price(range.high)}</span><span className="text-[#607086]">||</span><span className="font-semibold text-[#ff8b82]">▼ {price(range.low)}</span></span>;
}

function methodValue(testCase: BacktestCase, method: string) {
  return testCase.methods.find((item) => item.method === method)?.intrinsicValue ?? null;
}

function undervaluedMethods(testCase: BacktestCase, analysisPrice = testCase.analysisPrice) {
  return countMethodsAboveAnalysisPrice(testCase, analysisPrice);
}

/**
 * The workbook rule for a consensus with enough valid methods:
 * `undervalued >= 3` -> `UNDERVALUED`, otherwise `OVERVALUED`.
 *
 * It takes only the undervalued count because the denominator is already known
 * to be at least three by the time it is called; the `/3`, `/4`, `/5` text is
 * display, not input.
 */
function badgeFromCounts(undervaluedMethods: number): BacktestConsensus {
  return undervaluedMethods >= backtestMethodology.classification.methodUndervaluedMinimum ? "UNDERVALUED" : "OVERVALUED";
}

/**
 * Translate the stored `calc_backtest_cases.consensus` text into the badge the
 * table renders: `'N/A'` stays `N/A`, `'3|5'` becomes `UNDERVALUED`, `'1|5'`
 * becomes `OVERVALUED`.
 *
 * `null` means "no stored badge", which lets the caller fall back instead of
 * guessing; that is a contract break, not a value.
 */
function consensusFromStoredValue(testCase: BacktestCase): BacktestConsensus | null {
  const stored = testCase.consensus;
  if (stored === null || stored === undefined) return null;
  if (stored === "N/A") return "N/A";
  const [undervalued, valid] = stored.split("|");
  const undervaluedCount = Number(undervalued);
  const validCount = Number(valid);
  if (!Number.isFinite(undervaluedCount) || !Number.isFinite(validCount)) return null;
  return badgeFromCounts(undervaluedCount);
}

/**
 * Consensus badge, read from the database — never recomputed here.
 *
 * `calc_backtest_cases.consensus` stores either `'undervalued|valid'` or `'N/A'`
 * when fewer than three methods are valid, and `resolve_consensus` in
 * `supabase/backtest_engine.py` is its single owner. The browser used to
 * recompute it with `classifyMethodsAbovePrice`, which only has two branches and
 * cannot see the three-method threshold, so 44 stored cases (`consensus_valid <
 * 3`) displayed a verdict the database never wrote
 * (docs/CONSENSUS_ARCHITECTURE.md sections 2.3 and 3.3).
 *
 * The stored value is preferred; the two counts are only a fallback for a row
 * that somehow arrives without its badge, and the fallback keeps the database's
 * own rule so a missing column can never invent an `OVERVALUED`.
 */
function consensusByMethod(testCase: BacktestCase, analysisPrice = testCase.analysisPrice): BacktestConsensus {
  const stored = consensusFromStoredValue(testCase);
  if (stored) return stored;
  const { undervaluedMethods, totalMethods } = classifyMethodsAbovePrice(testCase.methods, analysisPrice);
  return totalMethods < backtestMethodology.classification.methodUndervaluedMinimum ? "N/A" : badgeFromCounts(undervaluedMethods);
}

/**
 * "Consensus by MoS" is derived from the stored `mos_main`, not read from
 * `verdict_mos` (that column holds the outcome verdict: WIN/RISK/CONFIRMED/...).
 *
 * A `null` MoS means no MoS could be computed at all — the same cases where
 * fewer than three methods are valid — so it reads `N/A`, not `OVERVALUED`
 * (docs/CONSENSUS_ARCHITECTURE.md section 2.4: 41 cases).
 */
function consensusByMos(testCase: BacktestCase): BacktestConsensus {
  return testCase.mosMain === null ? "N/A" : classifyMosMain(testCase.mosMain);
}

type CaseMetrics = ReturnType<typeof calculateBacktestMetrics>;

/**
 * Metrics for one case, preferring the values stored in the database.
 *
 * The tab used to recompute everything from `pricePath`, which was correct only
 * while `pricePath` held the real daily bars. Stored data only keeps the window
 * *extremes*, and extremes cannot rebuild the per-horizon windows: under the
 * workbook's `DATEDIF` month arithmetic an extreme in month 6 can fall outside
 * the 6M window. Recomputing produced 18 wrong cells across the 18 AUTO cases,
 * so stored columns win whenever they exist.
 *
 * `Peak Month` / `Trough Month` need the same treatment for a second reason: the
 * workbook counts *completed* months (`DATEDIF`) while `monthsBetween` counts
 * month *boundaries*, so the two differ by one when the extreme lands in the
 * month right after a month-end analysis date (AUTO 2023-Q3 is 0 vs 1).
 *
 * Peak and trough returns are the stored `return_peak` / `return_down` now that
 * the analysis price is no longer editable: re-deriving them existed only to
 * follow a price the reader typed, and that control is gone. The per-horizon
 * returns are still derived, because the database stores the horizon high and
 * low prices but no matching return column.
 *
 * Falling back to `calculateBacktestMetrics` keeps the sample dataset (which has
 * no stored columns) working unchanged.
 */
function caseMetrics(testCase: BacktestCase): CaseMetrics {
  const derived = calculateBacktestMetrics(testCase);
  const stored = testCase.stored;
  // A zero analysis price would make every return non-finite; the derived path
  // already handles that, so defer to it.
  if (!stored || testCase.analysisPrice === 0) return derived;

  const ratio = (value: number) => value / testCase.analysisPrice - 1;
  const horizons: [number | null, number | null][] = [
    [stored.high3m, stored.low3m],
    [stored.high6m, stored.low6m],
    [stored.high9m, stored.low9m],
    [stored.high12m, stored.low12m],
  ];

  // The stored pair is either both present or both absent. Treating a lone side
  // as "not available" keeps a half-populated row from rendering a real number
  // next to an empty one.
  const ranges = horizons.map(([high, low]) =>
    high === null || low === null
      ? { high: null, low: null, highReturn: null, lowReturn: null }
      : { high, low, highReturn: ratio(high), lowReturn: ratio(low) },
  );

  return {
    ranges,
    returns: ranges.map((range) => range.highReturn),
    peakReturn: stored.returnPeak,
    troughReturn: stored.returnDown,
    downPrice: stored.troughPrice,
    peakPrice: stored.peakPrice,
    peakMonth: testCase.peakMonth ?? derived.peakMonth,
    troughMonth: testCase.troughMonth ?? derived.troughMonth,
  };
}

function VerdictBadge({ value, className = "" }: { value: BacktestVerdict; className?: string }) {
  const tone = value === "WIN" ? "bg-[#58b98f] text-black" : value === "RECOVERED" ? "bg-[#65b4d1] text-black" : value === "RISK" ? "bg-[#d77f7e] text-black" : value === "REPRICE" ? "bg-[#a48ad2] text-black" : value === "CONFIRMED" ? "bg-[#65b4d1] text-black" : value === "FLAT" || value === "OBSERVE" ? "bg-[#9aa7b5] text-black" : "bg-[#c49a50] text-black";
  return <span className={`inline-flex max-w-full items-center rounded-md border border-white/10 px-2 py-1 text-xs font-normal tracking-wide ${tone} ${className}`}>{value}</span>;
}
function consensusTooltip(kind: "method" | "mos") {
  return backtestConsensusDescription(kind);
}

function TooltipLabel({ label, tooltip }: { label: string; tooltip: string }) {
  const [isOpen, setIsOpen] = useState(false);
  useEffect(() => {
    if (!isOpen) return;
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") setIsOpen(false);
    };
    document.addEventListener("keydown", closeOnEscape);
    return () => document.removeEventListener("keydown", closeOnEscape);
  }, [isOpen]);

  const modal = isOpen ? (
    <div className="fixed inset-0 z-[9999] flex items-center justify-center bg-black/75 p-4 backdrop-blur-sm" role="dialog" aria-modal="true" aria-label={label} onClick={() => setIsOpen(false)}>
      <div className="w-full max-w-lg overflow-hidden rounded-2xl border border-white/15 bg-[#0b1929] text-left shadow-[0_24px_80px_rgba(0,0,0,0.6)]" onClick={(event) => event.stopPropagation()}>
        <div className="border-b border-white/10 px-5 py-4">
          <h3 className="text-base font-normal text-white">{label}</h3>
        </div>
        <p className="break-words whitespace-normal px-5 py-5 text-sm font-normal leading-6 text-[#d6e0ed]">{tooltip}</p>
      </div>
    </div>
  ) : null;

  return <><span className="inline-flex items-center gap-1"><span>{label}</span><button type="button" onClick={() => setIsOpen(true)} className="inline-flex h-3.5 w-3.5 shrink-0 cursor-pointer items-center justify-center rounded-full border border-current text-[9px] font-normal normal-case opacity-70 hover:opacity-100" aria-label={`Show information about ${label}`}>i</button></span>{typeof document !== "undefined" && modal ? createPortal(modal, document.body) : null}</>;
}

function DetailDrawer({ testCase, onClose }: { testCase: BacktestCase; onClose: () => void }) {
  return <div className="fixed inset-0 z-50 flex items-end justify-center bg-black/60 p-0 backdrop-blur-sm md:items-center md:p-6" role="dialog" aria-modal="true"><div className="max-h-[92vh] w-full max-w-5xl overflow-y-auto rounded-t-2xl border border-white/10 bg-[#081523] p-5 shadow-2xl md:rounded-2xl md:p-6"><div className="flex items-start justify-between gap-4"><div><div className="text-xs uppercase tracking-[0.14em] text-[#7f8fa6]">Historical Case Detail</div><h3 className="mt-1 text-xl font-semibold text-white">{testCase.ticker} · {testCase.quarter}</h3></div><button type="button" onClick={onClose} className="rounded-lg p-2 text-[#9aa9bf] hover:bg-white/5 hover:text-white" aria-label="Close detail"><Icon kind="close" /></button></div><div className="mt-5 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">{[["Sector", testCase.sector], ["Stock Type", testCase.stockType], ["Analysis Date", testCase.analysisDate], ["Original Analysis Price", price(testCase.analysisPrice)]].map(([label, cardValue]) => <div key={label} className="rounded-xl border border-white/8 bg-[#07111c]/70 p-3"><div className="text-[10px] text-[#7f8fa6]">{label}</div><div className="mt-1 text-sm font-semibold text-white">{cardValue}</div></div>)}</div><div className="mt-5 rounded-xl border border-white/8 bg-[#07111c]/70 p-4"><h4 className="text-sm font-semibold text-white">Case Classification</h4><div className="mt-3 grid grid-cols-2 gap-3 text-xs"><div><span className="text-[#7f8fa6]">Consensus</span><div className="mt-1"><StatusBadge tone={badgeTone(consensusByMethod(testCase))}>{consensusByMethod(testCase)}</StatusBadge></div></div><div><span className="text-[#7f8fa6]">Historical Verdict</span><div className="mt-1"><StatusBadge tone={badgeTone(testCase.verdict)}>{testCase.verdict}</StatusBadge></div></div></div><div className="mt-4 grid grid-cols-3 gap-3">{[["MoS Main", percent(testCase.mosMain)], ["MoS Peter", percent(testCase.mosPeter)], ["MoS Weight", percent(testCase.mosWeight)]].map(([label, cardValue]) => <div key={label}><div className="text-[10px] text-[#7f8fa6]">{label}</div><div className="mt-1 text-sm font-semibold text-[#f2d18f]">{cardValue}</div></div>)}</div></div></div></div>;
}

type DetailColumn = { key: string; label: React.ReactNode; width: string; group: string; render: (testCase: BacktestCase) => React.ReactNode };
function DetailTableV2({ cases, onSelect }: { cases: BacktestCase[]; onSelect: (testCase: BacktestCase) => void }) {
  const columns: DetailColumn[] = [
    { key: "ticker", label: "Ticker", width: "w-[90px]", group: "IDENTITY", render: (item) => <span className="font-semibold text-white">{item.ticker}</span> },
    { key: "stockType", label: "Stock Type", width: "w-[130px]", group: "IDENTITY", render: (item) => item.stockType },
    { key: "quarter", label: "Quarter", width: "w-[110px]", group: "IDENTITY", render: (item) => <button type="button" onClick={() => onSelect(item)} className="text-[#65b7ee] hover:text-white hover:underline">{item.quarter}</button> },
    { key: "analysisDate", label: "ANALYSIS DATE", width: "w-[125px]", group: "IDENTITY", render: (item) => item.analysisDate },
    { key: "analysisPrice", label: "Analysis Price", width: "w-[126px]", group: "IDENTITY", render: (item) => price(item.analysisPrice) },
    { key: "lynch", label: "IV Peter Lynch", width: "w-[125px]", group: "VALUATION", render: (item) => price(methodValue(item, "Peter Lynch / Adaptive")) },
    { key: "sectorValue", label: "IV Type & Sector", width: "w-[125px]", group: "VALUATION", render: (item) => price(methodValue(item, "Type & Sector Weighted")) },
    { key: "pbv", label: "IV Mean Reversion PBV", width: "w-[150px]", group: "VALUATION", render: (item) => price(methodValue(item, "Mean Reversion PBV")) },
    { key: "ddm", label: "IV DIVIDEND DISCOUNT MODEL", width: "w-[205px]", group: "VALUATION", render: (item) => price(methodValue(item, "Dividend Discount Model")) },
    { key: "earnings", label: "IV Discounted Earnings", width: "w-[155px]", group: "VALUATION", render: (item) => price(methodValue(item, "Discounted Earnings")) },
    { key: "methods", label: "Undervalued Methods", width: "w-[145px]", group: "METHOD", render: (item) => undervaluedMethods(item, item.analysisPrice) },
    { key: "consensusMethod", label: <TooltipLabel label="Consensus by Method" tooltip={consensusTooltip("method")} />, width: "w-[165px]", group: "METHOD", render: (item) => { const consensus = consensusByMethod(item); return <StatusBadge tone={badgeTone(consensus)}>{consensus}</StatusBadge>; } },
    { key: "mosMain", label: "MoS Main", width: "w-[105px]", group: "VALUATION", render: (item) => percent(item.mosMain) },
    { key: "mosPeter", label: "MoS Peter", width: "w-[105px]", group: "VALUATION", render: (item) => percent(item.mosPeter) },
    { key: "mosWeight", label: "MoS Weight", width: "w-[110px]", group: "MOS", render: (item) => percent(item.mosWeight) },
    { key: "consensusMos", label: <TooltipLabel label="Consensus by MoS" tooltip={consensusTooltip("mos")} />, width: "w-[165px]", group: "MOS", render: (item) => { const consensus = consensusByMos(item); return <StatusBadge tone={badgeTone(consensus)}>{consensus}</StatusBadge>; } },
    { key: "yield", label: "Yield (%)", width: "w-[100px]", group: "BUSINESS", render: (item) => percent(item.context.yield) },
    { key: "revenueYoY", label: "Revenue YoY", width: "w-[115px]", group: "BUSINESS", render: (item) => percent(item.context.revenueYoY) },
    { key: "revPercent", label: "Rev %", width: "w-[90px]", group: "BUSINESS", render: (item) => percent(item.context.revenueYoY) },
    { key: "netIncomeYoY", label: "Net Income YoY", width: "w-[135px]", group: "BUSINESS", render: (item) => percent(item.context.netIncomeYoY) },
    { key: "niPercent", label: "NI %", width: "w-[90px]", group: "BUSINESS", render: (item) => percent(item.context.netIncomeYoY) },
    { key: "epsMomentum", label: "EPS Momentum", width: "w-[125px]", group: "BUSINESS", render: (item) => item.context.epsMomentum },
    { key: "revenueMomentum", label: "Revenue Momentum", width: "w-[145px]", group: "BUSINESS", render: (item) => item.context.revenueMomentum },
    { key: "roeTrend", label: "ROE Trend", width: "w-[110px]", group: "BUSINESS", render: (item) => item.context.roeTrend },
    { key: "ret3m", label: "Ret 3M", width: "w-[190px]", group: "RETURNS", render: (item) => rangeText(caseMetrics(item).ranges[0]) },
    { key: "ret6m", label: "Ret 6M", width: "w-[190px]", group: "RETURNS", render: (item) => rangeText(caseMetrics(item).ranges[1]) },
    { key: "ret9m", label: "Ret 9M", width: "w-[190px]", group: "RETURNS", render: (item) => rangeText(caseMetrics(item).ranges[2]) },
    { key: "ret12m", label: "Ret 12M", width: "w-[200px]", group: "RETURNS", render: (item) => rangeText(caseMetrics(item).ranges[3]) },
    { key: "price3m", label: "Price 3M", width: "w-[190px]", group: "PRICES", render: (item) => priceRangeText(caseMetrics(item).ranges[0]) },
    { key: "price6m", label: "Price 6M", width: "w-[190px]", group: "PRICES", render: (item) => priceRangeText(caseMetrics(item).ranges[1]) },
    { key: "price9m", label: "Price 9M", width: "w-[190px]", group: "PRICES", render: (item) => priceRangeText(caseMetrics(item).ranges[2]) },
    { key: "price12m", label: "Price 12M", width: "w-[200px]", group: "PRICES", render: (item) => priceRangeText(caseMetrics(item).ranges[3]) },
    { key: "peakReturn", label: "Ret Peak", width: "w-[77px]", group: "PEAK / TROUGH", render: (item) => percent(caseMetrics(item).peakReturn) },
    { key: "peakPrice", label: "Peak Price", width: "w-[84px]", group: "PEAK / TROUGH", render: (item) => price(caseMetrics(item).peakPrice) },
    { key: "peakMonth", label: "Peak Month", width: "w-[100px]", group: "PEAK / TROUGH", render: (item) => { const month = caseMetrics(item).peakMonth; return month === null ? "N/A" : `${month} mo`; } },
    { key: "troughReturn", label: "Ret Trough", width: "w-[84px]", group: "PEAK / TROUGH", render: (item) => percent(caseMetrics(item).troughReturn) },
    { key: "downPrice", label: "Trough Price", width: "w-[95px]", group: "PEAK / TROUGH", render: (item) => price(caseMetrics(item).downPrice) },
    { key: "troughMonth", label: "Trough Month", width: "w-[110px]", group: "PEAK / TROUGH", render: (item) => { const month = caseMetrics(item).troughMonth; return month === null ? "N/A" : `${month} mo`; } },
    { key: "verdict", label: "Verdict by Method", width: "w-[145px]", group: "VERDICT", render: (item) => <VerdictBadge value={item.verdict} /> },
    { key: "verdictMos", label: "Verdict by MoS", width: "w-[145px]", group: "VERDICT", render: (item) => <VerdictBadge value={item.verdictMos} /> },
  ];
  const groups = [{ label: "IDENTITY", span: 5, className: "bg-[#1c3851] text-[#d8ecff]" }, { label: "VALUATION BY METHOD", span: 7, className: "bg-[#1c3851] text-[#d8ecff]" }, { label: "VALUATION BY MOS", span: 4, className: "bg-[#1c3851] text-[#d8ecff]" }, { label: "BUSINESS / FUNDAMENTAL SIGNALS", span: 8, className: "bg-[#1c3851] text-[#d8ecff]" }, { label: "RETURNS", span: 4, className: "bg-[#1c3851] text-[#d8ecff]" }, { label: "PRICES", span: 4, className: "bg-[#1c3851] text-[#d8ecff]" }, { label: "PEAK / TROUGH", span: 6, className: "bg-[#1c3851] text-[#d8ecff]" }, { label: "VERDICT", span: 2, className: "bg-[#1c3851] text-[#d8ecff]" }];
  const centeredValueColumns = ["ret3m", "ret6m", "ret9m", "ret12m", "price3m", "price6m", "price9m", "price12m"];
  return <div className="overflow-x-auto rounded-xl border border-white/8"><table className="w-max min-w-full border-collapse text-left text-xs"><thead className="bg-[#081523] text-[9px] uppercase tracking-wider text-[#7f8fa6]"><tr>{groups.map((group) => <th key={group.label} colSpan={group.span} className={`border-r-2 border-b-2 border-[#07111c] px-3 py-3 text-left align-top font-bold tracking-[0.12em] ${group.className}`}>{group.label}</th>)}</tr><tr>{columns.map((column, index) => <th key={column.key} className={`${column.width} whitespace-nowrap border-r border-white/10 px-3 py-3 text-left align-top ${index === 0 || columns[index - 1]?.group !== column.group ? "border-l-2 border-l-[#07111c] bg-white/[0.04]" : ""}`}>{column.label}</th>)}</tr></thead><tbody>{cases.map((item) => <tr key={item.id} className="border-t border-white/8 transition hover:bg-white/[0.02]">{columns.map((column, index) => <td key={column.key} className={`${column.width} whitespace-nowrap border-r border-white/8 px-3 py-3 text-[#b9c6d8] ${centeredValueColumns.includes(column.key) ? "text-center" : ""} ${index === 0 || columns[index - 1]?.group !== column.group ? "border-l-2 border-l-[#07111c] bg-white/[0.015]" : ""}`}>{column.render(item)}</td>)}</tr>)}</tbody></table></div>;
}

function CompactTable({ cases, onSelect }: { cases: BacktestCase[]; onSelect: (testCase: BacktestCase) => void }) {
  const columns = [
    { key: "stockType", label: "Stock Type", width: "w-[7%]" },
    { key: "quarter", label: "Quarter", width: "w-[6%]" },
    { key: "analysisDate", label: "ANALYSIS DATE", width: "w-[8%]" },
    { key: "analysisPrice", label: "Analysis Price", width: "w-[8%]" },
    { key: "methods", label: "Undervalued Methods", width: "w-[8%]" },
    { key: "methodConsensus", label: "Consensus by Method", width: "w-[11%]" },
    { key: "mosMain", label: "MoS Main", width: "w-[6%]" },
    { key: "mosConsensus", label: "Consensus by MoS", width: "w-[10%]" },
    { key: "peakReturn", label: "Ret Peak", width: "w-[7%]" },
    { key: "troughReturn", label: "Ret Down", width: "w-[7%]" },
    { key: "verdict", label: "Verdict by Method", width: "w-[11%]" },
    { key: "verdictMos", label: "Verdict by MoS", width: "w-[11%]" },
  ];
  const compactGroups = [
    { label: "IDENTITY", span: 4, className: "bg-[#1c3851] text-[#d8ecff]" },
    { label: "VALUATION BY METHOD", span: 2, className: "bg-[#1c3851] text-[#d8ecff]" },
    { label: "VALUATION BY MOS", span: 2, className: "bg-[#1c3851] text-[#d8ecff]" },
    { label: "PEAK / TROUGH", span: 2, className: "bg-[#1c3851] text-[#d8ecff]" },
    { label: "VERDICT", span: 2, className: "bg-[#1c3851] text-[#d8ecff]" },
  ];

  return <div className="w-full overflow-hidden rounded-xl border border-white/8"><table className="w-full table-fixed border-collapse text-left text-[10px] leading-tight min-[1441px]:text-xs"><thead className="bg-[#081523] text-[8px] uppercase tracking-wider text-[#7f8fa6] min-[1441px]:text-[9px]"><tr>{compactGroups.map((group) => <th key={group.label} colSpan={group.span} className={`border-r-2 border-b-2 border-[#07111c] px-1.5 py-2 text-left align-top font-bold tracking-[0.1em] min-[1441px]:px-2 min-[1441px]:py-2.5 ${group.className}`}>{group.label}</th>)}</tr><tr>{columns.map((column) => <th key={column.key} className={`${column.width} whitespace-normal break-words border-r border-white/8 px-1.5 py-2 text-left align-top min-[1441px]:px-2 min-[1441px]:py-2.5`}>{column.key === "methodConsensus" ? <TooltipLabel label={column.label} tooltip={consensusTooltip("method")} /> : column.key === "mosConsensus" ? <TooltipLabel label={column.label} tooltip={consensusTooltip("mos")} /> : column.label}</th>)}</tr></thead><tbody>{cases.map((item) => { const analysisPrice = item.analysisPrice; const derived = caseMetrics(item); const methodConsensus = consensusByMethod(item, analysisPrice); const mosConsensus = consensusByMos(item); return <tr key={item.id} className="border-t border-white/8 transition hover:bg-white/[0.02]"><td className="break-words border-r border-white/8 px-1.5 py-2 text-[#b9c6d8] min-[1441px]:px-2 min-[1441px]:py-2.5">{item.stockType}</td><td className="break-words border-r border-white/8 px-1.5 py-2 min-[1441px]:px-2 min-[1441px]:py-2.5"><button type="button" onClick={() => onSelect(item)} className="break-words text-[#65b7ee] hover:text-white hover:underline">{item.quarter}</button></td><td className="break-words border-r border-white/8 px-1.5 py-2 text-[#b9c6d8] min-[1441px]:px-2 min-[1441px]:py-2.5">{item.analysisDate}</td><td className="break-words border-r border-white/8 px-1.5 py-2 text-right text-white min-[1441px]:px-2 min-[1441px]:py-2.5">{price(analysisPrice)}</td><td className="break-words border-r border-white/8 px-1.5 py-2 text-center text-[#b9c6d8] min-[1441px]:px-2 min-[1441px]:py-2.5">{undervaluedMethods(item, analysisPrice)}</td><td className="break-words border-r border-white/8 px-1.5 py-2 min-[1441px]:px-2 min-[1441px]:py-2.5"><StatusBadge className="whitespace-normal break-words px-1 py-0.5 text-[8px] leading-3 min-[1441px]:px-1.5 min-[1441px]:py-1 min-[1441px]:text-[9px]" tone={badgeTone(methodConsensus)}>{methodConsensus}</StatusBadge></td><td className="break-words border-r border-white/8 px-1.5 py-2 text-right text-[#f2d18f] min-[1441px]:px-2 min-[1441px]:py-2.5">{percent(item.mosMain)}</td><td className="break-words border-r border-white/8 px-1.5 py-2 min-[1441px]:px-2 min-[1441px]:py-2.5"><StatusBadge className="whitespace-normal break-words px-1 py-0.5 text-[8px] leading-3 min-[1441px]:px-1.5 min-[1441px]:py-1 min-[1441px]:text-[9px]" tone={badgeTone(mosConsensus)}>{mosConsensus}</StatusBadge></td><td className="break-words border-r border-white/8 px-1.5 py-2 text-right text-[#3ef0a9] min-[1441px]:px-2 min-[1441px]:py-2.5">{percent(derived.peakReturn)}</td><td className="break-words border-r border-white/8 px-1.5 py-2 text-right text-[#ff8b82] min-[1441px]:px-2 min-[1441px]:py-2.5">{percent(derived.troughReturn)}</td><td className="break-words border-r border-white/8 px-1.5 py-2 min-[1441px]:px-2 min-[1441px]:py-2.5"><VerdictBadge value={item.verdict} className="whitespace-normal break-words px-1 py-0.5 text-[8px] leading-3 min-[1441px]:px-1.5 min-[1441px]:py-1 min-[1441px]:text-[9px]" /></td><td className="break-words border-r border-white/8 px-1.5 py-2 min-[1441px]:px-2 min-[1441px]:py-2.5"><VerdictBadge value={item.verdictMos} className="whitespace-normal break-words px-1 py-0.5 text-[8px] leading-3 min-[1441px]:px-1.5 min-[1441px]:py-1 min-[1441px]:text-[9px]" /></td></tr>; })}</tbody></table></div>;
}

export function BacktestTabContent({ stock }: { stock: StockDetail }) {
  const [view, setView] = useState<ViewMode>("compact");
  const [selectedCase, setSelectedCase] = useState<BacktestCase | null>(null);
  const cases = useMemo(() => stock.backtest?.cases ?? [], [stock.backtest?.cases]);
  const overviewAggregates = useMemo(
    () => aggregateBacktestOverview(cases),
    [cases],
  );
  const methodology = stock.backtest?.methodology;
  return <div className="space-y-6"><header><h2 className="text-3xl font-bold tracking-tight text-white">Backtest</h2><p className="mt-1 text-sm text-[#aeb9ca]">See how the valuation framework would have performed across historical cases.</p></header><BacktestOverview aggregates={overviewAggregates} /><SectionCard icon={<BacktestOverviewIcon kind="history" />} title="Historical Cases" subtitle="List of historical valuation cases. Click a quarter to see the case detail." actionSlot={<div className="flex items-center gap-1 self-start rounded-xl border border-white/10 bg-[#091322]/80 p-1 text-xs"><button type="button" onClick={() => setView("compact")} className={`rounded-lg px-4 py-1.5 font-semibold transition ${view === "compact" ? "bg-[#f2bb5c] text-[#1d170f]" : "text-[#9aa9bf] hover:bg-white/5 hover:text-white"}`}>Compact View</button><button type="button" onClick={() => setView("detail")} className={`rounded-lg px-4 py-1.5 font-semibold transition ${view === "detail" ? "bg-[#f2bb5c] text-[#1d170f]" : "text-[#9aa9bf] hover:bg-white/5 hover:text-white"}`}>Detail View</button></div>}>{cases.length === 0 ? <div className="p-10 text-center text-sm text-[#9aa9bf]">No historical backtest cases are available for {stock.ticker} yet.</div> : view === "compact" ? <CompactTable cases={cases} onSelect={setSelectedCase} /> : <DetailTableV2 cases={cases} onSelect={setSelectedCase} />}</SectionCard>{methodology && <SectionCard title="How the Backtest Works" subtitle="A simple and transparent process to evaluate historical outcomes."><div className="grid gap-4 lg:grid-cols-3">{methodology.processSteps.map((step) => <Step key={step.number} number={step.number} title={step.title} text={step.text} />)}</div></SectionCard>}{selectedCase && <DetailDrawer testCase={selectedCase} onClose={() => setSelectedCase(null)} />}</div>;
}

function Step({ number, title, text }: { number: string; title: string; text: string }) { return <article className="relative rounded-xl border border-white/8 bg-[#081523]/75 p-4"><div className="flex h-8 w-8 items-center justify-center rounded-lg border border-[#3892d0]/30 bg-[#3892d0]/10 text-xs font-bold text-[#65b7ee]">{number}</div><h4 className="mt-4 text-sm font-semibold text-white">{title}</h4><p className="mt-2 text-xs leading-5 text-[#9aa9bf]">{text}</p></article>; }
