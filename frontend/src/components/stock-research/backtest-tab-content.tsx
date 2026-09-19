"use client";

import React, { useMemo, useState } from "react";
import type { BacktestCase, BacktestConsensus, BacktestVerdict, StockDetail } from "@/data/mock-stock-details";
import { SectionCard } from "@/components/ui/section-card";
import { StatusBadge } from "@/components/ui/status-badge";
import { formatRupiah } from "@/utils/currency";

type ViewMode = "compact" | "detail";

const numberFormat = new Intl.NumberFormat("id-ID", { maximumFractionDigits: 2 });

function percent(value: number | null) {
  return value === null || !Number.isFinite(value) ? "N/A" : `${numberFormat.format(value * 100)}%`;
}

function price(value: number | null) {
  return value === null || !Number.isFinite(value) ? "N/A" : formatRupiah(value);
}

function badgeTone(value: BacktestConsensus | BacktestVerdict) {
  if (value === "UNDERVALUED" || value === "WIN" || value === "RECOVERED") return "positive" as const;
  if (value === "OVERVALUED" || value === "RISK" || value === "CONFIRMED") return "overvalued" as const;
  if (value === "MIXED" || value === "FLAT" || value === "OBSERVE") return "stable" as const;
  return "caution" as const;
}

function Icon({ kind }: { kind: "chart" | "list" | "up" | "down" | "target" | "book" | "edit" | "close" | "info" }) {
  const paths = {
    chart: <><path d="M4 19V5M4 19h16" /><path d="m7 15 3-4 3 2 5-7" /></>,
    list: <><rect x="4" y="4" width="16" height="16" rx="2" /><path d="M8 9h8M8 13h8M8 17h5" /></>,
    up: <><path d="M4 17 10 11l4 3 6-7" /><path d="M15 7h5v5" /></>,
    down: <><path d="M4 7 10 13l4-3 6 7" /><path d="M15 17h5v-5" /></>,
    target: <><circle cx="12" cy="12" r="8" /><circle cx="12" cy="12" r="4" /><path d="m12 12 4-4" /></>,
    book: <><path d="M4 5.5A2.5 2.5 0 0 1 6.5 3H20v16H6.5A2.5 2.5 0 0 0 4 21.5v-16Z" /><path d="M4 5.5v16M8 7h8M8 11h8" /></>,
    edit: <><path d="m4 16.5-.8 3.3 3.3-.8L18 7.5 15.5 5 4 16.5Z" /><path d="m14 6.5 2.5 2.5" /></>,
    close: <><path d="m6 6 12 12M18 6 6 18" /></>,
    info: <><circle cx="12" cy="12" r="9" /><path d="M12 11v5M12 8h.01" /></>,
  };
  return <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" className="h-4 w-4" aria-hidden="true">{paths[kind]}</svg>;
}

function calculateSimulatedVerdict(testCase: BacktestCase, entryPrice: number): BacktestVerdict {
  const isUndervalued = testCase.consensus === "UNDERVALUED";
  const upsideTarget = entryPrice * (isUndervalued ? 1.2 : 1.15);
  const downsideTarget = entryPrice * (isUndervalued ? 0.8 : 0.9);
  const path = testCase.pricePath.filter(point => point.date > testCase.analysisDate).slice(0, 12);
  let upsideDate: string | null = null;
  let downsideDate: string | null = null;
  for (const point of path) {
    if (!upsideDate && point.high >= upsideTarget) upsideDate = point.date;
    if (!downsideDate && point.low <= downsideTarget) downsideDate = point.date;
    if (upsideDate || downsideDate) break;
  }
  if (!upsideDate && !downsideDate) return isUndervalued ? "FLAT" : "OBSERVE";
  if (upsideDate && (!downsideDate || upsideDate < downsideDate)) return isUndervalued ? "WIN" : "MARKET SURPRISE";
  const laterUpside = path.some(point => point.high >= upsideTarget);
  return isUndervalued && laterUpside ? "RECOVERED" : isUndervalued ? "RISK" : "CONFIRMED";
}

function SummaryCard({ label, value, context, icon, tone = "text-white" }: { label: string; value: string; context: string; icon: "list" | "up" | "down" | "target"; tone?: string }) {
  return <article className="rounded-2xl border border-white/10 bg-[#081523]/80 p-4"><div className="flex items-center justify-between"><span className="text-xs text-[#aebbd0]">{label}</span><span className="flex h-8 w-8 items-center justify-center rounded-lg border border-[#3892d0]/30 bg-[#3892d0]/10 text-[#65b7ee]"><Icon kind={icon} /></span></div><div className={`mt-4 text-2xl font-semibold ${tone}`}>{value}</div><div className="mt-1 text-[11px] text-[#8090a7]">{context}</div></article>;
}

function DetailDrawer({ testCase, onClose }: { testCase: BacktestCase; onClose: () => void }) {
  const [entry, setEntry] = useState(String(testCase.analysisPrice));
  const [appliedEntry, setAppliedEntry] = useState(testCase.analysisPrice);
  const entryPrice = Number(entry.replace(/\D/g, ""));
  const simulatedVerdict = calculateSimulatedVerdict(testCase, appliedEntry);
  return <div className="fixed inset-0 z-50 flex items-end justify-center bg-black/60 p-0 backdrop-blur-sm md:items-center md:p-6" role="dialog" aria-modal="true">
    <div className="max-h-[92vh] w-full max-w-5xl overflow-y-auto rounded-t-2xl border border-white/10 bg-[#081523] p-5 shadow-2xl md:rounded-2xl md:p-6">
      <div className="flex items-start justify-between gap-4"><div><div className="text-xs uppercase tracking-[0.14em] text-[#7f8fa6]">Historical Case Detail</div><h3 className="mt-1 text-xl font-semibold text-white">{testCase.ticker} · {testCase.quarter}</h3></div><button type="button" onClick={onClose} className="rounded-lg p-2 text-[#9aa9bf] hover:bg-white/5 hover:text-white" aria-label="Close detail"><Icon kind="close" /></button></div>
      <div className="mt-5 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">{[["Sector", testCase.sector], ["Stock Type", testCase.stockType], ["Analysis Date", testCase.analysisDate], ["Original Analysis Price", price(testCase.analysisPrice)]].map(([label, value]) => <div key={label} className="rounded-xl border border-white/8 bg-[#07111c]/70 p-3"><div className="text-[10px] text-[#7f8fa6]">{label}</div><div className="mt-1 text-sm font-semibold text-white">{value}</div></div>)}</div>
      <div className="mt-5 grid gap-4 lg:grid-cols-[1fr_1.2fr]"><div className="rounded-xl border border-white/8 bg-[#07111c]/70 p-4"><div className="flex items-center justify-between"><h4 className="text-sm font-semibold text-white">Your Entry Simulation</h4><span className="text-[#f2bb5c]"><Icon kind="edit" /></span></div><p className="mt-2 text-xs leading-5 text-[#9aa9bf]">Original historical values stay unchanged. Only calculated comparisons use your entry price.</p><div className="mt-4 grid grid-cols-2 gap-3"><div><label className="text-[10px] text-[#7f8fa6]" htmlFor="entry-price">Your Entry Price</label><input id="entry-price" value={entry} onChange={event => setEntry(event.target.value)} inputMode="numeric" className="mt-1 w-full rounded-lg border border-white/10 bg-[#0b1929] px-3 py-2 text-sm text-white outline-none focus:border-[#3892d0]" /></div><div className="flex items-end"><button type="button" onClick={() => Number.isFinite(entryPrice) && entryPrice > 0 && setAppliedEntry(entryPrice)} className="w-full rounded-lg bg-[#3892d0] px-3 py-2 text-xs font-semibold text-white hover:bg-[#4ca5e4]">Apply</button></div></div><button type="button" onClick={() => { setEntry(String(testCase.analysisPrice)); setAppliedEntry(testCase.analysisPrice); }} className="mt-3 text-[11px] font-semibold text-[#65b7ee] hover:text-white">Reset to Analysis Price</button><div className="mt-4 grid grid-cols-2 gap-3 border-t border-white/8 pt-4"><div><div className="text-[10px] text-[#7f8fa6]">Historical Verdict</div><div className="mt-1"><StatusBadge tone={badgeTone(testCase.verdict)}>{testCase.verdict}</StatusBadge></div></div><div><div className="text-[10px] text-[#7f8fa6]">Simulated Verdict</div><div className="mt-1"><StatusBadge tone={badgeTone(simulatedVerdict)}>{simulatedVerdict}</StatusBadge></div></div></div></div><div className="rounded-xl border border-white/8 bg-[#07111c]/70 p-4"><h4 className="text-sm font-semibold text-white">Case Classification</h4><div className="mt-3 grid grid-cols-2 gap-3 text-xs"><div><span className="text-[#7f8fa6]">Consensus</span><div className="mt-1"><StatusBadge tone={badgeTone(testCase.consensus)}>{testCase.consensus}</StatusBadge></div></div><div><span className="text-[#7f8fa6]">Verdict MoS</span><div className="mt-1"><StatusBadge tone={badgeTone(testCase.verdictMos)}>{testCase.verdictMos}</StatusBadge></div></div></div><div className="mt-4 grid grid-cols-3 gap-3">{[["MoS Main", percent(testCase.mosMain)], ["MoS Peter", percent(testCase.mosPeter)], ["MoS Weight", percent(testCase.mosWeight)]].map(([label, value]) => <div key={label}><div className="text-[10px] text-[#7f8fa6]">{label}</div><div className="mt-1 text-sm font-semibold text-[#f2d18f]">{value}</div></div>)}</div></div></div>
      <div className="mt-5 overflow-x-auto rounded-xl border border-white/8"><table className="w-full min-w-[700px] text-left text-xs"><thead className="bg-[#0b1929] text-[10px] uppercase tracking-wider text-[#7f8fa6]"><tr><th className="px-3 py-3">Method</th><th className="px-3 py-3">Intrinsic Value</th><th className="px-3 py-3">MoS @ Analysis Price</th><th className="px-3 py-3">MoS @ Your Entry</th></tr></thead><tbody>{testCase.methods.map(method => <tr key={method.method} className="border-t border-white/8"><td className="px-3 py-3 font-medium text-white">{method.method}</td><td className="px-3 py-3 text-[#f2d18f]">{price(method.intrinsicValue)}</td><td className="px-3 py-3 text-[#9aa9bf]">{method.intrinsicValue === null ? "N/A" : percent(1 - testCase.analysisPrice / method.intrinsicValue)}</td><td className="px-3 py-3 font-semibold text-[#3ef0a9]">{method.intrinsicValue === null ? "N/A" : percent(1 - appliedEntry / method.intrinsicValue)}</td></tr>)}</tbody></table></div>
      <div className="mt-5 grid gap-3 sm:grid-cols-3 lg:grid-cols-7">{[["Revenue YoY", percent(testCase.context.revenueYoY)], ["Net Income YoY", percent(testCase.context.netIncomeYoY)], ["EPS Momentum", testCase.context.epsMomentum], ["Revenue Momentum", testCase.context.revenueMomentum], ["ROE Trend", testCase.context.roeTrend], ["Yield", percent(testCase.context.yield)], ["OCF / NI", testCase.context.ocfNi === null ? "N/A" : `${numberFormat.format(testCase.context.ocfNi)}x`]].map(([label, value]) => <div key={label} className="rounded-lg bg-[#07111c]/70 p-2.5"><div className="text-[10px] text-[#7f8fa6]">{label}</div><div className="mt-1 text-xs font-semibold text-white">{value}</div></div>)}</div>
    </div>
  </div>;
}

export function BacktestTabContent({ stock }: { stock: StockDetail }) {
  const [view, setView] = useState<ViewMode>("compact");
  const [selectedCase, setSelectedCase] = useState<BacktestCase | null>(null);
  const cases = useMemo(() => stock.backtest?.cases ?? [], [stock.backtest?.cases]);
  const summary = useMemo(() => {
    const total = cases.length;
    const undervalued = cases.filter(item => item.consensus === "UNDERVALUED").length;
    const overvalued = cases.filter(item => item.consensus !== "UNDERVALUED").length;
    const upside = cases.filter(item => item.verdict === "WIN" || item.verdict === "RECOVERED").length;
    return { total, undervalued, overvalued, upside };
  }, [cases]);
  const [showHelp, setShowHelp] = useState(false);
  return <div className="space-y-6"><header className="relative flex flex-col justify-between gap-4 md:flex-row md:items-end"><div><div className="flex items-center gap-2"><span className="flex h-8 w-8 items-center justify-center rounded-lg border border-[#d6a24d]/40 bg-[#f2bb5c]/10 text-[#f2bb5c]"><Icon kind="chart" /></span><div><h2 className="text-3xl font-bold tracking-tight text-white">Backtest</h2><p className="mt-1 text-sm text-[#aeb9ca]">See how the valuation framework would have performed across historical cases.</p></div></div></div><button type="button" onClick={() => setShowHelp(value => !value)} aria-expanded={showHelp} className="inline-flex items-center gap-2 self-start rounded-lg border border-white/10 bg-[#081523] px-3 py-2 text-xs font-semibold text-[#b9c6d8] hover:border-[#3892d0]/50 hover:text-white"><Icon kind="info" />How to read this page?</button>{showHelp && <div className="absolute right-0 top-full z-10 mt-2 max-w-sm rounded-xl border border-[#3892d0]/30 bg-[#0b1929] p-4 text-xs leading-5 text-[#b9c6d8] shadow-xl">Backtest shows historical cases only. The original analysis price and verdict never change; Your Entry Simulation recalculates margin of safety and outcome using your input price.</div>}</header>
    <SectionCard icon={<Icon kind="chart" />} title="Backtest Overview" subtitle="Summary of historical cases based on the valuation framework."><div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4"><SummaryCard label="Total Cases" value={String(summary.total)} context="Analyzed quarters" icon="list" /><SummaryCard label="Undervalued Cases" value={summary.total ? percent(summary.undervalued / summary.total) : "N/A"} context={`${summary.undervalued} of ${summary.total} cases`} icon="up" tone="text-[#3ef0a9]" /><SummaryCard label="Overvalued / Mixed Cases" value={summary.total ? percent(summary.overvalued / summary.total) : "N/A"} context={`${summary.overvalued} of ${summary.total} cases`} icon="down" tone="text-[#ff8b82]" /><SummaryCard label="Cases with +20% Upside" value={summary.total ? percent(summary.upside / summary.total) : "N/A"} context={`${summary.upside} of ${summary.total} cases`} icon="target" tone="text-[#f2d18f]" /></div></SectionCard>
    <SectionCard icon={<Icon kind="list" />} title="Historical Cases" subtitle="List of historical valuation cases. Click a quarter to see details or edit the price to simulate your entry." actionSlot={<div className="flex items-center gap-1 rounded-lg border border-white/10 bg-[#07111c] p-1"><button type="button" onClick={() => setView("compact")} className={`rounded-md px-2.5 py-1.5 text-[11px] font-semibold ${view === "compact" ? "bg-[#3892d0] text-white" : "text-[#8e9bb0]"}`}>Compact View</button><button type="button" onClick={() => setView("detail")} className={`rounded-md px-2.5 py-1.5 text-[11px] font-semibold ${view === "detail" ? "bg-[#3892d0] text-white" : "text-[#8e9bb0]"}`}>Detail View</button></div>}><div className="overflow-x-auto rounded-xl border border-white/8">{cases.length === 0 ? <div className="p-10 text-center text-sm text-[#9aa9bf]">No historical backtest cases are available for {stock.ticker} yet.</div> : <table className="w-full min-w-[980px] border-collapse text-left text-xs"><thead className="bg-[#081523] text-[10px] uppercase tracking-wider text-[#7f8fa6]"><tr>{(view === "compact" ? ["Ticker", "Quarter", "Analysis Price", "Consensus", "MoS Main", "MoS Weight", "Verdict", "Verdict MoS", "Actions"] : ["Ticker", "Quarter", "Analysis Date", "Sector", "Stock Type", "Analysis Price", "Consensus", "MoS Main", "MoS Peter", "MoS Weight", "Verdict", "Verdict MoS", "Actions"]).map(title => <th key={title} className="px-3 py-3">{title}</th>)}</tr></thead><tbody>{cases.map(item => <tr key={item.id} className="border-t border-white/8 hover:bg-white/[0.02]">{view === "compact" ? <><td className="px-3 py-3 font-semibold text-white">{item.ticker}</td><td className="px-3 py-3"><button type="button" onClick={() => setSelectedCase(item)} className="font-semibold text-[#65b7ee] hover:text-white hover:underline">{item.quarter}</button></td><td className="px-3 py-3 text-white">{price(item.analysisPrice)}</td><td className="px-3 py-3"><StatusBadge tone={badgeTone(item.consensus)}>{item.consensus}</StatusBadge></td><td className="px-3 py-3 text-[#f2d18f]">{percent(item.mosMain)}</td><td className="px-3 py-3 text-[#f2d18f]">{percent(item.mosWeight)}</td><td className="px-3 py-3"><StatusBadge tone={badgeTone(item.verdict)}>{item.verdict}</StatusBadge></td><td className="px-3 py-3"><StatusBadge tone={badgeTone(item.verdictMos)}>{item.verdictMos}</StatusBadge></td><td className="px-3 py-3"><button type="button" onClick={() => setSelectedCase(item)} className="rounded-md border border-white/10 p-1.5 text-[#9aa9bf] hover:border-[#3892d0] hover:text-white" aria-label={`Simulate entry for ${item.quarter}`}><Icon kind="edit" /></button></td></> : <><td className="px-3 py-3 font-semibold text-white">{item.ticker}</td><td className="px-3 py-3"><button type="button" onClick={() => setSelectedCase(item)} className="text-[#65b7ee] hover:text-white hover:underline">{item.quarter}</button></td><td className="px-3 py-3 text-[#b9c6d8]">{item.analysisDate}</td><td className="px-3 py-3 text-[#b9c6d8]">{item.sector}</td><td className="px-3 py-3 text-[#b9c6d8]">{item.stockType}</td><td className="px-3 py-3 text-white">{price(item.analysisPrice)}</td><td className="px-3 py-3"><StatusBadge tone={badgeTone(item.consensus)}>{item.consensus}</StatusBadge></td><td className="px-3 py-3 text-[#f2d18f]">{percent(item.mosMain)}</td><td className="px-3 py-3 text-[#f2d18f]">{percent(item.mosPeter)}</td><td className="px-3 py-3 text-[#f2d18f]">{percent(item.mosWeight)}</td><td className="px-3 py-3"><StatusBadge tone={badgeTone(item.verdict)}>{item.verdict}</StatusBadge></td><td className="px-3 py-3"><StatusBadge tone={badgeTone(item.verdictMos)}>{item.verdictMos}</StatusBadge></td><td className="px-3 py-3"><button type="button" onClick={() => setSelectedCase(item)} className="rounded-md border border-white/10 p-1.5 text-[#9aa9bf] hover:border-[#3892d0] hover:text-white" aria-label={`Open ${item.quarter}`}><Icon kind="edit" /></button></td></>}</tr>)}</tbody></table>}</div></SectionCard>
    <SectionCard icon={<Icon kind="book" />} title="How the Backtest Works" subtitle="A simple and transparent process to evaluate historical outcomes."><div className="grid gap-4 lg:grid-cols-3"><Step number="01" title="Identify the Condition" text="Each historical quarter is classified as Undervalued, Overvalued, or Mixed using the valuation framework available on the analysis date." /><Step number="02" title="Track Price Movement" text="After the analysis date, price movement is observed for up to 12 months against predefined upside and downside thresholds." /><Step number="03" title="Determine the Outcome" text="The first threshold reached determines the historical outcome. This is evidence of past behavior, not a prediction or recommendation." /></div></SectionCard>
    {selectedCase && <DetailDrawer testCase={selectedCase} onClose={() => setSelectedCase(null)} />}</div>;
}

function Step({ number, title, text }: { number: string; title: string; text: string }) {
  return <article className="relative rounded-xl border border-white/8 bg-[#081523]/75 p-4"><div className="flex h-8 w-8 items-center justify-center rounded-lg border border-[#3892d0]/30 bg-[#3892d0]/10 text-xs font-bold text-[#65b7ee]">{number}</div><h4 className="mt-4 text-sm font-semibold text-white">{title}</h4><p className="mt-2 text-xs leading-5 text-[#9aa9bf]">{text}</p></article>;
}
