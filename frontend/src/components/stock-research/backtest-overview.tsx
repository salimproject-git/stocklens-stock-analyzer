import type { BacktestCase, BacktestConsensus, BacktestVerdict } from "@/data/mock-stock-details";

type SignalView = {
  title: string;
  subtitle: string;
  icon: "method" | "mos";
  total: number;
  undervalued: number;
  overvalued: number;
  undervaluedOutcomes: Record<"WIN" | "RECOVERED" | "FLAT" | "RISK", number>;
  overvaluedOutcomes: Record<"REPRICE" | "CONFIRMED" | "OBSERVE", number>;
};

const undervaluedColors = { WIN: "#36d991", RECOVERED: "#55c7f2", FLAT: "#8290a4", RISK: "#ff827d" };
const overvaluedColors = { REPRICE: "#a882ff", CONFIRMED: "#55c7f2", OBSERVE: "#8290a4" };

function percentage(value: number, total: number) { return total > 0 ? (value / total) * 100 : 0; }
function formatPercentage(value: number, total: number) { const result = percentage(value, total); return result === 0 ? "0%" : `${result.toFixed(1)}%`; }

function deriveView(cases: BacktestCase[], classify: (item: BacktestCase) => BacktestConsensus, outcome: (item: BacktestCase) => BacktestVerdict, title: string, subtitle: string, icon: "method" | "mos"): SignalView {
  const undervaluedCases = cases.filter((item) => classify(item) === "UNDERVALUED");
  const overvaluedCases = cases.filter((item) => classify(item) !== "UNDERVALUED");
  const count = <T extends string>(items: BacktestCase[], keys: readonly T[]) => Object.fromEntries(keys.map((key) => [key, items.filter((item) => outcome(item) === key).length])) as Record<T, number>;
  const undervaluedOutcomes = count(undervaluedCases, ["WIN", "RECOVERED", "FLAT", "RISK"]);
  return { title, subtitle, icon, total: cases.length, undervalued: undervaluedCases.length, overvalued: overvaluedCases.length, undervaluedOutcomes: count(undervaluedCases, ["WIN", "RECOVERED", "FLAT", "RISK"]), overvaluedOutcomes: count(overvaluedCases, ["REPRICE", "CONFIRMED", "OBSERVE"]) };
}

export function BacktestOverviewIcon({ kind }: { kind: "method" | "mos" | "history" }) {
  const paths = {
    method: <><path d="M4 17 9 12l3 3 7-8" /><path d="M15 7h4v4" /><path d="M4 20h16" /></>,
    mos: <><path d="M12 3 19 6v5c0 4.4-2.9 8.2-7 10-4.1-1.8-7-5.6-7-10V6l7-3Z" /><path d="m9 12 2 2 4-4" /></>,
    history: <><path d="M4 19V5M4 19h16" /><path d="M7 15v-3M11 15V8M15 15v-5M19 15V6" /></>,
  };
  return <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" className="h-4 w-4" aria-hidden="true">{paths[kind]}</svg>;
}
function Glyph({ type }: { type: "method" | "mos" | "analytics" | "info" | "bulb" }) {
  return <span aria-hidden="true">{type === "analytics" ? "▥" : type === "bulb" ? "◉" : type === "info" ? "i" : type === "mos" ? "◈" : "⌁"}</span>;
}

function OutcomeRows({ values, total, colors }: { values: Record<string, number>; total: number; colors: Record<string, string> }) {
  return <div className="space-y-1.5">{Object.entries(values).map(([label, count]) => <div key={label} className="grid grid-cols-[76px_minmax(0,1fr)_42px_48px] items-center gap-2 text-[10px]"><span className="flex items-center gap-2 font-semibold text-[#cbd5e3]"><i className="h-1.5 w-1.5 rounded-full" style={{ backgroundColor: colors[label] }} />{label}</span><span className="h-1.5 min-w-0 overflow-hidden rounded-full bg-[#172536]"><i className="block h-full rounded-full" style={{ width: `${percentage(count, total)}%`, backgroundColor: colors[label] }} /></span><span className="whitespace-nowrap rounded-md bg-[#111e2d] px-1 py-1 text-center font-medium text-[#d8e0eb]">{count} / {total}</span><span className="whitespace-nowrap rounded-md bg-[#111e2d] px-1 py-1 text-center font-medium text-[#91a0b4]">{formatPercentage(count, total)}</span></div>)}</div>;
}

function OutcomePanel({ title, total, values, colors }: { title: string; total: number; values: Record<string, number>; colors: Record<string, string> }) {
  return <section className="rounded-xl border border-white/[0.07] bg-[#0a1726]/65 p-2.5"><h4 className="mb-3 flex items-center gap-3 text-[13px] font-semibold text-[#e7edf7]"><span>{title}</span><small className="text-[11px] font-normal text-[#74839a]">({total} cases)</small></h4><OutcomeRows values={values} total={total} colors={colors} /></section>;
}

function SignalCard({ view }: { view: SignalView }) {
  const undervaluedShare = percentage(view.undervalued, view.total);
  return <article className="flex flex-col rounded-[20px] border border-white/10 bg-[linear-gradient(180deg,rgba(11,23,37,0.92),rgba(7,16,28,0.94))] p-5 shadow-[0_24px_48px_rgba(0,0,0,0.28)] transition-colors hover:border-white/20 md:p-6"><header className="mb-5 flex items-start justify-between gap-4"><div className="flex items-center gap-3"><span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg border border-[#d6a24d]/40 bg-[#f2bb5c]/10 text-[#f2bb5c]"><BacktestOverviewIcon kind={view.icon} /></span><div><h3 className="text-[17px] font-semibold tracking-[-0.01em] text-white">{view.title}</h3><p className="mt-0.5 text-xs text-[#9aa9bf]">{view.subtitle}</p></div></div></header><section><h4 className="mb-3 flex items-center gap-2 text-[13px] font-semibold text-[#e7edf7]">Valuation Signal <small className="text-[11px] font-normal text-[#74839a]">({view.total} cases)</small></h4><div className="flex h-[34px] overflow-hidden rounded-lg bg-[#172536] text-[10px] font-semibold text-white"><div className="flex items-center justify-center bg-[#219d71]" style={{ width: `${undervaluedShare}%` }}>{view.undervalued} ({formatPercentage(view.undervalued, view.total)})</div><div className="flex items-center justify-center bg-[#3892d0]" style={{ width: `${100 - undervaluedShare}%` }}>{view.overvalued} ({formatPercentage(view.overvalued, view.total)})</div></div><div className="mt-2 flex gap-4 text-[10px]"><span className="text-[#219d71]">● Undervalued</span><span className="text-[#3892d0]">● Overvalued</span></div></section><div className="my-4 border-t border-white/[0.08]" /><div className="grid gap-3 xl:grid-cols-2"><OutcomePanel title="Undervalued Outcome" total={view.undervalued} values={view.undervaluedOutcomes} colors={undervaluedColors} /><OutcomePanel title="Overvalued Outcome" total={view.overvalued} values={view.overvaluedOutcomes} colors={overvaluedColors} /></div></article>;
}

export function BacktestOverview({ cases, analysisPrices }: { cases: BacktestCase[]; analysisPrices: Record<string, number> }) {
  const method = deriveView(cases, (item) => { const price = analysisPrices[item.id] ?? item.analysisPrice; return item.methods.filter((entry) => entry.intrinsicValue !== null && entry.intrinsicValue > price).length >= 3 ? "UNDERVALUED" : "OVERVALUED"; }, (item) => item.verdict, "By Method", "Historical results based on the combined valuation methods.", "method");
  const mos = deriveView(cases, (item) => item.mosMain !== null && item.mosMain >= 0.3 ? "UNDERVALUED" : "OVERVALUED", (item) => item.verdictMos, "By MoS Main", "Historical results based on the main Margin of Safety signal.", "mos");
  return <div className="grid items-stretch gap-4 md:grid-cols-2"><SignalCard view={method} /><SignalCard view={mos} /></div>;
}
