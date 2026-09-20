"use client";

import React, { useEffect, useMemo, useState } from "react";
import { createPortal } from "react-dom";
import type { BacktestCase, BacktestConsensus, BacktestVerdict, StockDetail } from "@/data/mock-stock-details";
import { SectionCard } from "@/components/ui/section-card";
import { StatusBadge } from "@/components/ui/status-badge";
import { formatRupiah } from "@/utils/currency";
import { BacktestOverview } from "./backtest-overview";

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
  return "caution" as const;
}

function Icon({ kind }: { kind: "list" | "up" | "down" | "target" | "edit" | "close" }) {
  const paths = {
    list: <><rect x="4" y="4" width="16" height="16" rx="2" /><path d="M8 9h8M8 13h8M8 17h5" /></>,
    up: <><path d="M4 17 10 11l4 3 6-7" /><path d="M15 7h5v5" /></>,
    down: <><path d="M4 7 10 13l4-3 6 7" /><path d="M15 17h5v-5" /></>,
    target: <><circle cx="12" cy="12" r="8" /><circle cx="12" cy="12" r="4" /><path d="m12 12 4-4" /></>,
    edit: <><path d="m4 16.5-.8 3.3 3.3-.8L18 7.5 15.5 5 4 16.5Z" /><path d="m14 6.5 2.5 2.5" /></>,
    close: <><path d="m6 6 12 12M18 6 6 18" /></>,
  };
  return <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" className="h-4 w-4" aria-hidden="true">{paths[kind]}</svg>;
}

function calculateSimulatedVerdict(testCase: BacktestCase, entryPrice: number): BacktestVerdict {
  const isUndervalued = testCase.consensus === "UNDERVALUED";
  const upsideTarget = entryPrice * (isUndervalued ? 1.2 : 1.15);
  const downsideTarget = entryPrice * (isUndervalued ? 0.8 : 0.9);
  const path = testCase.pricePath.filter((point) => point.date > testCase.analysisDate).sort((a, b) => a.date.localeCompare(b.date)).slice(0, 12);
  let upsideDate: string | null = null;
  let downsideDate: string | null = null;
  for (const point of path) {
    if (!upsideDate && point.high >= upsideTarget) upsideDate = point.date;
    if (!downsideDate && point.low <= downsideTarget) downsideDate = point.date;
    if (upsideDate || downsideDate) break;
  }
  if (!upsideDate && !downsideDate) return isUndervalued ? "FLAT" : "OBSERVE";
  if (upsideDate && (!downsideDate || upsideDate < downsideDate)) return isUndervalued ? "WIN" : "OBSERVE";
  return isUndervalued ? "RECOVERED" : "CONFIRMED";
}

function monthsBetween(startDate: string, endDate: string) {
  const start = new Date(`${startDate}T00:00:00Z`);
  const end = new Date(`${endDate}T00:00:00Z`);
  return (end.getUTCFullYear() - start.getUTCFullYear()) * 12 + end.getUTCMonth() - start.getUTCMonth();
}

function rangeAtHorizon(testCase: BacktestCase, horizon: number, analysisPrice: number) {
  const points = testCase.pricePath.filter((point) => point.date > testCase.analysisDate && monthsBetween(testCase.analysisDate, point.date) <= horizon);
  const point = points.find((candidate) => monthsBetween(testCase.analysisDate, candidate.date) === horizon) ?? points.sort((a, b) => a.date.localeCompare(b.date)).at(-1);
  if (!point) return { high: null, low: null, highReturn: null, lowReturn: null };
  const high = point.high;
  const low = point.low;
  return { high, low, highReturn: high / analysisPrice - 1, lowReturn: low / analysisPrice - 1 };
}

function closeAtHorizon(testCase: BacktestCase, horizon: number) {
  return testCase.pricePath.filter((point) => point.date > testCase.analysisDate && monthsBetween(testCase.analysisDate, point.date) <= horizon).sort((a, b) => b.date.localeCompare(a.date))[0]?.close ?? null;
}

function getDerivedData(testCase: BacktestCase, analysisPrice = testCase.analysisPrice) {
  const peak = testCase.pricePath.reduce<typeof testCase.pricePath[number] | null>((current, point) => !current || point.high > current.high ? point : current, null);
  const down = testCase.pricePath.reduce<typeof testCase.pricePath[number] | null>((current, point) => !current || point.low < current.low ? point : current, null);
  const ranges = [3, 6, 9, 12].map((horizon) => rangeAtHorizon(testCase, horizon, analysisPrice));
  return { ranges, returns: ranges.map((range) => range.highReturn), peakReturn: peak ? peak.high / analysisPrice - 1 : null, troughReturn: down ? down.low / analysisPrice - 1 : null, downPrice: down?.low ?? null, peakPrice: peak?.high ?? null, peakMonth: peak ? monthsBetween(testCase.analysisDate, peak.date) : null, troughMonth: down ? monthsBetween(testCase.analysisDate, down.date) : null };
}

function rangeText(range: ReturnType<typeof rangeAtHorizon>) {
  return <span className="inline-flex items-center gap-1.5"><span className="font-semibold text-[#3ef0a9]">▲ {percent(range.highReturn)}</span><span className="text-[#607086]">||</span><span className="font-semibold text-[#ff8b82]">▼ {percent(range.lowReturn)}</span></span>;
}

function priceRangeText(range: ReturnType<typeof rangeAtHorizon>) {
  return <span className="inline-flex items-center gap-1.5"><span className="font-semibold text-[#3ef0a9]">▲ {price(range.high)}</span><span className="text-[#607086]">||</span><span className="font-semibold text-[#ff8b82]">▼ {price(range.low)}</span></span>;
}

function methodValue(testCase: BacktestCase, method: string) {
  return testCase.methods.find((item) => item.method === method)?.intrinsicValue ?? null;
}

function undervaluedMethods(testCase: BacktestCase) {
  return `${testCase.methods.filter((item) => item.intrinsicValue !== null && item.intrinsicValue > testCase.analysisPrice).length}/${testCase.methods.length}`;
}

function consensusByMethod(testCase: BacktestCase, analysisPrice = testCase.analysisPrice): BacktestConsensus {
  const methodsAbovePrice = testCase.methods.filter((item) => item.intrinsicValue !== null && item.intrinsicValue > analysisPrice).length;
  return methodsAbovePrice >= 3 ? "UNDERVALUED" : "OVERVALUED";
}

function consensusByMos(testCase: BacktestCase): BacktestConsensus {
  return testCase.mosMain !== null && testCase.mosMain >= 0.3 ? "UNDERVALUED" : "OVERVALUED";
}

function consensusTooltip(kind: "method" | "mos") {
  return kind === "method"
    ? "Undervalued jika minimal 3 dari 5 metode menghasilkan intrinsic value di atas harga analisis. Selain itu overvalued."
    : "Undervalued jika MoS Main 30% atau lebih. Di bawah 30% berarti overvalued.";
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

function EditablePriceCell({ value: currentValue, isLoading, onCommit, alignRight = true }: { value: number; isLoading?: boolean; onCommit: (value: number) => void; alignRight?: boolean }) {
  const [isEditing, setIsEditing] = useState(false);
  const [draft, setDraft] = useState(String(currentValue));

  const startEditing = () => {
    setDraft(String(currentValue));
    setIsEditing(true);
  };

  const commit = () => {
    const nextValue = Number(draft.replace(/\D/g, ""));
    if (Number.isFinite(nextValue) && nextValue > 0) onCommit(nextValue);
    setIsEditing(false);
  };

  if (isLoading) {
    return <div className={`inline-flex items-center gap-2 text-[#f2d18f] ${alignRight ? "justify-end" : ""}`}><span className="h-3 w-3 animate-spin rounded-full border-2 border-[#f2d18f]/30 border-t-[#f2d18f]" aria-hidden="true" /><span className="text-[11px]">Loading...</span></div>;
  }

  if (isEditing) {
    return <div className="flex items-center gap-1"><input autoFocus value={draft} onChange={(event) => setDraft(event.target.value)} onKeyDown={(event) => { if (event.key === "Enter") commit(); if (event.key === "Escape") setIsEditing(false); }} inputMode="numeric" className="w-[92px] rounded-md border border-[#3892d0] bg-[#0b1929] px-2 py-1 text-xs text-white outline-none" aria-label="Edit harga analisis" /><button type="button" onClick={commit} className="rounded-md bg-[#3ef0a9]/15 px-1.5 py-1 text-[#3ef0a9] hover:bg-[#3ef0a9]/25" aria-label="Simpan harga analisis">✓</button></div>;
  }

  return <div className={`flex items-center gap-2 ${alignRight ? "justify-end" : ""}`}><span className="text-white">{price(currentValue)}</span><button type="button" onClick={startEditing} className="rounded-md border border-white/10 p-1 text-[#9aa9bf] hover:border-[#3892d0] hover:text-white" aria-label="Edit harga analisis"><Icon kind="edit" /></button></div>;
}

function SummaryCard({ label, value: cardValue, context, icon, tone = "text-white" }: { label: string; value: string; context: string; icon: "list" | "up" | "down" | "target"; tone?: string }) {
  return <article className="rounded-2xl border border-white/10 bg-[#081523]/80 p-4"><div className="flex items-center justify-between"><span className="text-xs text-[#aebbd0]">{label}</span><span className="flex h-8 w-8 items-center justify-center rounded-lg border border-[#3892d0]/30 bg-[#3892d0]/10 text-[#65b7ee]"><Icon kind={icon} /></span></div><div className={`mt-4 text-2xl font-semibold ${tone}`}>{cardValue}</div><div className="mt-1 text-[11px] text-[#8090a7]">{context}</div></article>;
}

function DetailDrawer({ testCase, onClose }: { testCase: BacktestCase; onClose: () => void }) {
  const [entry, setEntry] = useState(String(testCase.analysisPrice));
  const [appliedEntry, setAppliedEntry] = useState(testCase.analysisPrice);
  const simulatedVerdict = calculateSimulatedVerdict(testCase, appliedEntry);
  const entryPrice = Number(entry.replace(/\D/g, ""));
  return <div className="fixed inset-0 z-50 flex items-end justify-center bg-black/60 p-0 backdrop-blur-sm md:items-center md:p-6" role="dialog" aria-modal="true"><div className="max-h-[92vh] w-full max-w-5xl overflow-y-auto rounded-t-2xl border border-white/10 bg-[#081523] p-5 shadow-2xl md:rounded-2xl md:p-6"><div className="flex items-start justify-between gap-4"><div><div className="text-xs uppercase tracking-[0.14em] text-[#7f8fa6]">Historical Case Detail</div><h3 className="mt-1 text-xl font-semibold text-white">{testCase.ticker} · {testCase.quarter}</h3></div><button type="button" onClick={onClose} className="rounded-lg p-2 text-[#9aa9bf] hover:bg-white/5 hover:text-white" aria-label="Close detail"><Icon kind="close" /></button></div><div className="mt-5 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">{[["Sector", testCase.sector], ["Stock Type", testCase.stockType], ["Analysis Date", testCase.analysisDate], ["Original Analysis Price", price(testCase.analysisPrice)]].map(([label, cardValue]) => <div key={label} className="rounded-xl border border-white/8 bg-[#07111c]/70 p-3"><div className="text-[10px] text-[#7f8fa6]">{label}</div><div className="mt-1 text-sm font-semibold text-white">{cardValue}</div></div>)}</div><div className="mt-5 grid gap-4 lg:grid-cols-[1fr_1.2fr]"><div className="rounded-xl border border-white/8 bg-[#07111c]/70 p-4"><h4 className="text-sm font-semibold text-white">Your Entry Simulation</h4><p className="mt-2 text-xs leading-5 text-[#9aa9bf]">Original historical values stay unchanged. Only calculated comparisons use your entry price.</p><div className="mt-4 grid grid-cols-2 gap-3"><div><label className="text-[10px] text-[#7f8fa6]" htmlFor="entry-price">Your Entry Price</label><input id="entry-price" value={entry} onChange={(event) => setEntry(event.target.value)} inputMode="numeric" className="mt-1 w-full rounded-lg border border-white/10 bg-[#0b1929] px-3 py-2 text-sm text-white outline-none focus:border-[#3892d0]" /></div><div className="flex items-end"><button type="button" onClick={() => Number.isFinite(entryPrice) && entryPrice > 0 && setAppliedEntry(entryPrice)} className="w-full rounded-lg bg-[#3892d0] px-3 py-2 text-xs font-semibold text-white hover:bg-[#4ca5e4]">Apply</button></div></div><button type="button" onClick={() => { setEntry(String(testCase.analysisPrice)); setAppliedEntry(testCase.analysisPrice); }} className="mt-3 text-[11px] font-semibold text-[#65b7ee] hover:text-white">Reset to Analysis Price</button></div><div className="rounded-xl border border-white/8 bg-[#07111c]/70 p-4"><h4 className="text-sm font-semibold text-white">Case Classification</h4><div className="mt-3 grid grid-cols-2 gap-3 text-xs"><div><span className="text-[#7f8fa6]">Consensus</span><div className="mt-1"><StatusBadge tone={badgeTone(testCase.consensus)}>{testCase.consensus}</StatusBadge></div></div><div><span className="text-[#7f8fa6]">Historical Verdict</span><div className="mt-1"><StatusBadge tone={badgeTone(testCase.verdict)}>{testCase.verdict}</StatusBadge></div></div><div><span className="text-[#7f8fa6]">Simulated Verdict</span><div className="mt-1"><StatusBadge tone={badgeTone(simulatedVerdict)}>{simulatedVerdict}</StatusBadge></div></div></div><div className="mt-4 grid grid-cols-3 gap-3">{[["MoS Main", percent(testCase.mosMain)], ["MoS Peter", percent(testCase.mosPeter)], ["MoS Weight", percent(testCase.mosWeight)]].map(([label, cardValue]) => <div key={label}><div className="text-[10px] text-[#7f8fa6]">{label}</div><div className="mt-1 text-sm font-semibold text-[#f2d18f]">{cardValue}</div></div>)}</div></div></div></div></div>;
}

type DetailColumn = { key: string; label: React.ReactNode; width: string; group: string; render: (testCase: BacktestCase) => React.ReactNode };
const detailGroups = [
  { label: "IDENTITY", span: 5, className: "bg-[#1c3851] text-[#d8ecff]" },
  { label: "VALUATION", span: 10, className: "bg-[#1c3851] text-[#d8ecff]" },
  { label: "BUSINESS / FUNDAMENTAL SIGNALS", span: 8, className: "bg-[#1c3851] text-[#d8ecff]" },
  { label: "BACKTEST PRICE & RETURNS", span: 12, className: "bg-[#1c3851] text-[#d8ecff]" },
  { label: "VERDICT", span: 2, className: "bg-[#1c3851] text-[#d8ecff]" },
];

function DetailTable({ cases, prices, onSelect, onPriceChange }: { cases: BacktestCase[]; prices: Record<string, number>; onSelect: (testCase: BacktestCase) => void; onPriceChange: (id: string, value: number) => void }) {
  const columns: DetailColumn[] = [
    { key: "ticker", label: "Ticker", width: "w-[90px]", group: "IDENTITY", render: (item) => <span className="font-semibold text-white">{item.ticker}</span> },
    { key: "stockType", label: "Jenis Saham", width: "w-[130px]", group: "IDENTITY", render: (item) => item.stockType }, { key: "quarter", label: "Kuartal", width: "w-[110px]", group: "IDENTITY", render: (item) => <button type="button" onClick={() => onSelect(item)} className="font-semibold text-[#65b7ee] hover:text-white hover:underline">{item.quarter}</button> }, { key: "analysisDate", label: "TGL ANALISIS", width: "w-[125px]", group: "IDENTITY", render: (item) => item.analysisDate }, { key: "analysisPrice", label: "Harga Analisis", width: "w-[180px]", group: "IDENTITY", render: (item) => <EditablePriceCell value={prices[item.id] ?? item.analysisPrice} onCommit={(value) => onPriceChange(item.id, value)} /> },
    { key: "lynch", label: "IV Peter Lynch", width: "w-[125px]", group: "VALUATION", render: (item) => price(methodValue(item, "Peter Lynch / Adaptive")) }, { key: "sectorValue", label: "IV Type & Sector", width: "w-[125px]", group: "VALUATION", render: (item) => price(methodValue(item, "Type & Sector Weighted")) }, { key: "pbv", label: "IV Mean Reversion PBV", width: "w-[150px]", group: "VALUATION", render: (item) => price(methodValue(item, "Mean Reversion PBV")) }, { key: "ddm", label: "IV DDM", width: "w-[105px]", group: "VALUATION", render: (item) => price(methodValue(item, "Dividend Discount Model")) }, { key: "earnings", label: "IV Discounted Earnings", width: "w-[155px]", group: "VALUATION", render: (item) => price(methodValue(item, "Discounted Earnings")) }, { key: "methods", label: "Undervalued Methods", width: "w-[145px]", group: "VALUATION", render: (item) => undervaluedMethods(item) }, { key: "consensus", label: "Konsensus", width: "w-[125px]", group: "VALUATION", render: (item) => <StatusBadge tone={badgeTone(item.consensus)}>{item.consensus}</StatusBadge> }, { key: "mosMain", label: "MoS Main", width: "w-[105px]", group: "VALUATION", render: (item) => percent(item.mosMain) }, { key: "mosPeter", label: "MoS Peter", width: "w-[105px]", group: "VALUATION", render: (item) => percent(item.mosPeter) }, { key: "mosWeight", label: "MoS Weight", width: "w-[110px]", group: "VALUATION", render: (item) => percent(item.mosWeight) },
    { key: "yield", label: "Yield (%)", width: "w-[100px]", group: "BUSINESS", render: (item) => percent(item.context.yield) }, { key: "revenueYoY", label: "Revenue YoY", width: "w-[115px]", group: "BUSINESS", render: (item) => percent(item.context.revenueYoY) }, { key: "revPercent", label: "Rev %", width: "w-[90px]", group: "BUSINESS", render: (item) => percent(item.context.revenueYoY) }, { key: "netIncomeYoY", label: "Net Income YoY", width: "w-[135px]", group: "BUSINESS", render: (item) => percent(item.context.netIncomeYoY) }, { key: "niPercent", label: "NI %", width: "w-[90px]", group: "BUSINESS", render: (item) => percent(item.context.netIncomeYoY) }, { key: "epsMomentum", label: "EPS Momentum", width: "w-[125px]", group: "BUSINESS", render: (item) => item.context.epsMomentum }, { key: "revenueMomentum", label: "Revenue Momentum", width: "w-[145px]", group: "BUSINESS", render: (item) => item.context.revenueMomentum }, { key: "roeTrend", label: "ROE Trend", width: "w-[110px]", group: "BUSINESS", render: (item) => item.context.roeTrend },
    { key: "ret3m", label: "Ret 3M", width: "w-[100px]", group: "BACKTEST", render: (item) => percent(getDerivedData(item).returns[0]) }, { key: "ret6m", label: "Ret 6M", width: "w-[100px]", group: "BACKTEST", render: (item) => percent(getDerivedData(item).returns[1]) }, { key: "ret9m", label: "Ret 9M", width: "w-[100px]", group: "BACKTEST", render: (item) => percent(getDerivedData(item).returns[2]) }, { key: "ret12m", label: "Ret 12M", width: "w-[105px]", group: "BACKTEST", render: (item) => percent(getDerivedData(item).returns[3]) }, { key: "price3m", label: "Price 3M", width: "w-[115px]", group: "BACKTEST", render: (item) => price(closeAtHorizon(item, 3)) }, { key: "price6m", label: "Price 6M", width: "w-[115px]", group: "BACKTEST", render: (item) => price(closeAtHorizon(item, 6)) }, { key: "price9m", label: "Price 9M", width: "w-[115px]", group: "BACKTEST", render: (item) => price(closeAtHorizon(item, 9)) }, { key: "price12m", label: "Price 12M", width: "w-[120px]", group: "BACKTEST", render: (item) => price(closeAtHorizon(item, 12)) }, { key: "peakReturn", label: "Ret Peak", width: "w-[110px]", group: "BACKTEST", render: (item) => percent(getDerivedData(item).peakReturn) }, { key: "downPrice", label: "Harga Down", width: "w-[120px]", group: "BACKTEST", render: (item) => price(getDerivedData(item).downPrice) }, { key: "peakPrice", label: "Harga Peak", width: "w-[120px]", group: "BACKTEST", render: (item) => price(getDerivedData(item).peakPrice) }, { key: "peakMonth", label: "Bln Peak", width: "w-[100px]", group: "BACKTEST", render: (item) => { const month = getDerivedData(item).peakMonth; return month === null ? "N/A" : `${month} bln`; } },
    { key: "verdict", label: "Verdict by Method", width: "w-[145px]", group: "VERDICT", render: (item) => <StatusBadge tone={badgeTone(item.verdict)}>{item.verdict}</StatusBadge> }, { key: "verdictMos", label: "Verdict MoS Main", width: "w-[145px]", group: "VERDICT", render: (item) => <StatusBadge tone={badgeTone(item.verdictMos)}>{item.verdictMos}</StatusBadge> },
  ];
  return <div className="overflow-x-auto rounded-xl border border-white/8"><table className="w-max min-w-full border-collapse text-left text-xs"><thead className="bg-[#081523] text-[10px] uppercase tracking-wider text-[#7f8fa6]"><tr>{detailGroups.map((group) => <th key={group.label} colSpan={group.span} className={`border-r-2 border-b-2 border-[#07111c] px-3 py-3 text-left font-bold tracking-[0.12em] ${group.className}`}>{group.label}</th>)}</tr><tr>{columns.map((column, index) => <th key={column.key} className={`${column.width} whitespace-nowrap border-r border-white/10 px-3 py-3 ${index === 0 || columns[index - 1]?.group !== column.group ? "border-l-2 border-l-[#07111c] bg-white/[0.04]" : ""}`}>{column.label}</th>)}</tr></thead><tbody>{cases.map((item) => <tr key={item.id} className="border-t border-white/8 hover:bg-white/[0.02]">{columns.map((column, index) => <td key={column.key} className={`${column.width} whitespace-nowrap border-r border-white/8 px-3 py-3 text-[#b9c6d8] ${index === 0 || columns[index - 1]?.group !== column.group ? "border-l-2 border-l-[#07111c] bg-white/[0.015]" : ""}`}>{column.render(item)}</td>)}</tr>)}</tbody></table></div>;
}

function DetailTableV2({ cases, prices, loadingIds, onSelect, onPriceChange }: { cases: BacktestCase[]; prices: Record<string, number>; loadingIds: Set<string>; onSelect: (testCase: BacktestCase) => void; onPriceChange: (id: string, value: number) => void }) {
  const valueFor = (item: BacktestCase) => prices[item.id] ?? item.analysisPrice;
  const verdictHeaderClass = (key: string) => key === "verdict" ? "bg-[#182335] text-[#dbe8f7]" : key === "verdictMos" ? "bg-[#202936] text-[#e1e8f0]" : "";
  const verdictCellClass = (key: string) => key === "verdict" ? "bg-[#101f31] text-[#dbe8f7]" : key === "verdictMos" ? "bg-[#18212c] text-[#e1e8f0]" : "text-[#b9c6d8]";
  const columns: DetailColumn[] = [
    { key: "ticker", label: "Ticker", width: "w-[90px]", group: "IDENTITY", render: (item) => <span className="font-semibold text-white">{item.ticker}</span> },
    { key: "stockType", label: "Jenis Saham", width: "w-[130px]", group: "IDENTITY", render: (item) => item.stockType },
    { key: "quarter", label: "Kuartal", width: "w-[110px]", group: "IDENTITY", render: (item) => <span className="text-white">{item.quarter}</span> },
    { key: "analysisDate", label: "TGL ANALISIS", width: "w-[125px]", group: "IDENTITY", render: (item) => item.analysisDate },
    { key: "analysisPrice", label: "Harga Analisis", width: "w-[126px]", group: "IDENTITY", render: (item) => <EditablePriceCell value={valueFor(item)} isLoading={loadingIds.has(item.id)} onCommit={(value) => onPriceChange(item.id, value)} /> },
    { key: "lynch", label: "IV Peter Lynch", width: "w-[125px]", group: "VALUATION", render: (item) => price(methodValue(item, "Peter Lynch / Adaptive")) },
    { key: "sectorValue", label: "IV Type & Sector", width: "w-[125px]", group: "VALUATION", render: (item) => price(methodValue(item, "Type & Sector Weighted")) },
    { key: "pbv", label: "IV Mean Reversion PBV", width: "w-[150px]", group: "VALUATION", render: (item) => price(methodValue(item, "Mean Reversion PBV")) },
    { key: "ddm", label: "IV DIVIDEND DISCOUNT MODEL", width: "w-[205px]", group: "VALUATION", render: (item) => price(methodValue(item, "Dividend Discount Model")) },
    { key: "earnings", label: "IV Discounted Earnings", width: "w-[155px]", group: "VALUATION", render: (item) => price(methodValue(item, "Discounted Earnings")) },
    { key: "methods", label: "Undervalued Methods", width: "w-[145px]", group: "METHOD", render: (item) => undervaluedMethods(item) },
    { key: "consensusMethod", label: <TooltipLabel label="Konsensus by Method" tooltip={consensusTooltip("method")} />, width: "w-[165px]", group: "METHOD", render: (item) => { const consensus = consensusByMethod(item, valueFor(item)); return <StatusBadge tone={badgeTone(consensus)}>{consensus}</StatusBadge>; } },
    { key: "mosMain", label: "MoS Main", width: "w-[105px]", group: "VALUATION", render: (item) => percent(item.mosMain) },
    { key: "mosPeter", label: "MoS Peter", width: "w-[105px]", group: "VALUATION", render: (item) => percent(item.mosPeter) },
    { key: "mosWeight", label: "MoS Weight", width: "w-[110px]", group: "MOS", render: (item) => percent(item.mosWeight) },
    { key: "consensusMos", label: <TooltipLabel label="Konsensus by MoS" tooltip={consensusTooltip("mos")} />, width: "w-[165px]", group: "MOS", render: (item) => { const consensus = consensusByMos(item); return <StatusBadge tone={badgeTone(consensus)}>{consensus}</StatusBadge>; } },
    { key: "yield", label: "Yield (%)", width: "w-[100px]", group: "BUSINESS", render: (item) => percent(item.context.yield) },
    { key: "revenueYoY", label: "Revenue YoY", width: "w-[115px]", group: "BUSINESS", render: (item) => percent(item.context.revenueYoY) },
    { key: "revPercent", label: "Rev %", width: "w-[90px]", group: "BUSINESS", render: (item) => percent(item.context.revenueYoY) },
    { key: "netIncomeYoY", label: "Net Income YoY", width: "w-[135px]", group: "BUSINESS", render: (item) => percent(item.context.netIncomeYoY) },
    { key: "niPercent", label: "NI %", width: "w-[90px]", group: "BUSINESS", render: (item) => percent(item.context.netIncomeYoY) },
    { key: "epsMomentum", label: "EPS Momentum", width: "w-[125px]", group: "BUSINESS", render: (item) => item.context.epsMomentum },
    { key: "revenueMomentum", label: "Revenue Momentum", width: "w-[145px]", group: "BUSINESS", render: (item) => item.context.revenueMomentum },
    { key: "roeTrend", label: "ROE Trend", width: "w-[110px]", group: "BUSINESS", render: (item) => item.context.roeTrend },
    { key: "ret3m", label: "Ret 3M", width: "w-[190px]", group: "RETURNS", render: (item) => rangeText(getDerivedData(item, valueFor(item)).ranges[0]) },
    { key: "ret6m", label: "Ret 6M", width: "w-[190px]", group: "RETURNS", render: (item) => rangeText(getDerivedData(item, valueFor(item)).ranges[1]) },
    { key: "ret9m", label: "Ret 9M", width: "w-[190px]", group: "RETURNS", render: (item) => rangeText(getDerivedData(item, valueFor(item)).ranges[2]) },
    { key: "ret12m", label: "Ret 12M", width: "w-[200px]", group: "RETURNS", render: (item) => rangeText(getDerivedData(item, valueFor(item)).ranges[3]) },
    { key: "price3m", label: "Price 3M", width: "w-[190px]", group: "PRICES", render: (item) => priceRangeText(getDerivedData(item, valueFor(item)).ranges[0]) },
    { key: "price6m", label: "Price 6M", width: "w-[190px]", group: "PRICES", render: (item) => priceRangeText(getDerivedData(item, valueFor(item)).ranges[1]) },
    { key: "price9m", label: "Price 9M", width: "w-[190px]", group: "PRICES", render: (item) => priceRangeText(getDerivedData(item, valueFor(item)).ranges[2]) },
    { key: "price12m", label: "Price 12M", width: "w-[200px]", group: "PRICES", render: (item) => priceRangeText(getDerivedData(item, valueFor(item)).ranges[3]) },
    { key: "peakReturn", label: "Ret Peak", width: "w-[77px]", group: "PEAK / TROUGH", render: (item) => percent(getDerivedData(item, valueFor(item)).peakReturn) },
    { key: "peakPrice", label: "Harga Peak", width: "w-[84px]", group: "PEAK / TROUGH", render: (item) => price(getDerivedData(item, valueFor(item)).peakPrice) },
    { key: "peakMonth", label: "Bln Peak", width: "w-[100px]", group: "PEAK / TROUGH", render: (item) => { const month = getDerivedData(item, valueFor(item)).peakMonth; return month === null ? "N/A" : `${month} bln`; } },
    { key: "troughReturn", label: "Ret Trough", width: "w-[84px]", group: "PEAK / TROUGH", render: (item) => percent(getDerivedData(item, valueFor(item)).troughReturn) },
    { key: "downPrice", label: "Harga Trough", width: "w-[95px]", group: "PEAK / TROUGH", render: (item) => price(getDerivedData(item, valueFor(item)).downPrice) },
    { key: "troughMonth", label: "Bln Trough", width: "w-[110px]", group: "PEAK / TROUGH", render: (item) => { const month = getDerivedData(item, valueFor(item)).troughMonth; return month === null ? "N/A" : `${month} bln`; } },
    { key: "verdict", label: "Verdict by Method", width: "w-[145px]", group: "VERDICT", render: (item) => <span className="inline-flex rounded-md bg-[#101f31] px-2 py-1 text-[#dbe8f7]"><StatusBadge tone={badgeTone(item.verdict)}>{item.verdict}</StatusBadge></span> },
    { key: "verdictMos", label: "Verdict by MoS", width: "w-[145px]", group: "VERDICT", render: (item) => <span className="inline-flex rounded-md bg-[#18212c] px-2 py-1 text-[#e1e8f0]"><StatusBadge tone={badgeTone(item.verdictMos)}>{item.verdictMos}</StatusBadge></span> },
  ];
  const groups = [{ label: "IDENTITY", span: 5, className: "bg-[#1c3851] text-[#d8ecff]" }, { label: "VALUATION BY METHOD", span: 7, className: "bg-[#1c3851] text-[#d8ecff]" }, { label: "VALUATION BY MOS", span: 4, className: "bg-[#1c3851] text-[#d8ecff]" }, { label: "BUSINESS / FUNDAMENTAL SIGNALS", span: 8, className: "bg-[#1c3851] text-[#d8ecff]" }, { label: "RETURNS", span: 4, className: "bg-[#1c3851] text-[#d8ecff]" }, { label: "PRICES", span: 4, className: "bg-[#1c3851] text-[#d8ecff]" }, { label: "PEAK / TROUGH", span: 6, className: "bg-[#1c3851] text-[#d8ecff]" }, { label: "VERDICT", span: 2, className: "bg-[#1c3851] text-[#d8ecff]" }];
  const centeredValueColumns = ["ret3m", "ret6m", "ret9m", "ret12m", "price3m", "price6m", "price9m", "price12m"];
  return <div className="overflow-x-auto rounded-xl border border-white/8"><table className="w-max min-w-full border-collapse text-left text-xs"><thead className="bg-[#081523] text-[9px] uppercase tracking-wider text-[#7f8fa6]"><tr>{groups.map((group) => <th key={group.label} colSpan={group.span} className={`border-r-2 border-b-2 border-[#07111c] px-3 py-3 text-left align-top font-bold tracking-[0.12em] ${group.className}`}>{group.label}</th>)}</tr><tr>{columns.map((column, index) => <th key={column.key} className={`${column.width} whitespace-nowrap border-r border-white/10 px-3 py-3 text-left align-top ${index === 0 || columns[index - 1]?.group !== column.group ? "border-l-2 border-l-[#07111c] bg-white/[0.04]" : ""}`}>{column.label}</th>)}</tr></thead><tbody>{cases.map((item) => <tr key={item.id} aria-busy={loadingIds.has(item.id)} className={`border-t border-white/8 transition ${loadingIds.has(item.id) ? "pointer-events-none bg-[#f2bb5c]/10 opacity-60" : "hover:bg-white/[0.02]"}`}>{columns.map((column, index) => <td key={column.key} className={`${column.width} whitespace-nowrap border-r border-white/8 px-3 py-3 text-[#b9c6d8] ${centeredValueColumns.includes(column.key) ? "text-center" : ""} ${index === 0 || columns[index - 1]?.group !== column.group ? "border-l-2 border-l-[#07111c] bg-white/[0.015]" : ""}`}>{column.render(item)}</td>)}</tr>)}</tbody></table></div>;
}

function CompactTableLegacy({ cases, prices, loadingIds = new Set<string>(), onSelect, onPriceChange }: { cases: BacktestCase[]; prices: Record<string, number>; loadingIds?: Set<string>; onSelect: (testCase: BacktestCase) => void; onPriceChange: (id: string, value: number) => void }) {
  const headers = ["Ticker", "Kuartal", "TGL ANALISIS", "Harga Analisis", "Konsensus", "MoS Main", "MoS Weight", "Verdict by Method", "Verdict MoS Main"];
  return <div className="overflow-x-auto rounded-xl border border-white/8"><table className="w-full min-w-[980px] border-collapse text-left text-xs"><thead className="bg-[#081523] text-[10px] uppercase tracking-wider text-[#7f8fa6]"><tr>{headers.map((label) => <th key={label} className="whitespace-nowrap px-3 py-3">{label}</th>)}</tr></thead><tbody>{cases.map((item) => { const consensus = consensusByMethod(item, prices[item.id] ?? item.analysisPrice); return <tr key={item.id} className={`border-t border-white/8 hover:bg-white/[0.02] ${loadingIds.has(item.id) ? "bg-[#f2bb5c]/5 opacity-70" : ""}`}><td className="px-3 py-3 font-semibold text-white">{item.ticker}</td><td className="px-3 py-3"><button type="button" onClick={() => onSelect(item)} className="font-semibold text-[#65b7ee] hover:text-white hover:underline">{item.quarter}</button></td><td className="px-3 py-3 text-[#b9c6d8]">{item.analysisDate}</td><td className="px-3 py-3"><EditablePriceCell value={prices[item.id] ?? item.analysisPrice} isLoading={loadingIds.has(item.id)} onCommit={(value) => onPriceChange(item.id, value)} /></td><td className="px-3 py-3"><StatusBadge tone={badgeTone(consensus)}>{consensus}</StatusBadge></td><td className="px-3 py-3 text-[#f2d18f]">{percent(item.mosMain)}</td><td className="px-3 py-3 text-[#f2d18f]">{percent(item.mosWeight)}</td><td className="px-3 py-3"><StatusBadge tone={badgeTone(item.verdict)}>{item.verdict}</StatusBadge></td><td className="px-3 py-3"><StatusBadge tone={badgeTone(item.verdictMos)}>{item.verdictMos}</StatusBadge></td></tr>; })}</tbody></table></div>;
}

function CompactTableLegacy2({ cases, prices, loadingIds = new Set<string>(), onSelect, onPriceChange }: { cases: BacktestCase[]; prices: Record<string, number>; loadingIds?: Set<string>; onSelect: (testCase: BacktestCase) => void; onPriceChange: (id: string, value: number) => void }) {
  const headers = ["Jenis Saham", "Kuartal", "TGL ANALISIS", "Harga Analisis", "Undervalued Methods", "Konsensus by Method", "MoS Main", "Konsensus by MoS", "Ret Peak", "Ret Down", "Verdict by Method", "Verdict by MoS"];
  return <div className="overflow-x-auto rounded-xl border border-white/8"><table className="w-max min-w-[1500px] border-collapse text-left text-xs"><thead className="bg-[#081523] text-[10px] uppercase tracking-wider text-[#7f8fa6]"><tr>{headers.map((label) => <th key={label} className="whitespace-nowrap border-r border-white/8 px-3 py-3">{label === "Konsensus by Method" ? <TooltipLabel label={label} tooltip={consensusTooltip("method")} /> : label === "Konsensus by MoS" ? <TooltipLabel label={label} tooltip={consensusTooltip("mos")} /> : label}</th>)}</tr></thead><tbody>{cases.map((item) => { const analysisPrice = prices[item.id] ?? item.analysisPrice; const derived = getDerivedData(item, analysisPrice); const methodConsensus = consensusByMethod(item, analysisPrice); const mosConsensus = consensusByMos(item); const isLoading = loadingIds.has(item.id); return <tr key={item.id} aria-busy={isLoading} className={`border-t border-white/8 transition ${isLoading ? "pointer-events-none bg-[#f2bb5c]/10 opacity-60" : "hover:bg-white/[0.02]"}`}><td className="whitespace-nowrap border-r border-white/8 px-3 py-3 text-[#b9c6d8]">{item.stockType}</td><td className="whitespace-nowrap border-r border-white/8 px-3 py-3"><button type="button" onClick={() => onSelect(item)} className="text-[#65b7ee] hover:text-white hover:underline">{item.quarter}</button></td><td className="whitespace-nowrap border-r border-white/8 px-3 py-3 text-[#b9c6d8]">{item.analysisDate}</td><td className="whitespace-nowrap border-r border-white/8 px-3 py-3"><EditablePriceCell value={analysisPrice} isLoading={isLoading} onCommit={(value) => onPriceChange(item.id, value)} /></td><td className="whitespace-nowrap border-r border-white/8 px-3 py-3 text-[#b9c6d8]">{undervaluedMethods(item)}</td><td className="whitespace-nowrap border-r border-white/8 px-3 py-3"><StatusBadge tone={badgeTone(methodConsensus)}>{methodConsensus}</StatusBadge></td><td className="whitespace-nowrap border-r border-white/8 px-3 py-3 text-[#f2d18f]">{percent(item.mosMain)}</td><td className="whitespace-nowrap border-r border-white/8 px-3 py-3"><StatusBadge tone={badgeTone(mosConsensus)}>{mosConsensus}</StatusBadge></td><td className="whitespace-nowrap border-r border-white/8 px-3 py-3 text-[#3ef0a9]">{percent(derived.peakReturn)}</td><td className="whitespace-nowrap border-r border-white/8 px-3 py-3 text-[#ff8b82]">{percent(derived.troughReturn)}</td><td className="whitespace-nowrap border-r border-white/8 px-3 py-3"><StatusBadge tone={badgeTone(item.verdict)}>{item.verdict}</StatusBadge></td><td className="whitespace-nowrap border-r border-white/8 px-3 py-3"><StatusBadge tone={badgeTone(item.verdictMos)}>{item.verdictMos}</StatusBadge></td></tr>; })}</tbody></table></div>;
}

function CompactTable({ cases, prices, loadingIds = new Set<string>(), onSelect, onPriceChange: _onPriceChange }: { cases: BacktestCase[]; prices: Record<string, number>; loadingIds?: Set<string>; onSelect: (testCase: BacktestCase) => void; onPriceChange: (id: string, value: number) => void }) {
  const columns = [
    { key: "stockType", label: "Jenis Saham", width: "w-[7%]" },
    { key: "quarter", label: "Kuartal", width: "w-[6%]" },
    { key: "analysisDate", label: "TGL ANALISIS", width: "w-[8%]" },
    { key: "analysisPrice", label: "Harga Analisis", width: "w-[8%]" },
    { key: "methods", label: "Undervalued Methods", width: "w-[8%]" },
    { key: "methodConsensus", label: "Konsensus by Method", width: "w-[11%]" },
    { key: "mosMain", label: "MoS Main", width: "w-[6%]" },
    { key: "mosConsensus", label: "Konsensus by MoS", width: "w-[10%]" },
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

  return <div className="w-full overflow-hidden rounded-xl border border-white/8"><table className="w-full table-fixed border-collapse text-left text-[10px] leading-tight min-[1441px]:text-xs"><thead className="bg-[#081523] text-[8px] uppercase tracking-wider text-[#7f8fa6] min-[1441px]:text-[9px]"><tr>{compactGroups.map((group) => <th key={group.label} colSpan={group.span} className={`border-r-2 border-b-2 border-[#07111c] px-1.5 py-2 text-left align-top font-bold tracking-[0.1em] min-[1441px]:px-2 min-[1441px]:py-2.5 ${group.className}`}>{group.label}</th>)}</tr><tr>{columns.map((column) => <th key={column.key} className={`${column.width} whitespace-normal break-words border-r border-white/8 px-1.5 py-2 text-left align-top min-[1441px]:px-2 min-[1441px]:py-2.5 ${column.key === "verdict" ? "bg-[#182335] text-[#dbe8f7]" : column.key === "verdictMos" ? "bg-[#202936] text-[#e1e8f0]" : ""}`}>{column.key === "methodConsensus" ? <TooltipLabel label={column.label} tooltip={consensusTooltip("method")} /> : column.key === "mosConsensus" ? <TooltipLabel label={column.label} tooltip={consensusTooltip("mos")} /> : column.label}</th>)}</tr></thead><tbody>{cases.map((item) => { const analysisPrice = prices[item.id] ?? item.analysisPrice; const derived = getDerivedData(item, analysisPrice); const methodConsensus = consensusByMethod(item, analysisPrice); const mosConsensus = consensusByMos(item); const isLoading = loadingIds.has(item.id); return <tr key={item.id} aria-busy={isLoading} className={`border-t border-white/8 transition ${isLoading ? "pointer-events-none bg-[#f2bb5c]/10 opacity-60" : "hover:bg-white/[0.02]"}`}><td className="break-words border-r border-white/8 px-1.5 py-2 text-[#b9c6d8] min-[1441px]:px-2 min-[1441px]:py-2.5">{item.stockType}</td><td className="break-words border-r border-white/8 px-1.5 py-2 min-[1441px]:px-2 min-[1441px]:py-2.5"><button type="button" onClick={() => onSelect(item)} className="break-words text-[#65b7ee] hover:text-white hover:underline">{item.quarter}</button></td><td className="break-words border-r border-white/8 px-1.5 py-2 text-[#b9c6d8] min-[1441px]:px-2 min-[1441px]:py-2.5">{item.analysisDate}</td><td className="break-words border-r border-white/8 px-1.5 py-2 text-right text-white min-[1441px]:px-2 min-[1441px]:py-2.5">{price(analysisPrice)}</td><td className="break-words border-r border-white/8 px-1.5 py-2 text-center text-[#b9c6d8] min-[1441px]:px-2 min-[1441px]:py-2.5">{undervaluedMethods(item)}</td><td className="break-words border-r border-white/8 px-1.5 py-2 min-[1441px]:px-2 min-[1441px]:py-2.5"><StatusBadge className="whitespace-normal break-words px-1 py-0.5 text-[8px] leading-3 min-[1441px]:px-1.5 min-[1441px]:py-1 min-[1441px]:text-[9px]" tone={badgeTone(methodConsensus)}>{methodConsensus}</StatusBadge></td><td className="break-words border-r border-white/8 px-1.5 py-2 text-right text-[#f2d18f] min-[1441px]:px-2 min-[1441px]:py-2.5">{percent(item.mosMain)}</td><td className="break-words border-r border-white/8 px-1.5 py-2 min-[1441px]:px-2 min-[1441px]:py-2.5"><StatusBadge className="whitespace-normal break-words px-1 py-0.5 text-[8px] leading-3 min-[1441px]:px-1.5 min-[1441px]:py-1 min-[1441px]:text-[9px]" tone={badgeTone(mosConsensus)}>{mosConsensus}</StatusBadge></td><td className="break-words border-r border-white/8 px-1.5 py-2 text-right text-[#3ef0a9] min-[1441px]:px-2 min-[1441px]:py-2.5">{percent(derived.peakReturn)}</td><td className="break-words border-r border-white/8 px-1.5 py-2 text-right text-[#ff8b82] min-[1441px]:px-2 min-[1441px]:py-2.5">{percent(derived.troughReturn)}</td><td className="break-words border-l border-r border-[#26384d] bg-[#101f31] px-1.5 py-2 min-[1441px]:px-2 min-[1441px]:py-2.5"><StatusBadge className="whitespace-normal break-words px-1 py-0.5 text-[8px] leading-3 min-[1441px]:px-1.5 min-[1441px]:py-1 min-[1441px]:text-[9px]" tone={badgeTone(item.verdict)}>{item.verdict}</StatusBadge></td><td className="break-words border-l border-[#34404e] bg-[#18212c] px-1.5 py-2 min-[1441px]:px-2 min-[1441px]:py-2.5"><StatusBadge className="whitespace-normal break-words px-1 py-0.5 text-[8px] leading-3 min-[1441px]:px-1.5 min-[1441px]:py-1 min-[1441px]:text-[9px]" tone={badgeTone(item.verdictMos)}>{item.verdictMos}</StatusBadge></td></tr>; })}</tbody></table></div>;
}

export function BacktestTabContent({ stock }: { stock: StockDetail }) {
  const [view, setView] = useState<ViewMode>("compact");
  const [selectedCase, setSelectedCase] = useState<BacktestCase | null>(null);
  const [analysisPrices, setAnalysisPrices] = useState<Record<string, number>>({});
  const [loadingPriceIds, setLoadingPriceIds] = useState<Set<string>>(new Set());
  const cases = useMemo(() => stock.backtest?.cases ?? [], [stock.backtest?.cases]);
  const updateAnalysisPrice = (id: string, nextValue: number) => {
    setLoadingPriceIds((current) => new Set(current).add(id));
    window.setTimeout(() => {
      setAnalysisPrices((current) => ({ ...current, [id]: nextValue }));
      setLoadingPriceIds((current) => { const next = new Set(current); next.delete(id); return next; });
    }, 700);
  };
  return <div className="space-y-6"><header><h2 className="text-3xl font-bold tracking-tight text-white">Backtest</h2><p className="mt-1 text-sm text-[#aeb9ca]">See how the valuation framework would have performed across historical cases.</p></header><BacktestOverview cases={cases} analysisPrices={analysisPrices} /><SectionCard title="Historical Cases" subtitle="List of historical valuation cases. Click a quarter to see the case detail." actionSlot={<div className="flex items-center gap-1 self-start rounded-xl border border-white/10 bg-[#091322]/80 p-1 text-xs"><button type="button" onClick={() => setView("compact")} className={`rounded-lg px-4 py-1.5 font-semibold transition ${view === "compact" ? "bg-[#f2bb5c] text-[#1d170f]" : "text-[#9aa9bf] hover:bg-white/5 hover:text-white"}`}>Compact View</button><button type="button" onClick={() => setView("detail")} className={`rounded-lg px-4 py-1.5 font-semibold transition ${view === "detail" ? "bg-[#f2bb5c] text-[#1d170f]" : "text-[#9aa9bf] hover:bg-white/5 hover:text-white"}`}>Detail View</button></div>}>{cases.length === 0 ? <div className="p-10 text-center text-sm text-[#9aa9bf]">No historical backtest cases are available for {stock.ticker} yet.</div> : view === "compact" ? <CompactTable cases={cases} prices={analysisPrices} onSelect={setSelectedCase} onPriceChange={updateAnalysisPrice} /> : <DetailTableV2 cases={cases} prices={analysisPrices} loadingIds={loadingPriceIds} onSelect={setSelectedCase} onPriceChange={updateAnalysisPrice} />}</SectionCard><SectionCard title="How the Backtest Works" subtitle="A simple and transparent process to evaluate historical outcomes."><div className="grid gap-4 lg:grid-cols-3"><Step number="01" title="Identify the Condition" text="Each historical quarter is classified as Undervalued, Overvalued, or Mixed using the valuation framework available on the analysis date." /><Step number="02" title="Track Price Movement" text="After the analysis date, price movement is observed for up to 12 months against predefined upside and downside thresholds." /><Step number="03" title="Determine the Outcome" text="The first threshold reached determines the historical outcome. This is evidence of past behavior, not a prediction or recommendation." /></div></SectionCard>{selectedCase && <DetailDrawer testCase={selectedCase} onClose={() => setSelectedCase(null)} />}</div>;
}

function Step({ number, title, text }: { number: string; title: string; text: string }) { return <article className="relative rounded-xl border border-white/8 bg-[#081523]/75 p-4"><div className="flex h-8 w-8 items-center justify-center rounded-lg border border-[#3892d0]/30 bg-[#3892d0]/10 text-xs font-bold text-[#65b7ee]">{number}</div><h4 className="mt-4 text-sm font-semibold text-white">{title}</h4><p className="mt-2 text-xs leading-5 text-[#9aa9bf]">{text}</p></article>; }
