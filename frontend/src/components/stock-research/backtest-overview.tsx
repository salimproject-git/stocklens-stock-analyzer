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

const undervaluedColors = { WIN: "#36d991", RECOVERED: "#55c7f2", FLAT: "#8290a4", RISK: "#e9b85b" };
const overvaluedColors = { REPRICE: "#a882ff", CONFIRMED: "#ff827d", OBSERVE: "#8290a4" };

function percentage(value: number, total: number) { return total > 0 ? (value / total) * 100 : 0; }
function formatPercentage(value: number, total: number) { const result = percentage(value, total); return result === 0 ? "0%" : `${result.toFixed(1)}%`; }

function deriveView(cases: BacktestCase[], classify: (item: BacktestCase) => BacktestConsensus, outcome: (item: BacktestCase) => BacktestVerdict, title: string, subtitle: string, icon: "method" | "mos"): SignalView {
  const undervaluedCases = cases.filter((item) => classify(item) === "UNDERVALUED");
  const overvaluedCases = cases.filter((item) => classify(item) !== "UNDERVALUED");
  const count = <T extends string>(items: BacktestCase[], keys: readonly T[]) => Object.fromEntries(keys.map((key) => [key, items.filter((item) => outcome(item) === key).length])) as Record<T, number>;
  return { title, subtitle, icon, total: cases.length, undervalued: undervaluedCases.length, overvalued: overvaluedCases.length, undervaluedOutcomes: count(undervaluedCases, ["WIN", "RECOVERED", "FLAT", "RISK"]), overvaluedOutcomes: count(overvaluedCases, ["REPRICE", "CONFIRMED", "OBSERVE"]) };
}

function Glyph({ type }: { type: "method" | "mos" | "analytics" | "info" | "bulb" }) {
  return <span aria-hidden="true">{type === "analytics" ? "▥" : type === "bulb" ? "◉" : type === "info" ? "i" : type === "mos" ? "◈" : "⌁"}</span>;
}

function OutcomeRows({ values, total, colors }: { values: Record<string, number>; total: number; colors: Record<string, string> }) {
  return <div className="space-y-2.5">{Object.entries(values).map(([label, count]) => <div key={label} className="grid grid-cols-[82px_minmax(0,1fr)_62px] items-center gap-2 text-[10px]"><span className="flex items-center gap-2 font-semibold text-[#cbd5e3]"><i className="h-1.5 w-1.5 rounded-full" style={{ backgroundColor: colors[label] }} />{label}</span><span className="h-1.5 overflow-hidden rounded-full bg-[#172536]"><i className="block h-full rounded-full" style={{ width: `${percentage(count, total)}%`, backgroundColor: colors[label] }} /></span><span className="text-right text-[#8796aa]">{count} / {total} {formatPercentage(count, total)}</span></div>)}</div>;
}

function OutcomePanel({ title, total, values, colors }: { title: string; total: number; values: Record<string, number>; colors: Record<string, string> }) {
  return <section className="rounded-xl border border-white/[0.07] bg-[#0a1726]/65 p-3"><h4 className="mb-3 text-[13px] font-semibold text-[#e7edf7]">{title} <small className="text-[11px] font-normal text-[#74839a]">({total} cases)</small> <span title="Outcome distribution among cases within this valuation signal." className="text-[#75849a]"><Glyph type="info" /></span></h4><OutcomeRows values={values} total={total} colors={colors} /></section>;
}

function SignalCard({ view }: { view: SignalView }) {
  const undervaluedShare = percentage(view.undervalued, view.total);
  return <article className="flex min-h-[650px] flex-col rounded-[18px] border border-[#26394e] bg-[#0d1b2b] p-5 shadow-[0_12px_35px_rgba(0,0,0,0.14)] transition-colors hover:border-[#35506c]"><header className="mb-5 flex items-start justify-between gap-3"><div><div className="flex items-center gap-2"><span className="rounded-lg border border-[#3b9fd1]/30 bg-[#3b9fd1]/10 px-2 py-1 text-[#68c9f4]"><Glyph type={view.icon} /></span><h3 className="text-[20px] font-bold text-white">{view.title}</h3></div><p className="mt-2 text-[11px] text-[#8493a8]">{view.subtitle}</p></div><span className="rounded-full border border-white/10 bg-[#14263a] px-2.5 py-1 text-[10px] text-[#9aaac0]">{view.total} cases</span></header><section><h4 className="mb-3 flex items-center gap-2 text-[13px] font-semibold text-[#e7edf7]">Valuation Signal <small className="text-[11px] font-normal text-[#74839a]">({view.total} cases)</small> <span title="Historical cases classified as Undervalued or Overvalued / Mixed based on the selected valuation framework." className="text-[#75849a]"><Glyph type="info" /></span></h4><div className="flex h-[34px] overflow-hidden rounded-lg bg-[#172536] text-[10px] font-semibold text-white"><div className="flex items-center justify-center bg-[#219d71]" style={{ width: `${undervaluedShare}%` }}>{view.undervalued} ({formatPercentage(view.undervalued, view.total)})</div><div className="flex items-center justify-center bg-[#b45458]" style={{ width: `${100 - undervaluedShare}%` }}>{view.overvalued} ({formatPercentage(view.overvalued, view.total)})</div></div><div className="mt-2 flex gap-4 text-[10px] text-[#8290a4]"><span>● Undervalued</span><span>● Overvalued / Mixed</span></div></section><div className="my-4 border-t border-white/[0.08]" /><div className="space-y-3"><OutcomePanel title="Historical Outcome - Undervalued" total={view.undervalued} values={view.undervaluedOutcomes} colors={undervaluedColors} /><OutcomePanel title="Historical Outcome - Overvalued / Mixed" total={view.overvalued} values={view.overvaluedOutcomes} colors={overvaluedColors} /></div></article>;
}

function UndervaluedPanel({ view }: { view: SignalView }) {
  const share = percentage(view.undervalued, view.total);
  const win = view.undervaluedOutcomes.WIN;
  return <section className="rounded-xl border border-white/[0.08] bg-[#0a1726]/75 p-3.5"><div className="mb-3 flex items-center justify-between"><h4 className="text-[13px] font-semibold text-[#e8eef8]">{view.title}</h4><span className="text-[10px] text-[#8392a7]">{view.undervalued} cases</span></div><div className="grid grid-cols-[72px_78px_minmax(0,1fr)] items-center gap-3"><div className="flex w-[72px] flex-col items-center gap-1"><div className="relative h-16 w-16 rounded-full" style={{ background: `conic-gradient(#35d795 ${share}%, #1d3043 ${share}% 100%)` }}><div className="absolute inset-[7px] flex items-center justify-center rounded-full bg-[#0b1a2a]"><span className="text-[12px] font-bold text-white">{formatPercentage(view.undervalued, view.total)}</span></div></div><span className="text-[9px] text-[#718097]">of total cases</span></div><div className="text-center"><div className="text-[22px] font-bold text-white">{formatPercentage(win, view.undervalued)}</div><div className="text-[9px] font-semibold text-[#91a0b4]">WIN rate</div><div className="mt-1 text-[9px] text-[#68788e]">({win} / {view.undervalued} cases)</div></div><OutcomeRows values={view.undervaluedOutcomes} total={view.undervalued} colors={undervaluedColors} /></div></section>;
}

function BothViewsCard({ method, mos }: { method: SignalView; mos: SignalView }) {
  return <article className="flex min-h-[650px] flex-col rounded-[18px] border border-[#26394e] bg-[#0d1b2b] p-5 shadow-[0_12px_35px_rgba(0,0,0,0.14)] transition-colors hover:border-[#35506c]"><header className="mb-5 flex items-start justify-between gap-3"><div><div className="flex items-center gap-2"><span className="rounded-lg border border-[#9c75f0]/30 bg-[#9c75f0]/10 px-2 py-1 text-[#b999ff]"><Glyph type="analytics" /></span><h3 className="text-[20px] font-bold text-white">Undervalued Cases (Both Views)</h3></div><p className="mt-2 text-[11px] text-[#8493a8]">Undervalued signals and their historical outcomes.</p></div><span className="rounded-full border border-white/10 bg-[#14263a] px-2.5 py-1 text-[10px] text-[#9aaac0]">{method.total} cases</span></header><div className="space-y-3"><UndervaluedPanel view={method} /><UndervaluedPanel view={mos} /></div><div className="mt-auto pt-4"><div className="flex items-start gap-2 rounded-xl border border-[#bfa35d]/15 bg-[#8a7020]/10 px-3 py-2.5 text-[10px] leading-4 text-[#b8b7a7]"><span className="text-[#e3bd69]"><Glyph type="bulb" /></span><span>Both views recorded a 100% historical WIN rate among their Undervalued cases, with a different number of cases identified.</span></div></div></article>;
}

export function BacktestOverview({ cases, analysisPrices }: { cases: BacktestCase[]; analysisPrices: Record<string, number> }) {
  const method = deriveView(cases, (item) => { const price = analysisPrices[item.id] ?? item.analysisPrice; return item.methods.filter((entry) => entry.intrinsicValue !== null && entry.intrinsicValue > price).length >= 3 ? "UNDERVALUED" : "OVERVALUED"; }, (item) => item.verdict, "By Method", "Historical results using the main valuation method.", "method");
  const mos = deriveView(cases, (item) => item.mosMain !== null && item.mosMain >= 0.3 ? "UNDERVALUED" : "OVERVALUED", (item) => item.verdictMos, "By MoS Main", "Historical results using the Margin of Safety approach.", "mos");
  return <div className="grid items-stretch gap-4 md:grid-cols-2 xl:grid-cols-3"><SignalCard view={method} /><SignalCard view={mos} /><BothViewsCard method={method} mos={mos} /></div>;
}
