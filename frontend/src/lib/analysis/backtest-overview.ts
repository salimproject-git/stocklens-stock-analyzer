import type { BacktestCase, BacktestVerdict } from "@/data/mock-stock-details";
import { classifyMethodsAbovePrice, classifyMosMain, type ValuationClassification } from "./backtest";

type OutcomeCounts = Record<BacktestVerdict, number>;
const verdicts: BacktestVerdict[] = ["WIN", "RECOVERED", "FLAT", "RISK", "REPRICE", "CONFIRMED", "OBSERVE"];

function aggregate(cases: BacktestCase[], classify: (testCase: BacktestCase) => ValuationClassification, outcome: (testCase: BacktestCase) => BacktestVerdict) {
  const outcomes = Object.fromEntries(verdicts.map((verdict) => [verdict, 0])) as OutcomeCounts;
  let undervalued = 0;
  for (const testCase of cases) {
    if (classify(testCase) === "UNDERVALUED") undervalued += 1;
    outcomes[outcome(testCase)] += 1;
  }
  return { totalCases: cases.length, valuationSignal: { undervalued, overvaluedMixed: cases.length - undervalued }, outcomes };
}

export function aggregateBacktestOverview(cases: BacktestCase[], analysisPrices: Record<string, number> = {}) {
  const classifyByMethod = (testCase: BacktestCase) => classifyMethodsAbovePrice(testCase.methods, analysisPrices[testCase.id] ?? testCase.analysisPrice).classification;
  const classifyByMosMain = (testCase: BacktestCase) => classifyMosMain(testCase.mosMain);
  const byMethod = aggregate(cases, classifyByMethod, (testCase) => testCase.verdict);
  const byMosMain = aggregate(cases, classifyByMosMain, (testCase) => testCase.verdictMos);
  const undervaluedByMethod = cases.filter((testCase) => classifyByMethod(testCase) === "UNDERVALUED");
  const undervaluedByMosMain = cases.filter((testCase) => classifyByMosMain(testCase) === "UNDERVALUED");
  const overvaluedByMethod = cases.filter((testCase) => classifyByMethod(testCase) !== "UNDERVALUED");
  const overvaluedByMosMain = cases.filter((testCase) => classifyByMosMain(testCase) !== "UNDERVALUED");
  const undervaluedMethodOutcomes = aggregate(undervaluedByMethod, classifyByMethod, (testCase) => testCase.verdict).outcomes;
  const undervaluedMosOutcomes = aggregate(undervaluedByMosMain, classifyByMosMain, (testCase) => testCase.verdictMos).outcomes;
  const overvaluedMethodOutcomes = aggregate(overvaluedByMethod, classifyByMethod, (testCase) => testCase.verdict).outcomes;
  const overvaluedMosOutcomes = aggregate(overvaluedByMosMain, classifyByMosMain, (testCase) => testCase.verdictMos).outcomes;
  return {
    byMethod,
    byMosMain,
    undervaluedCases: {
      byMethod: {
        totalCases: undervaluedByMethod.length,
        outcomes: undervaluedMethodOutcomes,
        readout: buildHistoricalBacktestReadout(undervaluedByMethod.length, undervaluedMethodOutcomes),
      },
      byMosMain: {
        totalCases: undervaluedByMosMain.length,
        outcomes: undervaluedMosOutcomes,
        readout: buildHistoricalBacktestReadout(undervaluedByMosMain.length, undervaluedMosOutcomes),
      },
    },
    overvaluedCases: {
      byMethod: { totalCases: overvaluedByMethod.length, outcomes: overvaluedMethodOutcomes },
      byMosMain: { totalCases: overvaluedByMosMain.length, outcomes: overvaluedMosOutcomes },
    },
  };
}

export function buildHistoricalBacktestReadout(total: number, outcomes: Pick<OutcomeCounts, "WIN" | "RECOVERED" | "FLAT" | "RISK">) {
  const winRate = total > 0 ? (outcomes.WIN / total) * 100 : 0;
  const lines = [`Of ${total} historical cases classified as Undervalued, ${outcomes.WIN} resulted in WIN (${winRate.toFixed(1)}%).`];
  const recorded = (["RECOVERED", "FLAT", "RISK"] as const)
    .map((verdict) => [verdict, outcomes[verdict]] as const)
    .filter(([, count]) => count > 0);
  if (recorded.length === 0) lines.push("No other outcome was recorded within this group.");
  else for (const [verdict, count] of recorded) lines.push(`${verdict}: ${count}.`);
  return lines;
}
